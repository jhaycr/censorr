import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from censorr.commands.abstract_command import Command
from censorr.commands.audio_mute import MuteWindow
from censorr.utils.filesystem import ensure_output_dir
from censorr.utils.logging import get_logger


logger = get_logger(__name__)


@dataclass
class VolumeSample:
    start: float
    end: float
    mean_volume_db: float


class AudioQC(Command):
    """Lightweight QC comparing muted segments against control audio."""

    def do(
        self,
        muted_audio_path: str,
        windows_path: str,
        output_dir: str,
        *,
        threshold_db: float = 20.0,
    ) -> str:
        output_dir = ensure_output_dir(output_dir)

        windows = self._load_windows(windows_path)
        if not windows:
            raise RuntimeError(f"No mute windows found in {windows_path}")

        duration = self._probe_duration(muted_audio_path)
        control_spans = self._select_control_spans(windows, duration)
        if not control_spans:
            raise RuntimeError("No control spans available for QC")

        mute_samples = [self._measure_span(muted_audio_path, w.start, w.end) for w in windows]
        control_samples = [self._measure_span(muted_audio_path, start, end) for start, end in control_spans]

        mute_mean = self._mean_db(mute_samples)
        control_mean = self._mean_db(control_samples)
        delta = control_mean - mute_mean
        passed = delta >= threshold_db

        report = {
            "threshold_db": threshold_db,
            "control_mean_db": control_mean,
            "mute_mean_db": mute_mean,
            "delta_db": delta,
            "passed": passed,
            "mute_samples": [sample.__dict__ for sample in mute_samples],
            "control_samples": [sample.__dict__ for sample in control_samples],
        }

        report_path = Path(output_dir) / "qc_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        if passed:
            logger.info("QC passed: delta %.2f dB (threshold %.2f)", delta, threshold_db)
        else:
            logger.warning("QC failed: delta %.2f dB below threshold %.2f", delta, threshold_db)

        return str(report_path)

    def _load_windows(self, path: str) -> List[MuteWindow]:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Window file not found: {path}")

        if p.suffix.lower() == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
            windows = [MuteWindow(start=float(item["start"]), end=float(item["end"])) for item in data]
            return self._merge_overlaps(windows)

        # Fallback to CSV with start_ms/end_ms columns
        from censorr.commands.audio_mute import AudioMute

        return AudioMute()._load_windows(str(p))

    def _merge_overlaps(self, windows: List[MuteWindow]) -> List[MuteWindow]:
        if not windows:
            return []
        windows = sorted(windows, key=lambda w: (w.start, w.end))
        merged = [windows[0]]
        for w in windows[1:]:
            last = merged[-1]
            if w.start <= last.end + 1e-3:
                merged[-1] = MuteWindow(start=last.start, end=max(last.end, w.end))
            else:
                merged.append(w)
        return merged

    def _probe_duration(self, path: str) -> float:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to probe duration: {result.stderr}")
        fmt = json.loads(result.stdout).get("format", {})
        return float(fmt.get("duration", 0.0))

    def _select_control_spans(
        self, windows: List[MuteWindow], duration: float, sample_len: float = 1.0, max_samples: int = 5
    ) -> List[Tuple[float, float]]:
        controls: List[Tuple[float, float]] = []
        current = 0.0
        for w in windows:
            if w.start - current >= sample_len:
                controls.append((current, min(current + sample_len, w.start)))
            current = max(current, w.end)
        if duration - current >= sample_len:
            controls.append((current, min(current + sample_len, duration)))
        return controls[:max_samples]

    def _measure_span(self, audio_path: str, start: float, end: float) -> VolumeSample:
        if end <= start:
            raise ValueError("Span end must be after start")

        cmd = [
            "ffmpeg",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            audio_path,
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("volumedetect failed: %s", result.stderr)
            raise RuntimeError("Failed to measure volume")

        mean_db = self._parse_mean_volume(result.stderr)
        if mean_db is None:
            raise RuntimeError("Could not parse mean_volume from ffmpeg output")

        return VolumeSample(start=start, end=end, mean_volume_db=mean_db)

    def _parse_mean_volume(self, stderr: str) -> float | None:
        match = re.search(r"mean_volume:\s*(-?[0-9]+\.?[0-9]*) dB", stderr)
        return float(match.group(1)) if match else None

    def _mean_db(self, samples: List[VolumeSample]) -> float:
        if not samples:
            return 0.0
        return sum(s.mean_volume_db for s in samples) / len(samples)
