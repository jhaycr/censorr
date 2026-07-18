import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import typer

from censorr import __version__
from censorr.cli import views
from censorr.config.load import load_config
from censorr.naming.plex import classify
from censorr.pipeline import runner
from censorr.pipeline.context import PipelineContext
from censorr.pipeline.errors import CensorrError, exit_code_for
from censorr.pipeline.fingerprint import check_skip, resolve_wordlist
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
    force: bool = typer.Option(False, "--force", help="Bypass the fingerprint skip-check"),
    keep_intermediates: bool = typer.Option(
        False, "--keep-intermediates", help="Keep the workdir after a successful publish"
    ),
) -> None:
    """Censor a media file: remux, verify, and publish to its Plex-correct
    location. Skips automatically if an up-to-date output already exists
    (R10); --force bypasses that check. --dry-run stops after planning.
    """
    if dry_run:
        ctx = _run_planning(file, preset, config)
        views.render_inspect(ctx)
        return

    ctx = _build_context(file, preset, config)

    if not force:
        media_type = classify(ctx.job.source, ctx.job.media_type_hint)
        wordlist = resolve_wordlist(ctx.cfg)
        skip, naming_plan = check_skip(ctx.job.source, media_type, cfg=ctx.cfg, wordlist=wordlist)
        if skip:
            typer.echo(f"skipped (fingerprint_match): {naming_plan.video_path}")
            raise typer.Exit(code=2)

    workdir = Path(tempfile.mkdtemp(prefix="censorr-"))
    try:
        ctx = run_pipeline(ctx, workdir)
    except CensorrError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=exit_code_for(exc)) from exc

    views.render_inspect(ctx)

    if ctx.outcome is not None:
        # R16 skip outcome (no_text_subtitles, language_mismatch, skipped_clean):
        # nothing was published, workdir has nothing worth keeping.
        if not keep_intermediates:
            shutil.rmtree(workdir, ignore_errors=True)
        raise typer.Exit(code=2)

    if ctx.naming_plan is not None:
        views.console.print(f"[bold green]Published:[/bold green] {ctx.naming_plan.video_path}")
    if not keep_intermediates:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    app()
