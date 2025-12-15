import json
import os
import subprocess
from typing import Dict, List, Optional

from censorr.commands.abstract_command import Command
from censorr.utils.filesystem import ensure_output_dir
from censorr.utils.language import is_language_match
from censorr.utils.logging import get_logger


logger = get_logger(__name__)


class AudioExtract(Command):
    """Extract an audio stream without re-encoding, matching a language selector."""

    CODEC_EXT_MAP = {
        "aac": "m4a",
        "mp3": "mp3",
        "flac": "flac",
        "opus": "opus",
        "vorbis": "ogg",
        "ac3": "ac3",
        "eac3": "eac3",
        "dts": "dts",
        "truehd": "thd",
        "pcm_s16le": "wav",
        "pcm_s24le": "wav",
    }

    def do(
        self,
        input_file_path: str,
        output_dir: str,
        include_language: Optional[List[str]] = None,
    ) -> str:
        output_dir = ensure_output_dir(output_dir)
        include_language = include_language or []

        probe_data = self._probe_file(input_file_path)
        audio_streams = self._get_audio_streams(probe_data)
        if not audio_streams:
            raise RuntimeError("No audio streams found in input file")

        target_stream = self._select_stream(audio_streams, include_language)
        if target_stream is None:
            raise RuntimeError(
                f"No audio stream matched languages: {include_language}"
                if include_language
                else "No audio stream selected"
            )

        relative_index = audio_streams.index(target_stream)

        out_path = self._extract_stream(
            input_file_path, output_dir, target_stream, relative_index
        )
        logger.info("Extracted audio to %s", out_path)
        return out_path

    def _probe_file(self, input_path: str) -> dict:
        logger.info("Probing file: %s", input_path)
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                input_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to probe file: {result.stderr}")
        return json.loads(result.stdout)

    def _get_audio_streams(self, probe_data: dict) -> List[dict]:
        return [s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"]

    def _select_stream(
        self, streams: List[dict], include_language: List[str]
    ) -> Optional[dict]:
        if include_language:
            lang_matches = [
                s
                for s in streams
                if is_language_match(str(s.get("tags", {}).get("language", "") or "").lower(), include_language)
            ]
        else:
            lang_matches = streams

        if not lang_matches:
            return None

        default_streams = [s for s in lang_matches if (s.get("disposition", {}) or {}).get("default") == 1]
        if default_streams:
            return default_streams[0]

        return lang_matches[0]

    def _ext_for_codec(self, codec: str) -> str:
        return self.CODEC_EXT_MAP.get(codec.lower(), "mka")

    def _extract_stream(
        self, input_path: str, output_dir: str, stream: Dict, relative_index: int
    ) -> str:
        codec_name = (stream.get("codec_name") or "").lower()
        lang = str(stream.get("tags", {}).get("language") or "und").lower()
        title = str(stream.get("tags", {}).get("title") or "").strip()
        title_part = f"_{title}" if title else ""
        
        # Probe channels and sample rate from stream
        channels = stream.get("channels")
        sample_rate = stream.get("sample_rate")

        # Extract to WAV for fast filter processing (no lossy re-encoding during mute)
        out_path = os.path.join(output_dir, f"audio_{lang}{title_part}.wav")

        cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-map",
            f"0:a:{relative_index}",
            "-c:a",
            "pcm_s16le",
        ]
        
        # Preserve original sample rate if available
        if sample_rate:
            cmd.extend(["-ar", str(sample_rate)])
        
        # Preserve original channel count if available
        if channels:
            cmd.extend(["-ac", str(channels)])
        
        cmd.extend(["-y", out_path])

        logger.info(
            "Extracting audio stream index=%s codec=%s lang=%s channels=%s rate=%s -> WAV",
            stream.get("index"),
            codec_name,
            lang,
            channels or "auto",
            sample_rate or "auto",
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("ffmpeg failed: %s", result.stderr)
            raise RuntimeError(f"Failed to extract audio: {result.stderr}")

        return out_path

