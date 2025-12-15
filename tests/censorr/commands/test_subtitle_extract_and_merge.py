import json
import subprocess
from pathlib import Path

import pytest

from censorr.commands.subtitle_extract_and_merge import SubtitleExtractAndMerge


@pytest.fixture()
def sample_probe_data():
    return {
        "streams": [
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "eng", "title": ""},
                "disposition": {"forced": 0},
            },
            {
                "index": 3,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "eng", "title": "SDH"},
                "disposition": {"forced": 0},
            },
            {
                "index": 4,
                "codec_type": "subtitle",
                "codec_name": "hdmv_pgs_subtitle",
                "tags": {"language": "eng", "title": "Image"},
                "disposition": {"forced": 0},
            },
            {
                "index": 5,
                "codec_type": "subtitle",
                "codec_name": "mov_text",
                "tags": {"language": "eng", "title": "alt"},
                "disposition": {"forced": 0},
            },
        ]
    }


def _srt_for(text: str) -> str:
    return f"1\n00:00:00,000 --> 00:00:02,000\n{text}\n"


def make_fake_run(tmp_path: Path, probe_data: dict):
    """Factory producing a subprocess.run fake that writes outputs."""

    def fake_run(cmd, capture_output=True, text=True, **kwargs):
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(probe_data), stderr="")

        if cmd[0] == "ffmpeg":
            # Output path is always last argument in our commands
            out_path = Path(cmd[-1])
            out_path.parent.mkdir(parents=True, exist_ok=True)

            # Determine the map value to pick content
            map_val = None
            if "-map" in cmd:
                map_idx = cmd.index("-map") + 1
                map_val = cmd[map_idx]

            text = {
                "0:s:0": "Hello shared",
                "0:s:1": "Hello shared",  # duplicate content for deduplication check
                "0:s:3": "Hello mov-text",
            }.get(map_val, f"Hello {map_val or 'unknown'}")

            content = _srt_for(text)

            out_path.write_text(content, encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        raise AssertionError(f"Unexpected command: {cmd}")

    return fake_run


def test_excludes_sdh_and_dedup(tmp_path, monkeypatch, sample_probe_data):
    fake_run = make_fake_run(tmp_path, sample_probe_data)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = SubtitleExtractAndMerge()
    output_dir = tmp_path / "out"
    op.do(
        input_file_path="/fake/video.mkv",
        output_dir=str(output_dir),
        selectors_include={"language": ["en"]},
        selectors_exclude={"any": ["sdh"]},
    )

    merged = (output_dir / "merged_subtitles.srt").read_text(encoding="utf-8")
    # Only the normal track should remain
    assert "Hello shared" in merged
    assert merged.count("Hello shared") == 1


def test_includes_only_sdh_when_requested(tmp_path, monkeypatch, sample_probe_data):
    fake_run = make_fake_run(tmp_path, sample_probe_data)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = SubtitleExtractAndMerge()
    output_dir = tmp_path / "out"
    op.do(
        input_file_path="/fake/video.mkv",
        output_dir=str(output_dir),
        selectors_include={"any": ["sdh"], "language": ["en"]},
        selectors_exclude={},
    )

    merged = (output_dir / "merged_subtitles.srt").read_text(encoding="utf-8")
    assert "Hello shared" in merged
    assert merged.count("Hello shared") == 1


def test_deduplicates_identical_lines(tmp_path, monkeypatch, sample_probe_data):
    fake_run = make_fake_run(tmp_path, sample_probe_data)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = SubtitleExtractAndMerge()
    output_dir = tmp_path / "out"
    # Include both normal and SDH; they share the same text timings in our fixtures
    op.do(
        input_file_path="/fake/video.mkv",
        output_dir=str(output_dir),
        selectors_include={"language": ["en"]},
        selectors_exclude={},
    )

    merged = (output_dir / "merged_subtitles.srt").read_text(encoding="utf-8")
    # Only one occurrence of the shared line should remain
    assert merged.count("Hello shared") == 1


def test_raises_when_no_match(tmp_path, monkeypatch, sample_probe_data):
    fake_run = make_fake_run(tmp_path, sample_probe_data)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = SubtitleExtractAndMerge()
    output_dir = tmp_path / "out"
    with pytest.raises(RuntimeError):
        op.do(
            input_file_path="/fake/video.mkv",
            output_dir=str(output_dir),
            selectors_include={"language": ["fr"]},
            selectors_exclude={},
        )


def test_transcodes_mov_text(tmp_path, monkeypatch, sample_probe_data):
    fake_run = make_fake_run(tmp_path, sample_probe_data)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = SubtitleExtractAndMerge()
    output_dir = tmp_path / "out"
    # Include mov_text by not excluding it, language matches en
    op.do(
        input_file_path="/fake/video.mkv",
        output_dir=str(output_dir),
        selectors_include={"language": ["en"]},
        selectors_exclude={},
    )

    # mov_text stream is the fourth subtitle in probe order (index=5 -> relative 3)
    mov_text_out = output_dir / "subtitle_3_eng_alt.srt"
    assert mov_text_out.exists()
    assert "Hello mov-text" in mov_text_out.read_text(encoding="utf-8")
