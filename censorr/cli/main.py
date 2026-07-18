import tempfile
from pathlib import Path
from uuid import uuid4

import typer

from censorr import __version__
from censorr.cli import views
from censorr.config.load import load_config
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
    """Run the plan-only stages (probe through plan_names; no remux/publish
    yet -- those land in Steps 9-11). Writes nothing outside the workdir.
    """
    ctx = _build_context(file, preset, config_path)
    with tempfile.TemporaryDirectory(prefix="censorr-") as workdir:
        try:
            ctx = run_pipeline(ctx, Path(workdir))
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
) -> None:
    """Censor a media file. Only --dry-run is implemented so far (Step 8);
    the actual remux/verify/publish pipeline lands in Steps 9-11.
    """
    if not dry_run:
        typer.echo("error: process without --dry-run isn't implemented yet", err=True)
        raise typer.Exit(code=1)
    ctx = _run_planning(file, preset, config)
    views.render_inspect(ctx)


if __name__ == "__main__":
    app()
