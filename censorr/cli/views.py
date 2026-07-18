from rich.console import Console
from rich.table import Table

from censorr.pipeline.context import PipelineContext

console = Console()


def render_inspect(ctx: PipelineContext) -> None:
    console.print(f"[bold]Source:[/bold] {ctx.job.source}")
    console.print(f"[bold]Mode:[/bold] {ctx.mode}")
    if ctx.outcome:
        console.print(f"[bold yellow]Outcome:[/bold yellow] {ctx.outcome}")

    if ctx.media_info is not None:
        table = Table(title="Tracks")
        table.add_column("Index")
        table.add_column("Type")
        table.add_column("Codec")
        table.add_column("Language")
        table.add_column("Title")
        for s in ctx.media_info.streams:
            table.add_row(str(s.index), s.codec_type, s.codec_name, s.language or "", s.title or "")
        console.print(table)

    if ctx.selection is not None:
        console.print(
            f"[bold]Selection:[/bold] audio=#{ctx.selection.audio_stream} "
            f"({ctx.selection.audio_lang}), subtitle=#{ctx.selection.subtitle_stream} "
            f"({ctx.selection.subtitle_lang}), mismatch={ctx.selection.language_mismatch}"
        )

    if ctx.matches:
        total = sum(len(v) for v in ctx.matches.values())
        console.print(f"[bold]Matches:[/bold] {total} across {len(ctx.matches)} entries")

    if ctx.windows:
        console.print(f"[bold]Mute windows:[/bold] {len(ctx.windows)}")
        for w in ctx.windows:
            console.print(f"  {w.start_s:.2f}s - {w.end_s:.2f}s ({w.reason})")

    if ctx.naming_plan is not None:
        console.print(f"[bold]Planned output:[/bold] {ctx.naming_plan.video_path}")
        for p in ctx.naming_plan.sidecar_paths:
            console.print(f"  sidecar: {p}")
