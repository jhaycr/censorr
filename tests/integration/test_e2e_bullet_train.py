"""End-to-end acceptance test in the style of a real-world "clean a whole
film" run (the Bullet Train manual retest), but fully hermetic: media is
lavfi-synthesized and the target is the non-profane stand-in word "banana",
so no profanity ships in the test corpus.

It drives the entire pipeline (probe -> ... -> publish) over a transcript that
embeds the word in every form the matcher must catch -- plain, inflected,
hyphenated tmesis (the "abso-fuckin'-lutely" case), and glued infix -- and
proves the published output contains the word nowhere: subtitles masked, audio
muted, clean lines and clean audio untouched.
"""

import json
import re
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from censorr.config.schema import ResolvedConfig
from censorr.pipeline.context import PipelineContext
from censorr.pipeline.job import Job
from censorr.pipeline.runner import run_pipeline
from tests.fixtures import BULLET_TRAIN_ENTRIES, build_movie_fixture

pytestmark = pytest.mark.ffmpeg

# The stand-in wordlist: one benign word, aggressive so glued infixes
# ("absbananalutely") match by substring, mirroring how "fuck" is configured
# in the shipped default wordlist.
BANANA_WORDLIST = {"words": [{"word": "banana", "aggressive": True}], "allowlist": []}


def _mean_volume_db(path: Path, start_s: float, duration_s: float) -> float:
    """Mean volume (dB) of one audio span in `path`. Anchored on the label so
    FFmpeg 8.x's merged log lines parse correctly (mirrors audio/qc.py)."""
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner",
            "-ss", str(start_s), "-t", str(duration_s), "-i", str(path),
            "-af", "volumedetect", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", result.stderr)
    return float(match.group(1)) if match else -91.0


def test_e2e_bullet_train_style_censors_every_form(tmp_path: Path) -> None:
    source = build_movie_fixture(
        tmp_path / "src", duration=280.0, entries=BULLET_TRAIN_ENTRIES
    )
    wordlist_path = tmp_path / "banana.json"
    wordlist_path.write_text(json.dumps(BANANA_WORDLIST))
    cfg = ResolvedConfig(
        detect={"wordlist": str(wordlist_path)},
        service={"queue_path": str(tmp_path / "queue")},
    )

    job = Job(id=str(uuid4()), source=source, submitted_by="cli")
    ctx = run_pipeline(PipelineContext(job=job, cfg=cfg), tmp_path / "workdir")

    # --- Published through the full pipeline; original untouched -------------
    assert ctx.outcome is None, f"unexpected short-circuit: {ctx.outcome}"
    assert ctx.naming_plan is not None
    output = ctx.naming_plan.video_path
    assert output.is_file()
    assert source.is_file()  # R-invariant: sources are never modified

    # --- QC passed with zero residual profanity ------------------------------
    assert ctx.qc_report is not None
    assert ctx.qc_report.passed is True
    assert ctx.qc_report.subtitle_residuals == []  # nothing profane slipped through
    assert ctx.qc_report.unmasked_text_identical is True  # clean lines untouched
    assert ctx.qc_report.control_audio_ok is True

    # Every profane form (plain, inflected, tmesis, glued) became its own window.
    assert len(ctx.windows) == 4

    # --- The word appears NOWHERE in the published subtitle ------------------
    masked_srt = tmp_path / "published_masked.srt"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(output), "-map", "0:s:0",
         str(masked_srt)],
        check=True,
    )
    published_text = masked_srt.read_text(encoding="utf-8").lower()
    assert "banana" not in published_text
    # The hyphenated tmesis was masked in place, its wrapper text preserved.
    assert "abso-" in published_text
    assert "-lutely" in published_text
    # Clean control lines survive verbatim.
    assert "completely ordinary" in published_text
    assert "nothing worth censoring" in published_text

    # --- The audio is silenced at every profane window, audible elsewhere ----
    # The pipeline's own QC measured every window on the published output.
    assert len(ctx.qc_report.audio_windows) == 4
    assert all(w.is_silent for w in ctx.qc_report.audio_windows)
    # Independently confirm on disk: each window's inner core is silent, while a
    # gap between windows stays as loud as the source tone.
    for window in ctx.windows:
        db = _mean_volume_db(output, window.start_s + 1.0, window.end_s - window.start_s - 2.0)
        assert db <= -50.0, f"window {window.start_s}-{window.end_s}s not muted ({db} dB)"
    assert _mean_volume_db(output, 40.0, 2.0) > -30.0
