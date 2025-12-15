import json
import subprocess
from pathlib import Path

import pytest

from censorr.commands.audio_extract import AudioExtract


def make_fake_run_for_audio(tmp_path: Path, probe_data: dict):
    """Factory producing a subprocess.run fake for audio extract.

    - Returns provided ffprobe JSON
    - For ffmpeg, creates the output file at the last argument path
    - Captures all commands for later assertions via closure attribute
    """

    calls = []

    def fake_run(cmd, capture_output=True, text=True, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(probe_data), stderr="")

        if cmd[0] == "ffmpeg":
            out_path = Path(cmd[-1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            # Write a tiny placeholder file to simulate output
            out_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        raise AssertionError(f"Unexpected command: {cmd}")

    fake_run.calls = calls
    return fake_run


@pytest.fixture()
def sample_audio_probe():
    # Simulate two audio streams in order: eng (default) then spa
    return {
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "sample_rate": "48000",
                "tags": {"language": "eng", "title": "Main"},
                "disposition": {"default": 1},
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "eac3",
                "channels": 6,
                "sample_rate": "48000",
                "tags": {"language": "spa", "title": ""},
                "disposition": {"default": 0},
            },
        ]
    }


def test_extracts_requested_language_and_preserves_params(tmp_path, monkeypatch, sample_audio_probe):
    fake_run = make_fake_run_for_audio(tmp_path, sample_audio_probe)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = AudioExtract()
    output_dir = tmp_path / "out"
    out_path = op.do(
        input_file_path="/fake/video.mkv",
        output_dir=str(output_dir),
        include_language=["en"],
    )

    # Output file should be named with language and title
    assert out_path.endswith("audio_eng_Main.wav")
    assert (output_dir / "audio_eng_Main.wav").exists()

    # Validate ffmpeg command used relative stream index 0 and preserved rate/channels
    ffmpeg_cmds = [c for c in fake_run.calls if c[0] == "ffmpeg"]
    assert ffmpeg_cmds, "ffmpeg was not invoked"
    cmd = ffmpeg_cmds[-1]

    # Mapping and codec
    assert "-map" in cmd and cmd[cmd.index("-map") + 1] == "0:a:0"
    assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "pcm_s16le"

    # Preserved sample rate and channels
    assert "-ar" in cmd and cmd[cmd.index("-ar") + 1] == "48000"
    assert "-ac" in cmd and cmd[cmd.index("-ac") + 1] == "2"


def test_selects_default_when_no_language_filter(tmp_path, monkeypatch, sample_audio_probe):
    fake_run = make_fake_run_for_audio(tmp_path, sample_audio_probe)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = AudioExtract()
    output_dir = tmp_path / "out"
    out_path = op.do(
        input_file_path="/fake/video.mkv",
        output_dir=str(output_dir),
        include_language=None,
    )

    # Should select the default stream (eng at relative 0)
    assert out_path.endswith("audio_eng_Main.wav")
    ffmpeg_cmds = [c for c in fake_run.calls if c[0] == "ffmpeg"]
    cmd = ffmpeg_cmds[-1]
    assert cmd[cmd.index("-map") + 1] == "0:a:0"


def test_raises_when_no_audio_streams(tmp_path, monkeypatch):
    probe_data = {"streams": []}
    fake_run = make_fake_run_for_audio(tmp_path, probe_data)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = AudioExtract()
    with pytest.raises(RuntimeError):
        op.do(
            input_file_path="/fake/video.mkv",
            output_dir=str(tmp_path / "out"),
            include_language=["en"],
        )


def test_raises_when_language_filter_has_no_match(tmp_path, monkeypatch, sample_audio_probe):
    fake_run = make_fake_run_for_audio(tmp_path, sample_audio_probe)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = AudioExtract()
    with pytest.raises(RuntimeError):
        op.do(
            input_file_path="/fake/video.mkv",
            output_dir=str(tmp_path / "out"),
            include_language=["fr"],
        )


def test_selects_specific_language_when_not_default(tmp_path, monkeypatch, sample_audio_probe):
    fake_run = make_fake_run_for_audio(tmp_path, sample_audio_probe)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = AudioExtract()
    output_dir = tmp_path / "out"
    out_path = op.do(
        input_file_path="/fake/video.mkv",
        output_dir=str(output_dir),
        include_language=["es"],  # request Spanish
    )

    assert out_path.endswith("audio_spa.wav") or out_path.endswith("audio_spa_.wav")
    ffmpeg_cmds = [c for c in fake_run.calls if c[0] == "ffmpeg"]
    cmd = ffmpeg_cmds[-1]
    # Should map the second stream (relative index 1)
    assert cmd[cmd.index("-map") + 1] == "0:a:1"
    # Spanish stream in fixture has 6 channels; verify preservation
    assert "-ac" in cmd and cmd[cmd.index("-ac") + 1] == "6"


def test_normalizes_language_names(tmp_path, monkeypatch, sample_audio_probe):
    fake_run = make_fake_run_for_audio(tmp_path, sample_audio_probe)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = AudioExtract()
    output_dir = tmp_path / "out"
    out_path = op.do(
        input_file_path="/fake/video.mkv",
        output_dir=str(output_dir),
        include_language=["English"],  # name, not code
    )

    assert out_path.endswith("audio_eng_Main.wav")


def test_does_not_pass_ar_ac_when_unknown(tmp_path, monkeypatch):
    probe_data = {
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "aac",
                # no channels / sample_rate present
                "tags": {"language": "eng"},
                "disposition": {"default": 1},
            }
        ]
    }

    fake_run = make_fake_run_for_audio(tmp_path, probe_data)
    monkeypatch.setattr(subprocess, "run", fake_run)

    op = AudioExtract()
    output_dir = tmp_path / "out"
    op.do(
        input_file_path="/fake/video.mkv",
        output_dir=str(output_dir),
        include_language=["en"],
    )

    ffmpeg_cmds = [c for c in fake_run.calls if c[0] == "ffmpeg"]
    cmd = ffmpeg_cmds[-1]
    assert "-ar" not in cmd
    assert "-ac" not in cmd
