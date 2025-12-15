import os
import logging
import json
from typing import Dict, List, Any, Optional

import subprocess
import pysubs2

from censorr.commands.abstract_command import Command
from censorr.utils.logging import get_logger
from censorr.utils.filesystem import ensure_output_dir
from censorr.utils.language import is_language_match

logger = get_logger(__name__)


class SubtitleExtractAndMerge(Command):
    """Extract and merge subtitle tracks from video files."""

    # Codec to file extension mapping for text-based subtitles
    TEXT_CODEC_MAP = {
        "subrip": "srt",
        "srt": "srt",
        "ass": "ass",
        "ssa": "ass",
        "webvtt": "vtt",
    }

    def do(
        self,
        input_file_path: str,
        output_dir: str,
        selectors_include: Optional[Dict[str, List[str]]] = None,
        selectors_exclude: Optional[Dict[str, List[str]]] = None,
    ) -> tuple[str, List[str]]:
        """
        Extract subtitle streams and merge them into a single file.

        Args:
            input_file_path: Path to input video file
            output_dir: Directory for output files
            selectors_include: Include filters by language/title/any
            selectors_exclude: Exclude filters by language/title/any
        """
        selectors_include = selectors_include or {}
        selectors_exclude = selectors_exclude or {}
        output_dir = ensure_output_dir(output_dir)

        # Probe file and get subtitle streams
        probe_data = self._probe_file(input_file_path)
        subtitle_streams = self._get_subtitle_streams(probe_data)
        logger.info(f"Found {len(subtitle_streams)} subtitle streams")

        # Filter streams by selectors
        filtered_streams = self._filter_streams(
            subtitle_streams, selectors_include, selectors_exclude
        )
        logger.info(f"Filtered to {len(filtered_streams)} matching streams")

        # Fail if no subtitles match the selectors
        if not filtered_streams:
            raise RuntimeError(
                f"No subtitle streams matched the provided selectors. "
                f"Include: {selectors_include}, Exclude: {selectors_exclude}"
            )

        # Extract filtered streams
        extracted_files = self._extract_filtered_streams(
            input_file_path, output_dir, subtitle_streams, filtered_streams
        )

        # Merge and save
        merged_path = self._merge_and_save(extracted_files, output_dir)
        return merged_path, extracted_files

    def _probe_file(self, input_path: str) -> dict:
        """Probe video file with ffprobe."""
        logger.info(f"Probing file: {input_path}")
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                input_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to probe file: {result.stderr}")
        return json.loads(result.stdout)

    def _get_subtitle_streams(self, probe_data: dict) -> List[dict]:
        """Extract subtitle streams from probe data."""
        return [
            s for s in probe_data.get("streams", [])
            if s.get("codec_type") == "subtitle"
        ]

    def _stream_info_string(self, stream: Dict[str, Any]) -> str:
        """Build searchable info string from stream metadata."""
        tags = stream.get("tags", {}) or {}
        language = str(tags.get("language", "")).strip()
        title = str(tags.get("title", "")).strip()
        codec = str(stream.get("codec_name", "")).strip()
        disposition = stream.get("disposition", {}) or {}
        forced_flag = "forced" if disposition.get("forced") == 1 else ""
        parts = [language, title, codec, forced_flag]
        return " ".join([p for p in parts if p]).lower()

    def _matches_keywords(self, text: str, keywords: List[str]) -> bool:
        """Check if any keyword matches in text."""
        if not keywords:
            return False
        lt = text.lower()
        return any(k.lower() in lt for k in keywords)

    def _should_include_stream(
        self,
        stream: Dict[str, Any],
        selectors_include: Dict[str, List[str]],
        selectors_exclude: Dict[str, List[str]],
    ) -> bool:
        """Determine if stream should be included based on selectors."""
        info = self._stream_info_string(stream)
        language = str(stream.get("tags", {}).get("language") or "").strip().lower()

        # Apply language inclusion filters (with normalization)
        include_lang = selectors_include.get("language", [])
        if include_lang and not is_language_match(language, include_lang):
            return False

        # Apply language exclusion filters
        exclude_lang = selectors_exclude.get("language", [])
        if exclude_lang and is_language_match(language, exclude_lang):
            return False

        # Check other inclusion filters (title, any)
        other_include_sets = [
            selectors_include.get("title", []),
            selectors_include.get("any", []),
        ]
        any_other_include = any(other_include_sets)
        
        if any_other_include and not include_lang:
            # If non-language includes specified, at least one must match
            if not any(
                self._matches_keywords(info, kws)
                for kws in other_include_sets if kws
            ):
                return False

        # Check exclusion filters (title, any)
        other_exclude_sets = [
            selectors_exclude.get("title", []),
            selectors_exclude.get("any", []),
        ]
        exclude_hit = any(
            self._matches_keywords(info, kws) for kws in other_exclude_sets if kws
        )
        if exclude_hit:
            return False

        return True

    def _filter_streams(
        self,
        streams: List[dict],
        selectors_include: Dict[str, List[str]],
        selectors_exclude: Dict[str, List[str]],
    ) -> List[dict]:
        """Filter streams by include/exclude selectors."""
        return [
            s for s in streams
            if self._should_include_stream(s, selectors_include, selectors_exclude)
        ]

    def _extract_filtered_streams(
        self,
        input_path: str,
        output_dir: str,
        all_streams: List[dict],
        filtered_streams: List[dict],
    ) -> List[str]:
        """Extract all filtered subtitle streams."""
        # Build subtitle-relative index mapping for ffmpeg -map 0:s:<n>
        subtitle_relative_map = {
            s.get("index"): idx for idx, s in enumerate(all_streams)
        }

        extracted_files = []
        for idx, stream in enumerate(filtered_streams):
            out_path = self._extract_one_stream(
                input_path, output_dir, stream, idx, subtitle_relative_map
            )
            if out_path:
                extracted_files.append(out_path)

        return extracted_files

    def _extract_one_stream(
        self,
        input_path: str,
        output_dir: str,
        stream: Dict[str, Any],
        idx: int,
        subtitle_relative_map: Dict[int, int],
    ) -> Optional[str]:
        """Extract a single subtitle stream."""
        stream_index = stream.get("index")
        tags = stream.get("tags", {}) or {}
        language = (tags.get("language") or "und").lower()
        title = (tags.get("title") or "").strip()
        codec_name = (stream.get("codec_name") or "").lower()

        logger.info(
            f"Processing stream {idx}: index={stream_index}, "
            f"lang={language}, title={title}, codec={codec_name}"
        )

        # Map to subtitle-relative index for ffmpeg
        subtitle_relative_idx = subtitle_relative_map.get(stream_index)
        if subtitle_relative_idx is None:
            logger.warning(
                f"Skipping stream {stream_index}: cannot map to subtitle-relative index"
            )
            return None

        # Handle text-based codecs with stream copy
        if codec_name in self.TEXT_CODEC_MAP:
            output_ext = self.TEXT_CODEC_MAP[codec_name]
            title_part = f"_{title}" if title else ""
            out_path = os.path.join(
                output_dir, f"subtitle_{idx}_{language}{title_part}.{output_ext}"
            )

            logger.info(f"Extracting via ffmpeg to {out_path}...")
            cmd = [
                "ffmpeg",
                "-i", input_path,
                "-map", f"0:s:{subtitle_relative_idx}",
                "-c:s", "copy",
                "-y",
                out_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Failed: {result.stderr}")
                return None

            logger.info("Extracted successfully")
            return out_path

        # Handle MP4 mov_text (requires transcoding to SRT)
        if codec_name == "mov_text":
            title_part = f"_{title}" if title else ""
            out_path = os.path.join(
                output_dir, f"subtitle_{idx}_{language}{title_part}.srt"
            )

            logger.info(f"Converting mov_text to {out_path}...")
            cmd = [
                "ffmpeg",
                "-i", input_path,
                "-map", f"0:s:{subtitle_relative_idx}",
                "-c:s", "srt",
                "-y",
                out_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Failed: {result.stderr}")
                return None

            logger.info("Converted successfully")
            return out_path

        # Skip image-based codecs
        logger.warning(
            f"Skipping non-text subtitle stream index {stream_index} (codec={codec_name})"
        )
        return None

    def _merge_and_save(self, extracted_files: List[str], output_dir: str) -> str:
        """Merge extracted subtitle files and save result."""
        if not extracted_files:
            empty_out = os.path.join(output_dir, "merged_subtitles.srt")
            with open(empty_out, "w", encoding="utf-8") as f:
                f.write("")
            logger.info("No matching subtitle streams found")
            return empty_out

        merged = pysubs2.SSAFile()
        seen_events = set()  # Track unique events by (start, end, text)

        for path in extracted_files:
            try:
                subs = pysubs2.load(path)
            except Exception:
                logger.warning(f"Failed to load {path}, skipping")
                continue

            for ev in subs.events:
                # Create unique key (case-insensitive)
                event_key = (ev.start, ev.end, ev.text.strip().lower())
                if event_key not in seen_events:
                    seen_events.add(event_key)
                    merged.events.append(ev)
                else:
                    logger.debug(f"Skipping duplicate subtitle: {ev.text[:50]}...")

        # Sort by start time
        merged.events.sort(key=lambda e: e.start)

        merged_path = os.path.join(output_dir, "merged_subtitles.srt")
        merged.save(merged_path, format="srt")
        logger.info(f"Merged subtitles saved to {merged_path}")
        return merged_path
