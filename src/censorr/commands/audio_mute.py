import csv
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from censorr.commands.abstract_command import Command
from censorr.utils.filesystem import ensure_output_dir
from censorr.utils.logging import get_logger


logger = get_logger(__name__)


@dataclass
class MuteWindow:
	start: float
	end: float


class AudioMute(Command):
	"""Mute segments of an extracted audio file using a profanity match CSV."""

	def do(self, audio_file_path: str, matches_csv_path: str, output_dir: str) -> Tuple[str, str]:
		output_dir = ensure_output_dir(output_dir)

		windows = self._load_windows(matches_csv_path)
		if not windows:
			raise RuntimeError("No mute windows found in matches CSV")

		windows_path = self._write_windows_sidecar(output_dir, windows)
		muted_path = self._apply_mutes(audio_file_path, windows, output_dir)

		logger.info("Muted audio written to %s (windows: %s)", muted_path, windows_path)
		return muted_path, windows_path

	def _load_windows(self, csv_path: str) -> List[MuteWindow]:
		windows: List[MuteWindow] = []
		with open(csv_path, newline="", encoding="utf-8") as f:
			reader = csv.DictReader(f)
			for row in reader:
				try:
					start_ms = float(row.get("start_ms", 0))
					end_ms = float(row.get("end_ms", 0))
					windows.append(MuteWindow(start=start_ms / 1000.0, end=end_ms / 1000.0))
				except Exception:
					continue
		windows.sort(key=lambda w: (w.start, w.end))
		return self._merge_overlaps(windows)

	def _merge_overlaps(self, windows: List[MuteWindow]) -> List[MuteWindow]:
		if not windows:
			return []
		merged: List[MuteWindow] = [windows[0]]
		for w in windows[1:]:
			last = merged[-1]
			if w.start <= last.end + 1e-3:
				merged[-1] = MuteWindow(start=last.start, end=max(last.end, w.end))
			else:
				merged.append(w)
		return merged

	def _write_windows_sidecar(self, output_dir: str, windows: List[MuteWindow]) -> str:
		sidecar_path = os.path.join(output_dir, "mute_windows.json")
		payload = [{"start": w.start, "end": w.end} for w in windows]
		with open(sidecar_path, "w", encoding="utf-8") as f:
			json.dump(payload, f, indent=2)
		return sidecar_path

	def _apply_mutes(self, audio_path: str, windows: List[MuteWindow], output_dir: str) -> str:
		input_path = Path(audio_path)
		out_path = Path(output_dir) / f"muted_{input_path.stem}{input_path.suffix}"

		# Build single volume filter with OR-combined enable conditions for efficiency
		enable_conditions = [
			f"between(t,{w.start:.3f},{w.end:.3f})"
			for w in windows
		]
		combined_enable = "+".join(enable_conditions)
		afilter = f"volume=enable='{combined_enable}':volume=0"

		cmd = [
			"ffmpeg",
			"-i",
			str(input_path),
			"-af",
			afilter,
			"-c:a",
			"pcm_s16le",
			"-y",
			str(out_path),
		]

		logger.info("Applying %d mute windows to %s", len(windows), audio_path)
		proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
		start = time.time()
		last_log = start
		while proc.poll() is None:
			time.sleep(1)
			now = time.time()
			if now - last_log >= 30:
				logger.info("Muting in progress... elapsed %.0fs", now - start)
				last_log = now

		stdout, stderr = proc.communicate()
		if proc.returncode != 0:
			logger.error("ffmpeg failed: %s", stderr)
			raise RuntimeError(f"Failed to mute audio: {stderr}")

		return str(out_path)

