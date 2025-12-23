import typer
from rich.console import Console

from censorr.pipeline import (
    RunPipeline,
    build_selectors,
    default_app_config_path,
    default_config_path,
    load_app_config,
)

app = typer.Typer(
    name="censorr",
    help="Censoring subtitles and audio in media files",
    add_completion=False,
)

console = Console()

# Shared Typer options
OUTPUT_DIR_OPTION = typer.Option(
    None, "--output", "-o", help="Output directory for generated files"
)
DEFAULT_THRESHOLD_OPTION = typer.Option(
    85.0, "--threshold", "-t", help="Default similarity threshold (0-100)"
)

INCLUDE_LANG_OPTION = typer.Option(None, "--include-lang", help="Include languages (e.g., en, eng)")
INCLUDE_TITLE_OPTION = typer.Option(None, "--include-title", help="Include by title keywords (e.g., forced)")
INCLUDE_ANY_OPTION = typer.Option(None, "--include-any", help="Include by any keyword match")

EXCLUDE_LANG_OPTION = typer.Option(None, "--exclude-lang", help="Exclude languages")
EXCLUDE_TITLE_OPTION = typer.Option(None, "--exclude-title", help="Exclude by title keywords (e.g., sdh)")
EXCLUDE_ANY_OPTION = typer.Option(None, "--exclude-any", help="Exclude by any keyword match")

@app.command()
def subtitle_extract(
    input_file_path: str,
    output_dir: str = OUTPUT_DIR_OPTION,
    include_language: list[str] = INCLUDE_LANG_OPTION,
    include_title: list[str] = INCLUDE_TITLE_OPTION,
    include_any: list[str] = INCLUDE_ANY_OPTION,
    exclude_language: list[str] = EXCLUDE_LANG_OPTION,
    exclude_title: list[str] = EXCLUDE_TITLE_OPTION,
    exclude_any: list[str] = EXCLUDE_ANY_OPTION,
):
    """Extract subtitle tracks from a video file with optional filtering."""
    from censorr.commands.subtitle_extract_and_merge import SubtitleExtractAndMerge

    selectors_include, selectors_exclude = build_selectors(
        include_language,
        include_title,
        include_any,
        exclude_language,
        exclude_title,
        exclude_any,
    )
    
    command = SubtitleExtractAndMerge()
    command.do(
        input_file_path=input_file_path,
        output_dir=output_dir,
        selectors_include=selectors_include if selectors_include else None,
        selectors_exclude=selectors_exclude if selectors_exclude else None,
    )


@app.command()
def subtitle_mask(
    input_file_path: str,
    config_path: str = typer.Argument(None, help="Path to term list (JSON array or newline file)"),
    output_dir: str = OUTPUT_DIR_OPTION,
    default_threshold: float = DEFAULT_THRESHOLD_OPTION,
):
    """Mask terms in a subtitle file and emit matches CSV."""
    from censorr.commands.subtitle_mask import SubtitleMask

    config_path = default_config_path(config_path)

    command = SubtitleMask()
    command.do(
        input_file_path=input_file_path,
        output_dir=output_dir,
        config_path=config_path,
        default_threshold=default_threshold,
    )


@app.command()
def subtitle_qc(
    input_file_path: str = typer.Argument(..., help="Path to masked subtitle file (SRT)"),
    config_path: str = typer.Option(
        None, "--config", "-c", help="Path to term list (JSON array or profanity list file)"
    ),
):
    """Fail if any configured profanities remain in the masked subtitle file."""
    from censorr.commands.subtitle_qc import SubtitleQC

    resolved_config = default_config_path(config_path)
    command = SubtitleQC()
    command.do(
        input_file_path=input_file_path,
        config_path=resolved_config,
    )


@app.command()
def audio_mute(
    audio_file_path: str = typer.Argument(..., help="Path to an extracted audio file"),
    matches_csv_path: str = typer.Option(
        ..., "--matches-csv", "-m", help="Path to profanity matches CSV from subtitle_mask"
    ),
    output_dir: str = OUTPUT_DIR_OPTION,
):
    """Mute audio segments based on a profanity matches CSV."""
    from censorr.commands.audio_mute import AudioMute

    command = AudioMute()
    command.do(
        audio_file_path=audio_file_path,
        matches_csv_path=matches_csv_path,
        output_dir=output_dir,
    )


@app.command()
def audio_qc(
    muted_audio_path: str = typer.Argument(..., help="Path to muted audio output"),
    windows_path: str = typer.Option(..., "--windows", "-w", help="Path to mute windows JSON/CSV"),
    output_dir: str = OUTPUT_DIR_OPTION,
    threshold_db: float | None = typer.Option(None, "--threshold-db", help="Minimum dB delta vs control audio"),
    config_path: str | None = typer.Option(None, "--config", "-c", help="Path to app config JSON"),
):
    """Quality-check muted audio by comparing mute windows to control segments."""
    from censorr.commands.audio_qc import AudioQC

    config_path = default_app_config_path(config_path)
    config = load_app_config(config_path)
    resolved_threshold = threshold_db
    if resolved_threshold is None:
        resolved_threshold = float(config.get("audio_qc_threshold_db", 20.0))

    command = AudioQC()
    command.do(
        muted_audio_path=muted_audio_path,
        windows_path=windows_path,
        output_dir=output_dir,
        threshold_db=resolved_threshold,
    )


@app.command()
def video_remux(
    input_video_path: str = typer.Argument(..., help="Original video path"),
    masked_subtitle_path: str = typer.Argument(..., help="Masked subtitle file (SRT)"),
    muted_audio_path: str = typer.Argument(..., help="Muted audio file"),
    remux_mode: str | None = typer.Option(None, help="Stream handling: (append | replace)"),
    naming_mode: str | None = typer.Option(None, help="Output naming: (movie | tv"),
    output_base: str | None = typer.Option(
        None, "--output-base", help="Base path for final remuxed file (defaults to input video dir)"
    ),
):
    """Remux video with masked subtitles and muted audio."""
    from censorr.commands.video_remux import VideoRemux

    command = VideoRemux()
    command.do(
        input_video_path=input_video_path,
        masked_subtitle_path=masked_subtitle_path,
        muted_audio_path=muted_audio_path,
        remux_mode=remux_mode or "replace",
        naming_mode=naming_mode or "movie",
        output_base=output_base,
    )


@app.command()
def run(
    input_file_path: str,
    output_dir: str | None = OUTPUT_DIR_OPTION,
    include_language: list[str] | None = INCLUDE_LANG_OPTION,
    include_title: list[str] | None = INCLUDE_TITLE_OPTION,
    include_any: list[str] | None = INCLUDE_ANY_OPTION,
    exclude_language: list[str] | None = EXCLUDE_LANG_OPTION,
    exclude_title: list[str] | None = EXCLUDE_TITLE_OPTION,
    exclude_any: list[str] | None = EXCLUDE_ANY_OPTION,
    config_path: str = typer.Option(
        None, "--config", "-c", help="Path to term list (JSON array or newline file)"
    ),
    default_threshold: float = DEFAULT_THRESHOLD_OPTION,
    qc_threshold_db: float | None = typer.Option(
        None, "--qc-threshold-db", help="Minimum dB delta for audio QC"
    ),
    app_config_path: str | None = typer.Option(
        None, "--app-config", help="Path to app config JSON (QC thresholds, etc.)"
    ),
    remux_mode: str | None = typer.Option(
        None, help="Remux stream handling: (append | replace)"
    ),
    remux_naming_mode: str | None = typer.Option(
        None, help="Remux output naming: (movie | tv)"
    ),
    remux_output_base: str | None = typer.Option(
        None,
        "--remux-output-base",
        help="Base path for final remuxed video (defaults to input video directory)",
    ),
    cleanup: bool = typer.Option(
        True,
        "--cleanup/--no-cleanup",
        help="Remove intermediate files created in output_dir after a successful run",
    ),
):
    """Run subtitle extraction, masking, audio extraction, muting, QC, and remux."""
    pipeline = RunPipeline(console=console)
    return pipeline.run(
        input_file_path=input_file_path,
        output_dir=output_dir,
        include_language=include_language,
        include_title=include_title,
        include_any=include_any,
        exclude_language=exclude_language,
        exclude_title=exclude_title,
        exclude_any=exclude_any,
        config_path=config_path,
        default_threshold=default_threshold,
        qc_threshold_db=qc_threshold_db,
        app_config_path=app_config_path,
        remux_mode=remux_mode,
        remux_naming_mode=remux_naming_mode,
        remux_output_base=remux_output_base,
        cleanup=cleanup,
    )


@app.command("queue-run")
def queue_run(
    input_file_path: str,
    output_dir: str | None = OUTPUT_DIR_OPTION,
    include_language: list[str] | None = INCLUDE_LANG_OPTION,
    include_title: list[str] | None = INCLUDE_TITLE_OPTION,
    include_any: list[str] | None = INCLUDE_ANY_OPTION,
    exclude_language: list[str] | None = EXCLUDE_LANG_OPTION,
    exclude_title: list[str] | None = EXCLUDE_TITLE_OPTION,
    exclude_any: list[str] | None = EXCLUDE_ANY_OPTION,
    config_path: str = typer.Option(
        None, "--config", "-c", help="Path to term list (JSON array or newline file)"
    ),
    default_threshold: float = DEFAULT_THRESHOLD_OPTION,
    qc_threshold_db: float | None = typer.Option(
        None, "--qc-threshold-db", help="Minimum dB delta for audio QC"
    ),
    app_config_path: str | None = typer.Option(
        None, "--app-config", help="Path to app config JSON"
    ),
    remux_mode: str | None = typer.Option(
        None, help="Remux stream handling: (append | replace)"
    ),
    remux_naming_mode: str | None = typer.Option(
        None, help="Remux output naming: (movie | tv)"
    ),
    remux_output_base: str | None = typer.Option(
        None,
        "--remux-output-base",
        help="Base path for final remuxed video (defaults to input video directory)",
    ),
    cleanup: bool = typer.Option(
        True,
        "--cleanup/--no-cleanup",
        help="Remove intermediate files created in output_dir after a successful run",
    ),
):
    """Enqueue and process a single job with the in-memory queue/worker."""
    from censorr.worker.queue import InMemoryQueue, JobPayload
    from censorr.worker.worker import InMemoryWorker

    payload = JobPayload(
        input_file_path=input_file_path,
        output_dir=output_dir,
        include_language=include_language,
        include_title=include_title,
        include_any=include_any,
        exclude_language=exclude_language,
        exclude_title=exclude_title,
        exclude_any=exclude_any,
        config_path=config_path,
        default_threshold=default_threshold,
        qc_threshold_db=qc_threshold_db,
        app_config_path=app_config_path,
        remux_mode=remux_mode,
        remux_naming_mode=remux_naming_mode,
        remux_output_base=remux_output_base,
        cleanup=cleanup,
    )

    queue = InMemoryQueue()
    job_id = queue.enqueue(payload)
    worker = InMemoryWorker(queue, pipeline=RunPipeline(console=console))
    worker.process_next()

    status = queue.get_status(job_id)
    result_path = queue.get_result(job_id)
    console.log(f"Job {job_id} status: {status}")
    if result_path:
        console.log(f"Output: {result_path}")
    return result_path

if __name__ == "__main__":
    app()