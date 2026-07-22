import re
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from censorr.config.schema import ResolvedConfig
from censorr.media.probe import probe
from censorr.pipeline.context import PipelineContext
from censorr.pipeline.job import Job
from censorr.pipeline.runner import REMUX_STAGES, run_pipeline

pytestmark = pytest.mark.ffmpeg


def run_full(source: Path, tmp_path: Path, cfg: ResolvedConfig | None = None) -> PipelineContext:
    """Runs through remux but not verify -- these tests check remux
    mechanics (track layout, codecs, muting), not QC gating (Step 10's
    own tests in test_qc.py cover that; the dense synthetic fixtures used
    here legitimately trip QC's over-mute budget at their short duration).
    """
    job = Job(id=str(uuid4()), source=source, submitted_by="cli")
    ctx = PipelineContext(job=job, cfg=cfg or ResolvedConfig())
    return run_pipeline(ctx, tmp_path, stage_sequence=REMUX_STAGES)


def mean_volume_db(path: Path, start_s: float, duration_s: float) -> float:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner",
            "-ss", str(start_s), "-t", str(duration_s),
            "-i", str(path),
            "-af", "volumedetect", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    # Anchor on the label: FFmpeg 8.x can flush this summary onto the same
    # captured line as preceding encoder/version metadata (mirrors audio/qc.py).
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", result.stderr)
    if match:
        return float(match.group(1))
    raise AssertionError(f"mean_volume not found in ffmpeg output for {path}")


def test_remux_track_layout_dispositions_titles(movie_fixture: Path, tmp_path: Path) -> None:
    ctx = run_full(movie_fixture, tmp_path)

    assert ctx.temp_output is not None
    info = probe(ctx.temp_output)

    assert len(info.video_streams()) == 1
    audio = info.audio_streams()
    assert len(audio) == 1
    assert audio[0].codec_name == "aac"
    assert audio[0].language == "eng"
    assert audio[0].title == "English (Censored)"
    assert audio[0].disposition.get("default") is True

    subs = info.subtitle_streams()
    assert len(subs) == 2  # masked full track + mute-captions track
    assert subs[0].title == "English (Censored)"
    assert subs[1].title == "English (Muted Dialogue)"
    assert subs[1].disposition.get("forced") is True
    assert subs[1].disposition.get("default") is True


def test_remux_fingerprint_metadata_present(movie_fixture: Path, tmp_path: Path) -> None:
    ctx = run_full(movie_fixture, tmp_path)
    assert ctx.temp_output is not None

    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(ctx.temp_output)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "CENSORR_FINGERPRINT" in result.stdout


def test_remux_duration_parity(movie_fixture: Path, tmp_path: Path) -> None:
    ctx = run_full(movie_fixture, tmp_path)
    assert ctx.temp_output is not None

    source_duration = probe(movie_fixture).duration_s
    output_duration = probe(ctx.temp_output).duration_s

    assert output_duration == pytest.approx(source_duration, abs=0.5)


def test_muted_window_is_silent_vs_audible_control(movie_fixture: Path, tmp_path: Path) -> None:
    ctx = run_full(movie_fixture, tmp_path)
    assert ctx.temp_output is not None
    assert len(ctx.windows) == 2

    window = ctx.windows[0]
    inset_start = window.start_s + 0.1
    inset_duration = window.end_s - window.start_s - 0.2
    muted_db = mean_volume_db(ctx.temp_output, inset_start, inset_duration)
    control_db = mean_volume_db(ctx.temp_output, 10.0, 1.0)  # entry 2 (10.0-11.0) is clean/unmuted

    assert muted_db < -60.0  # effectively silent
    assert control_db > -40.0  # audibly present
    assert muted_db < control_db - 20.0


def test_eac3_51_fixture_preserves_codec_and_channels(
    eac3_51_fixture: Path, tmp_path: Path
) -> None:
    ctx = run_full(eac3_51_fixture, tmp_path)
    assert ctx.temp_output is not None

    info = probe(ctx.temp_output)
    audio = info.audio_streams()[0]

    assert audio.codec_name == "eac3"
    assert audio.channels == 6


def test_clean_fixture_omits_captions_track(clean_movie_fixture: Path, tmp_path: Path) -> None:
    # Testing remux mechanics for "clean" mode here, not the R16 skip policy
    # (Step 11 covers that) -- override so a clean movie still remuxes.
    cfg = ResolvedConfig(behavior={"on_clean_movie": "publish"})
    ctx = run_full(clean_movie_fixture, tmp_path, cfg=cfg)
    assert ctx.temp_output is not None
    assert ctx.mode == "clean"

    info = probe(ctx.temp_output)
    subs = info.subtitle_streams()

    assert len(subs) == 1  # masked (== original, unchanged) only, no captions track
    audio = info.audio_streams()[0]
    assert audio.codec_name == "aac"  # zero-match -> stream-copy, no re-encode


def test_subtitles_only_mode_stream_copies_audio_unmuted(
    language_mismatch_fixture: Path, tmp_path: Path
) -> None:
    ctx = run_full(language_mismatch_fixture, tmp_path)
    assert ctx.temp_output is not None
    assert ctx.mode == "subtitles_only"

    info = probe(ctx.temp_output)
    subs = info.subtitle_streams()

    assert len(subs) == 1  # captions track omitted in subtitles_only mode (R16)
    # unmuted control: audio should be audible throughout, including where a
    # match would have triggered a mute window in full mode
    loud_db = mean_volume_db(ctx.temp_output, 2.0, 1.0)
    assert loud_db > -40.0
