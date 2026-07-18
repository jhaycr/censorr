import tempfile
from pathlib import Path
from uuid import uuid4

import typer

from censorr import __version__
from censorr.cli import views
from censorr.config.load import load_config
from censorr.pipeline import runner
from censorr.pipeline.context import PipelineContext
from censorr.pipeline.errors import CensorrError, exit_code_for
from censorr.pipeline.job import Job
from censorr.pipeline.runner import run_pipeline

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main() -> None:
    """Censorr — censors profanity in media audio and subtitles."""


@app.command()
def version() -> None:
    """Print the installed censorr version."""
    typer.echo(__version__)


def _build_context(file: Path, preset: str | None, config_path: Path | None) -> PipelineContext:
    cfg = load_config(config_path=config_path, preset=preset)
    job = Job(id=str(uuid4()), source=file, preset=preset, submitted_by="cli")
    return PipelineContext(job=job, cfg=cfg)


def _run_planning(file: Path, preset: str | None, config_path: Path | None) -> PipelineContext:
    """Run only the plan-only stages (probe through plan_names; no remux
    yet). Writes nothing outside the workdir.
    """
    ctx = _build_context(file, preset, config_path)
    with tempfile.TemporaryDirectory(prefix="censorr-") as workdir:
        try:
            ctx = run_pipeline(ctx, Path(workdir), stage_sequence=runner.PLANNING_STAGES)
        except CensorrError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=exit_code_for(exc)) from exc
    return ctx


@app.command()
def inspect(
    file: Path = typer.Argument(..., exists=True, dir_okay=False),
    preset: str | None = typer.Option(None, "--preset"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    """Probe + selection + windows + names; writes nothing outside the workdir."""
    ctx = _run_planning(file, preset, config)
    views.render_inspect(ctx)


@app.command()
def process(
    file: Path = typer.Argument(..., exists=True, dir_okay=False),
    preset: str | None = typer.Option(None, "--preset"),
    config: Path | None = typer.Option(None, "--config"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    keep_intermediates: bool = typer.Option(
        False,
        "--keep-intermediates",
        help="No-op until Step 11 adds cleanup-on-success for this flag to suppress",
    ),
) -> None:
    """Censor a media file. Without --dry-run this remuxes for real to a
    temp file in the workdir; publish/placement lands in Step 11.
    """
    if dry_run:
        ctx = _run_planning(file, preset, config)
        views.render_inspect(ctx)
        return

    ctx = _build_context(file, preset, config)
    workdir = Path(tempfile.mkdtemp(prefix="censorr-"))
    try:
        ctx = run_pipeline(ctx, workdir)
    except CensorrError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=exit_code_for(exc)) from exc

    views.render_inspect(ctx)
    if ctx.temp_output is not None:
        views.console.print(f"[bold]Temp output (not yet published):[/bold] {ctx.temp_output}")
    _ = keep_intermediates  # accepted now; enforced once Step 11 adds cleanup-on-success


if __name__ == "__main__":
    app()
