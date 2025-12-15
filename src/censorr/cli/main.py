import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

app = typer.Typer(
    name="censorr",
    help="Censoring subtitles and audio in media files",
    add_completion=False,
)

console = Console()

# Shared Typer options
OUTPUT_DIR_OPTION = typer.Option(
    "/tmp/censorr", "--output", "-o", help="Output directory for generated files"
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


def _build_selectors(
    include_language: list[str] | None,
    include_title: list[str] | None,
    include_any: list[str] | None,
    exclude_language: list[str] | None,
    exclude_title: list[str] | None,
    exclude_any: list[str] | None,
):
    selectors_include = {}
    if include_language:
        selectors_include["language"] = include_language
    if include_title:
        selectors_include["title"] = include_title
    if include_any:
        selectors_include["any"] = include_any

    selectors_exclude = {}
    if exclude_language:
        selectors_exclude["language"] = exclude_language
    if exclude_title:
        selectors_exclude["title"] = exclude_title
    if exclude_any:
        selectors_exclude["any"] = exclude_any

    return selectors_include, selectors_exclude


def _default_config_path(config_path: str | None) -> str:
    if config_path:
        return config_path
    return str(Path(__file__).resolve().parents[3] / "config" / "profanity_list.json")


def _default_app_config_path(config_path: str | None) -> str:
    if config_path:
        return config_path
    return str(Path(__file__).resolve().parents[3] / "config" / "app_config.json")


def _load_app_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

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

    selectors_include, selectors_exclude = _build_selectors(
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

    config_path = _default_config_path(config_path)

    command = SubtitleMask()
    command.do(
        input_file_path=input_file_path,
        output_dir=output_dir,
        config_path=config_path,
        default_threshold=default_threshold,
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

    config_path = _default_app_config_path(config_path)
    config = _load_app_config(config_path)
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
    remux_mode: str | None = typer.Option(None, help="Stream handling: append or replace (default: replace)"),
    naming_mode: str = typer.Option("movie", help="Output naming: movie or tv"),
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
        naming_mode=naming_mode,
        output_base=output_base,
    )


@app.command()
def run(
    input_file_path: str,
    output_dir: str = OUTPUT_DIR_OPTION,
    include_language: list[str] = INCLUDE_LANG_OPTION,
    include_title: list[str] = INCLUDE_TITLE_OPTION,
    include_any: list[str] = INCLUDE_ANY_OPTION,
    exclude_language: list[str] = EXCLUDE_LANG_OPTION,
    exclude_title: list[str] = EXCLUDE_TITLE_OPTION,
    exclude_any: list[str] = EXCLUDE_ANY_OPTION,
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
        None, help="Remux stream handling: append or replace (default: replace)"
    ),
    remux_naming_mode: str = typer.Option("movie", help="Remux output naming: movie or tv"),
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
    from censorr.commands.subtitle_extract_and_merge import SubtitleExtractAndMerge
    from censorr.commands.subtitle_mask import SubtitleMask
    from censorr.commands.audio_extract import AudioExtract
    from censorr.commands.audio_mute import AudioMute
    from censorr.commands.audio_qc import AudioQC
    from censorr.commands.video_remux import VideoRemux

    selectors_include, selectors_exclude = _build_selectors(
        include_language,
        include_title,
        include_any,
        exclude_language,
        exclude_title,
        exclude_any,
    )

    extract = SubtitleExtractAndMerge()
    merged_path, extracted_files = extract.do(
        input_file_path=input_file_path,
        output_dir=output_dir,
        selectors_include=selectors_include if selectors_include else None,
        selectors_exclude=selectors_exclude if selectors_exclude else None,
    )
    cleanup_targets = [str(merged_path), *[str(p) for p in extracted_files]]

    config_path = _default_config_path(config_path)
    app_config_path = _default_app_config_path(app_config_path)
    app_config = _load_app_config(app_config_path)

    resolved_qc_threshold = qc_threshold_db
    if resolved_qc_threshold is None:
        resolved_qc_threshold = float(app_config.get("audio_qc_threshold_db", 20.0))

    masker = SubtitleMask()
    masker.do(
        input_file_path=merged_path,
        output_dir=output_dir,
        config_path=config_path,
        default_threshold=default_threshold,
    )

    masked_path = str(Path(output_dir) / "masked_subtitles.srt")
    matches_csv_path = Path(output_dir) / "profanity_matches.csv"
    cleanup_targets.extend([str(masked_path), str(matches_csv_path)])

    audio = AudioExtract()
    audio_path = audio.do(
        input_file_path=input_file_path,
        output_dir=output_dir,
        include_language=include_language,
    )
    cleanup_targets.append(str(audio_path))

    if not matches_csv_path.exists():
        raise RuntimeError(f"Profanity matches CSV not found at {matches_csv_path}")

    muter = AudioMute()
    muted_path, windows_path = muter.do(
        audio_file_path=audio_path,
        matches_csv_path=str(matches_csv_path),
        output_dir=output_dir,
    )
    cleanup_targets.extend([str(muted_path), str(windows_path)])

    qc = AudioQC()
    qc_report_path = qc.do(
        muted_audio_path=muted_path,
        windows_path=windows_path,
        output_dir=output_dir,
        threshold_db=resolved_qc_threshold,
    )
    cleanup_targets.append(str(qc_report_path))

    remuxer = VideoRemux()
    remux_output = remuxer.do(
        input_video_path=input_file_path,
        masked_subtitle_path=masked_path,
        muted_audio_path=muted_path,
        remux_mode=remux_mode or "replace",
        naming_mode=remux_naming_mode,
        output_base=remux_output_base,
        sidecar_language=(include_language[0] if include_language else "eng"),
    )

    if cleanup:
        base_dir = Path(output_dir).resolve()
        unique_targets = []
        for p in cleanup_targets:
            if p and p not in unique_targets:
                unique_targets.append(p)

        for p in unique_targets:
            path = Path(p)
            try:
                if not path.exists() or not path.is_file():
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(base_dir):
                    continue
                path.unlink()
                console.log(f"[green]Cleanup removed {path}[/green]")
            except Exception as exc:
                console.log(f"[yellow]Cleanup skipped for {path}: {exc}[/yellow]")

    return remux_output

if __name__ == "__main__":
    app()