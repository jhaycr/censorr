from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Console


def build_selectors(
    include_language: Optional[List[str]] = None,
    include_title: Optional[List[str]] = None,
    include_any: Optional[List[str]] = None,
    exclude_language: Optional[List[str]] = None,
    exclude_title: Optional[List[str]] = None,
    exclude_any: Optional[List[str]] = None,
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    selectors_include: Dict[str, List[str]] = {}
    if include_language:
        selectors_include["language"] = include_language
    if include_title:
        selectors_include["title"] = include_title
    if include_any:
        selectors_include["any"] = include_any

    selectors_exclude: Dict[str, List[str]] = {}
    if exclude_language:
        selectors_exclude["language"] = exclude_language
    if exclude_title:
        selectors_exclude["title"] = exclude_title
    if exclude_any:
        selectors_exclude["any"] = exclude_any

    return selectors_include, selectors_exclude


def default_config_path(config_path: Optional[str]) -> str:
    if config_path:
        return config_path
    return str(Path(__file__).resolve().parents[2] / "config" / "profanity_list.json")


def default_app_config_path(config_path: Optional[str]) -> str:
    if config_path:
        return config_path
    return str(Path(__file__).resolve().parents[2] / "config" / "app_config.json")


def load_app_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


class RunPipeline:
    """Reusable pipeline that mirrors the `censorr run` command."""

    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()

    def run(
        self,
        *,
        input_file_path: str,
        output_dir: str,
        include_language: Optional[List[str]] = None,
        include_title: Optional[List[str]] = None,
        include_any: Optional[List[str]] = None,
        exclude_language: Optional[List[str]] = None,
        exclude_title: Optional[List[str]] = None,
        exclude_any: Optional[List[str]] = None,
        config_path: Optional[str] = None,
        default_threshold: float = 85.0,
        qc_threshold_db: Optional[float] = None,
        app_config_path: Optional[str] = None,
        remux_mode: Optional[str] = None,
        remux_naming_mode: str = "movie",
        remux_output_base: Optional[str] = None,
        cleanup: bool = True,
    ) -> str:
        # Import lazily so tests can patch command classes
        from censorr.commands.subtitle_extract_and_merge import SubtitleExtractAndMerge
        from censorr.commands.subtitle_mask import SubtitleMask
        from censorr.commands.audio_extract import AudioExtract
        from censorr.commands.audio_mute import AudioMute
        from censorr.commands.audio_qc import AudioQC
        from censorr.commands.video_remux import VideoRemux

        selectors_include, selectors_exclude = build_selectors(
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

        config_path = default_config_path(config_path)
        app_config_path = default_app_config_path(app_config_path)
        app_config = load_app_config(app_config_path)

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
            unique_targets: list[str] = []
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
                    self.console.log(f"[green]Cleanup removed {path}[/green]")
                except Exception as exc:
                    self.console.log(f"[yellow]Cleanup skipped for {path}: {exc}[/yellow]")

        return remux_output
