import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import typer

from censorr import __version__
from censorr.cli import views
from censorr.config.load import load_config
from censorr.naming.plex import classify
from censorr.pipeline import library, retention, runner
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


@app.command()
def reprocess(
    root: Path = typer.Argument(..., exists=True, file_okay=False),
    preset: str | None = typer.Option(None, "--preset"),
    config: Path | None = typer.Option(None, "--config"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Bulk walk: (re)process every source file under ROOT whose fingerprint
    is stale. Skips Censorr outputs and Plex extras (R7)."""
    cfg = load_config(config_path=config, preset=preset)
    wordlist = resolve_wordlist(cfg)

    worklist: list[Path] = []
    for candidate in library.find_reprocess_candidates(root, cfg):
        media_type = classify(candidate, None)
        skip, _plan = check_skip(candidate, media_type, cfg=cfg, wordlist=wordlist)
        if not skip:
            worklist.append(candidate)

    if dry_run:
        typer.echo(f"{len(worklist)} file(s) would be processed:")
        for path in worklist:
            typer.echo(f"  {path}")
        return

    failures = 0
    for path in worklist:
        typer.echo(f"processing: {path}")
        job = Job(id=str(uuid4()), source=path, preset=preset, submitted_by="cli")
        ctx = PipelineContext(job=job, cfg=cfg)
        workdir = Path(tempfile.mkdtemp(prefix="censorr-"))
        try:
            ctx = run_pipeline(ctx, workdir)
        except CensorrError as exc:
            typer.echo(f"  error: {exc}", err=True)
            failures += 1
            continue
        if ctx.outcome is not None:
            typer.echo(f"  skipped ({ctx.outcome})")
        elif ctx.naming_plan is not None:
            typer.echo(f"  published: {ctx.naming_plan.video_path}")
        shutil.rmtree(workdir, ignore_errors=True)

    typer.echo(f"done: {len(worklist) - failures} ok, {failures} failed")
    if failures:
        raise typer.Exit(code=1)


@app.command()
def reconcile(
    clean_root: Path = typer.Argument(..., exists=True, file_okay=False),
    config: Path | None = typer.Option(None, "--config"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Delete clean outputs under CLEAN_ROOT whose source no longer exists
    (heals rename/delete drift, R7)."""
    cfg = load_config(config_path=config)
    orphans = library.find_orphaned_outputs(clean_root, cfg)

    if dry_run:
        typer.echo(f"{len(orphans)} orphaned output(s) would be removed:")
        for path in orphans:
            typer.echo(f"  {path}")
        return

    for orphan in orphans:
        for removed in library.delete_output_with_sidecars(orphan):
            typer.echo(f"removed: {removed}")
    typer.echo(f"done: {len(orphans)} orphan(s) removed")


@app.command()
def gc(
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    """Sweep expired failed workdirs and job records (R11 retention)."""
    cfg = load_config(config_path=config)
    result = retention.sweep(cfg)
    typer.echo(
        f"removed {len(result.removed_workdirs)} workdir(s), "
        f"{len(result.removed_records)} record(s)"
    )


@app.command()
def work(
    config: Path | None = typer.Option(None, "--config"),
    poll_interval: float = typer.Option(5.0, "--poll-interval", help="Seconds between polls"),
    once: bool = typer.Option(False, "--once", help="Process at most one job, then exit"),
) -> None:
    """Run the queue worker: claim jobs, run the pipeline, record progress."""
    from censorr.service.worker import Worker

    cfg = load_config(config_path=config)
    worker = Worker(cfg, config_path=config)
    typer.echo(f"worker {worker.worker_id} polling {cfg.service.queue_path}")
    if once:
        claimed = worker.run_once()
        typer.echo("processed one job" if claimed else "queue empty")
        return
    worker.run_forever(poll_interval_s=poll_interval)


@app.command()
def serve(
    config: Path | None = typer.Option(None, "--config"),
    host: str = typer.Option("0.0.0.0", "--host"),  # noqa: S104 -- container-facing bind
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Run the FastAPI service (webhooks + jobs API). Requires censorr[serve]."""
    import uvicorn

    from censorr.service.app import create_app

    cfg = load_config(config_path=config)
    uvicorn.run(create_app(cfg), host=host, port=port)


if __name__ == "__main__":
    app()
