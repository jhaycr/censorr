from collections.abc import Callable
from pathlib import Path

from censorr.pipeline import stages
from censorr.pipeline.context import PipelineContext

type Stage = Callable[[PipelineContext, Path], PipelineContext]
type OnProgress = Callable[[str, PipelineContext], None]

# Sequential order (design §3). PLANNING_STAGES writes nothing outside the
# workdir (what `inspect` / `process --dry-run` run); STAGE_SEQUENCE adds
# remux (Step 9) -- verify/publish are added in Steps 10-11.
PLANNING_STAGES: list[tuple[str, Stage]] = [
    ("probe", stages.probe),
    ("select_tracks", stages.select_tracks_stage),
    ("acquire_subtitles", stages.acquire_subtitles),
    ("detect", stages.detect),
    ("plan_windows", stages.plan_windows),
    ("mask_subtitles", stages.mask_subtitles_stage),
    ("plan_names", stages.plan_names_stage),
]

STAGE_SEQUENCE: list[tuple[str, Stage]] = [
    *PLANNING_STAGES,
    ("remux", stages.remux_stage),
]


def run_pipeline(
    ctx: PipelineContext,
    workdir: Path,
    *,
    on_progress: OnProgress | None = None,
    stage_sequence: list[tuple[str, Stage]] | None = None,
) -> PipelineContext:
    """Run stages in order. Stops early once `ctx.outcome` is set by a
    stage (R16 skip cases) -- later stages never run against a decided
    context. Each completed stage leaves a marker file in `workdir` so a
    failed job's workdir can be inspected/resumed stage-by-stage.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    for name, stage_fn in stage_sequence if stage_sequence is not None else STAGE_SEQUENCE:
        if ctx.outcome is not None:
            break
        ctx = stage_fn(ctx, workdir)
        (workdir / f".stage_{name}.done").touch()
        if on_progress is not None:
            on_progress(name, ctx)
    return ctx
