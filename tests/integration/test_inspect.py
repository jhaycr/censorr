from pathlib import Path
from uuid import uuid4

import pytest

from censorr.config.schema import ResolvedConfig
from censorr.pipeline.context import PipelineContext
from censorr.pipeline.job import Job
from censorr.pipeline.runner import run_pipeline

pytestmark = pytest.mark.ffmpeg


def run_inspect(source: Path, tmp_path: Path, cfg: ResolvedConfig | None = None) -> PipelineContext:
    job = Job(id=str(uuid4()), source=source, submitted_by="cli")
    ctx = PipelineContext(job=job, cfg=cfg or ResolvedConfig())
    return run_pipeline(ctx, tmp_path)


def test_happy_path_has_matches_and_full_mode(movie_fixture: Path, tmp_path: Path) -> None:
    ctx = run_inspect(movie_fixture, tmp_path)

    assert ctx.outcome is None
    assert ctx.mode == "full"
    assert len(ctx.matches) == 2
    assert len(ctx.windows) == 2
    assert ctx.naming_plan is not None
    assert ctx.naming_plan.video_path != movie_fixture


def test_clean_fixture_produces_clean_mode(clean_movie_fixture: Path, tmp_path: Path) -> None:
    ctx = run_inspect(clean_movie_fixture, tmp_path)

    assert ctx.outcome is None
    assert ctx.mode == "clean"
    assert ctx.matches == {}
    assert ctx.windows == []
    assert ctx.naming_plan is not None


def test_no_subtitle_fixture_produces_skip_outcome(
    no_subtitle_fixture: Path, tmp_path: Path
) -> None:
    ctx = run_inspect(no_subtitle_fixture, tmp_path)

    assert ctx.outcome == "no_text_subtitles"
    assert ctx.naming_plan is None  # short-circuited before plan_names


def test_language_mismatch_fixture_produces_subtitles_only_mode(
    language_mismatch_fixture: Path, tmp_path: Path
) -> None:
    ctx = run_inspect(language_mismatch_fixture, tmp_path)

    assert ctx.outcome is None
    assert ctx.mode == "subtitles_only"
    assert ctx.selection is not None
    assert ctx.selection.language_mismatch is True
    assert ctx.windows == []  # plan_windows is skipped in subtitles_only mode
    assert ctx.naming_plan is not None


def test_language_mismatch_disallowed_produces_skip_outcome(
    language_mismatch_fixture: Path, tmp_path: Path
) -> None:
    cfg = ResolvedConfig(subtitles={"allow_language_mismatch": False})

    ctx = run_inspect(language_mismatch_fixture, tmp_path, cfg=cfg)

    assert ctx.outcome == "language_mismatch"
