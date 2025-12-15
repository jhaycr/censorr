import json
import subprocess
from pathlib import Path
from typing import Tuple

from censorr.commands.abstract_command import Command
from censorr.utils.filesystem import ensure_output_dir
from censorr.utils.logging import get_logger


logger = get_logger(__name__)


class VideoRemux(Command):
	"""Remux a video with masked subtitles and muted audio."""

	def do(
		self,
		input_video_path: str,
		masked_subtitle_path: str,
		muted_audio_path: str,
		*,
		remux_mode: str | None = None,
		naming_mode: str = "movie",
		output_base: str | None = None,
		sidecar_language: str = "eng",
	) -> str:
		remux_mode = (remux_mode or "replace").lower()
		naming_mode = naming_mode.lower()
		if remux_mode not in {"append", "replace"}:
			raise ValueError("remux_mode must be 'append' or 'replace'")
		if naming_mode not in {"movie", "tv"}:
			raise ValueError("naming_mode must be 'movie' or 'tv'")

		input_path = Path(input_video_path)
		subtitle_path = Path(masked_subtitle_path)
		audio_path = Path(muted_audio_path)

		if not input_path.exists():
			raise FileNotFoundError(f"Input video not found: {input_video_path}")
		if not subtitle_path.exists():
			raise FileNotFoundError(f"Masked subtitle not found: {masked_subtitle_path}")
		if not audio_path.exists():
			raise FileNotFoundError(f"Muted audio not found: {muted_audio_path}")

		audio_count, subtitle_count = self._probe_stream_counts(input_path)
		output_path = self._build_output_path(input_path, naming_mode, output_base)
		ensure_output_dir(str(output_path.parent))

		cmd = self._build_ffmpeg_cmd(
			input_path,
			audio_path,
			output_path,
			remux_mode,
			audio_count,
		)

		sidecar_path = self._write_subtitle_sidecar(output_path, subtitle_path, sidecar_language)

		logger.info("Remuxing to %s (remux_mode=%s, naming_mode=%s)", output_path, remux_mode, naming_mode)
		result = subprocess.run(cmd, capture_output=True, text=True)
		if result.returncode != 0:
			logger.error("ffmpeg remux failed: %s", result.stderr)
			raise RuntimeError(f"Failed to remux video: {result.stderr}")

		return str(output_path)

	def _probe_stream_counts(self, input_path: Path) -> Tuple[int, int]:
		result = subprocess.run(
			[
				"ffprobe",
				"-v",
				"quiet",
				"-print_format",
				"json",
				"-show_streams",
				str(input_path),
			],
			capture_output=True,
			text=True,
		)
		if result.returncode != 0:
			raise RuntimeError(f"Failed to probe streams: {result.stderr}")

		data = json.loads(result.stdout)
		streams = data.get("streams", [])
		audio = [s for s in streams if s.get("codec_type") == "audio"]
		subs = [s for s in streams if s.get("codec_type") == "subtitle"]
		return len(audio), len(subs)

	def _build_output_path(self, input_path: Path, naming_mode: str, output_base: str | None) -> Path:
		suffix = input_path.suffix
		if naming_mode == "movie":
			stem = input_path.stem
			insert_at = len(stem)
			for token in [" {", " [", " ("]:
				pos = stem.find(token)
				if pos != -1:
					insert_at = pos
					break
			new_stem = f"{stem[:insert_at].rstrip()} {{edition-Censorr}} {stem[insert_at:].lstrip()}".strip()
			base_dir = Path(output_base) if output_base else input_path.parent
			return base_dir / f"{new_stem}{suffix}"

		# tv naming
		# Expect .../<show>/<season>/<episode>.mkv; insert [Censorr] on show folder
		season_dir = input_path.parent
		show_dir = season_dir.parent if season_dir.parent != season_dir else season_dir
		root_dir = show_dir.parent
		base_root = Path(output_base) if output_base else root_dir
		show_name = f"{show_dir.name} [Censorr]"
		return base_root / show_name / season_dir.name / input_path.name

	def _build_ffmpeg_cmd(
		self,
		input_path: Path,
		audio_path: Path,
		output_path: Path,
		remux_mode: str,
		input_audio_count: int,
	) -> list[str]:
		cmd: list[str] = [
			"ffmpeg",
			"-i",
			str(input_path),
			"-i",
			str(audio_path),
		]

		if remux_mode == "append":
			cmd.extend(["-map", "0"])  # keep everything from original
			cmd.extend(["-map", "1:a?"])  # muted audio

			new_audio_idx = input_audio_count
		else:  # replace
			# keep video and other data, drop original audio streams
			cmd.extend(["-map", "0:v?"])
			cmd.extend(["-map", "0:d?"])
			cmd.extend(["-map", "0:t?"])
			cmd.extend(["-map_chapters", "0"])
			cmd.extend(["-map", "1:a?"])

			new_audio_idx = 0

		# Copy all streams; we only adjust metadata for the new audio track
		cmd.extend(["-c", "copy"])

		cmd.extend(["-metadata:s:a:%d" % new_audio_idx, "title=Censorr"])

		cmd.extend(["-y", str(output_path)])
		return cmd

	def _write_subtitle_sidecar(self, output_path: Path, subtitle_path: Path, language: str) -> Path:
		sidecar_name = f"{output_path.stem}.{language}.censorr.srt"
		sidecar_path = output_path.with_name(sidecar_name)
		sidecar_path.write_bytes(subtitle_path.read_bytes())
		logger.info("Wrote subtitle sidecar to %s", sidecar_path)
		return sidecar_path
