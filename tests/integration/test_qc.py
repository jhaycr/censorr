import json
from pathlib import Path
from uuid import uuid4

import pytest

from censorr.audio import qc as audio_qc
from censorr.audio.windows import MuteWindow
from censorr.config.schema import ResolvedConfig
from censorr.pipeline.context import PipelineContext
from censorr.pipeline.errors import QCError
from censorr.pipeline.job import Job
from censorr.pipeline.runner import REMUX_STAGES, run_pipeline

pytestmark = pytest.mark.ffmpeg


def run_full(source: Path, tmp_path: Path, cfg: ResolvedConfig | None = None) -> PipelineContext:
    job = Job(id=str(uuid4()), source=source, submitted_by="cli")
    ctx = PipelineContext(job=job, cfg=cfg or ResolvedConfig())
    return run_pipeline(ctx, tmp_path)


def test_happy_path_passes(qc_pass_fixture: Path, tmp_path: Path) -> None:
    ctx = run_full(qc_pass_fixture, tmp_path)

    assert ctx.qc_report is not None
    assert ctx.qc_report.passed is True
    assert ctx.qc_report.unmasked_text_identical is True
    assert ctx.qc_report.subtitle_residuals == []
    assert (tmp_path / "qc_report.json").is_file()


def test_hostile_matchall_wordlist_trips_over_mute_budget(
    qc_pass_fixture: Path, tmp_path: Path
) -> None:
    # qc_pass_fixture normally PASSES QC (see test_happy_path_passes) with
    # its default 2 matches. "this" is a non-stopword that appears in the
    # fixture's clean line too ("This entry is perfectly clean"), adding a
    # 3rd mute window an aggressive wordlist has no business adding --
    # proving it's the *hostile wordlist*, not fixture density, tripping
    # the 5% mute-ratio budget.
    wordlist_path = tmp_path / "hostile.json"
    hostile_wordlist = {"words": [{"word": "this", "threshold": 50}], "allowlist": []}
    wordlist_path.write_text(json.dumps(hostile_wordlist))
    cfg = ResolvedConfig(detect={"wordlist": str(wordlist_path)})

    with pytest.raises(QCError, match="mute ratio"):
        run_full(qc_pass_fixture, tmp_path, cfg=cfg)


def test_all_silent_audio_trips_control_integrity(movie_fixture: Path, tmp_path: Path) -> None:
    job = Job(id=str(uuid4()), source=movie_fixture, submitted_by="cli")
    ctx = run_pipeline(
        PipelineContext(job=job, cfg=ResolvedConfig()),
        tmp_path,
        stage_sequence=REMUX_STAGES,
    )
    assert ctx.temp_output is not None
    assert ctx.media_info is not None

    all_covering_window = [
        MuteWindow(start_s=0.0, end_s=ctx.media_info.duration_s, source="test", reason="all_silent")
    ]

    result = audio_qc.audit(
        ctx.temp_output,
        all_covering_window,
        ctx.media_info.duration_s,
        audio_min_drop_db=-12.0,
        max_mute_ratio=0.05,
        max_window_s=15.0,
    )

    assert result.control_audio_ok is False
    assert any("control-audio integrity" in v for v in result.violations)


def test_qc_skipped_appropriately_in_clean_mode(clean_movie_fixture: Path, tmp_path: Path) -> None:
    ctx = run_full(clean_movie_fixture, tmp_path)

    assert ctx.mode == "clean"
    assert ctx.qc_report is not None
    assert ctx.qc_report.passed is True
    assert ctx.qc_report.audio_windows == []
    assert ctx.qc_report.mute_ratio == 0.0
    assert ctx.qc_report.control_audio_ok is True  # audio QC skipped -> trivially ok


def test_qc_skipped_appropriately_in_subtitles_only_mode(
    language_mismatch_fixture: Path, tmp_path: Path
) -> None:
    ctx = run_full(language_mismatch_fixture, tmp_path)

    assert ctx.mode == "subtitles_only"
    assert ctx.qc_report is not None
    assert ctx.qc_report.passed is True
    assert ctx.qc_report.audio_windows == []
    assert ctx.qc_report.control_audio_ok is True


def test_qc_report_saved_to_workdir(qc_pass_fixture: Path, tmp_path: Path) -> None:
    run_full(qc_pass_fixture, tmp_path)

    report_path = tmp_path / "qc_report.json"
    assert report_path.is_file()
    data = json.loads(report_path.read_text())
    assert data["passed"] is True
