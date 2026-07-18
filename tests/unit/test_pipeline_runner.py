from pathlib import Path

from censorr.config.schema import ResolvedConfig
from censorr.pipeline.context import PipelineContext
from censorr.pipeline.job import Job
from censorr.pipeline.runner import run_pipeline


def make_ctx(**overrides: object) -> PipelineContext:
    job = Job(id="job-1", source=Path("/media/movie.mkv"), submitted_by="cli")
    return PipelineContext(job=job, cfg=ResolvedConfig(), **overrides)  # type: ignore[arg-type]


def test_stages_run_in_order(tmp_path: Path) -> None:
    calls: list[str] = []

    def make_stage(name: str):
        def stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
            calls.append(name)
            return ctx

        return stage

    sequence = [("a", make_stage("a")), ("b", make_stage("b")), ("c", make_stage("c"))]

    run_pipeline(make_ctx(), tmp_path, stage_sequence=sequence)

    assert calls == ["a", "b", "c"]


def test_short_circuits_once_outcome_is_set(tmp_path: Path) -> None:
    calls: list[str] = []

    def stage_a(ctx: PipelineContext, workdir: Path) -> PipelineContext:
        calls.append("a")
        return ctx.model_copy(update={"outcome": "no_text_subtitles"})

    def stage_b(ctx: PipelineContext, workdir: Path) -> PipelineContext:
        calls.append("b")
        return ctx

    sequence = [("a", stage_a), ("b", stage_b)]

    result = run_pipeline(make_ctx(), tmp_path, stage_sequence=sequence)

    assert calls == ["a"]  # b never ran
    assert result.outcome == "no_text_subtitles"


def test_stage_markers_written_to_workdir(tmp_path: Path) -> None:
    def stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
        return ctx

    sequence = [("probe", stage), ("detect", stage)]

    run_pipeline(make_ctx(), tmp_path, stage_sequence=sequence)

    assert (tmp_path / ".stage_probe.done").is_file()
    assert (tmp_path / ".stage_detect.done").is_file()


def test_on_progress_called_per_stage(tmp_path: Path) -> None:
    progress_calls: list[str] = []

    def stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
        return ctx

    sequence = [("a", stage), ("b", stage)]

    run_pipeline(
        make_ctx(),
        tmp_path,
        stage_sequence=sequence,
        on_progress=lambda name, ctx: progress_calls.append(name),
    )

    assert progress_calls == ["a", "b"]


def test_already_decided_context_runs_no_stages(tmp_path: Path) -> None:
    calls: list[str] = []

    def stage(ctx: PipelineContext, workdir: Path) -> PipelineContext:
        calls.append("ran")
        return ctx

    sequence = [("a", stage)]
    ctx = make_ctx(outcome="skipped_clean")

    run_pipeline(ctx, tmp_path, stage_sequence=sequence)

    assert calls == []
