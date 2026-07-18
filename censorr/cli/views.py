from rich.console import Console
from rich.table import Table

from censorr.pipeline.context import PipelineContext, QCReport

console = Console()


def _render_tracks(ctx: PipelineContext) -> None:
    if ctx.media_info is None:
        return
    table = Table(title="Tracks")
    table.add_column("Index")
    table.add_column("Type")
    table.add_column("Codec")
    table.add_column("Language")
    table.add_column("Title")
    for s in ctx.media_info.streams:
        table.add_row(str(s.index), s.codec_type, s.codec_name, s.language or "", s.title or "")
    console.print(table)


def _render_selection(ctx: PipelineContext) -> None:
    if ctx.selection is None:
        return
    console.print(
        f"[bold]Selection:[/bold] audio=#{ctx.selection.audio_stream} "
        f"({ctx.selection.audio_lang}), subtitle=#{ctx.selection.subtitle_stream} "
        f"({ctx.selection.subtitle_lang}), mismatch={ctx.selection.language_mismatch}"
    )


def _render_matches_and_windows(ctx: PipelineContext) -> None:
    if ctx.matches:
        total = sum(len(v) for v in ctx.matches.values())
        console.print(f"[bold]Matches:[/bold] {total} across {len(ctx.matches)} entries")
    if ctx.windows:
        console.print(f"[bold]Mute windows:[/bold] {len(ctx.windows)}")
        for w in ctx.windows:
            console.print(f"  {w.start_s:.2f}s - {w.end_s:.2f}s ({w.reason})")


def _render_naming_plan(ctx: PipelineContext) -> None:
    if ctx.naming_plan is None:
        return
    console.print(f"[bold]Planned output:[/bold] {ctx.naming_plan.video_path}")
    for p in ctx.naming_plan.sidecar_paths:
        console.print(f"  sidecar: {p}")


def render_inspect(ctx: PipelineContext) -> None:
    console.print(f"[bold]Source:[/bold] {ctx.job.source}")
    console.print(f"[bold]Mode:[/bold] {ctx.mode}")
    if ctx.outcome:
        console.print(f"[bold yellow]Outcome:[/bold yellow] {ctx.outcome}")

    _render_tracks(ctx)
    _render_selection(ctx)
    _render_matches_and_windows(ctx)
    _render_naming_plan(ctx)

    if ctx.qc_report is not None:
        render_qc_report(ctx.qc_report)


def render_qc_report(report: QCReport) -> None:
    status = "[bold green]PASSED[/bold green]" if report.passed else "[bold red]FAILED[/bold red]"
    table = Table(title=f"QC Report -- {status}")
    table.add_column("Check")
    table.add_column("Value")
    table.add_row("Mute ratio", f"{report.mute_ratio:.2%}")
    table.add_row("Max window", f"{report.max_window_s:.1f}s")
    table.add_row("Matched-entry ratio", f"{report.matched_entry_ratio:.2%}")
    table.add_row("Masked-entry ratio", f"{report.masked_entry_ratio:.2%}")
    table.add_row("Control audio OK", str(report.control_audio_ok))
    table.add_row("Duration delta", f"{report.duration_delta_s:.2f}s")
    table.add_row("Unmasked text identical", str(report.unmasked_text_identical))
    table.add_row("Residual matches", str(len(report.subtitle_residuals)))
    console.print(table)
    for warning in report.warnings:
        console.print(f"  [yellow]![/yellow] {warning}")
