import subprocess
from pathlib import Path

from pydantic import BaseModel

from censorr.audio.windows import MuteWindow

_SILENCE_FLOOR_DB = -50.0


class WindowMeasurement(BaseModel):
    start_s: float
    end_s: float
    mean_db: float
    is_silent: bool


class AudioQCResult(BaseModel):
    window_measurements: list[WindowMeasurement] = []
    mute_ratio: float
    max_window_s: float
    control_audio_ok: bool
    violations: list[str] = []


def _mean_volume_db(path: Path, start_s: float, duration_s: float) -> float:
    if duration_s <= 0:
        return _SILENCE_FLOOR_DB
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner",
            "-ss", str(start_s), "-t", str(duration_s),
            "-i", str(path),
            "-af", "volumedetect", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stderr.splitlines():
        if "mean_volume" in line:
            return float(line.split(":")[1].strip().split(" ")[0])
    return _SILENCE_FLOOR_DB


def _control_sample_ranges(
    windows: list[MuteWindow],
    total_duration_s: float,
    *,
    sample_duration_s: float = 1.0,
    count: int = 5,
) -> list[tuple[float, float]]:
    """Evenly-spaced sample regions that fall outside every mute window."""
    if total_duration_s <= 0:
        return []
    samples = []
    step = total_duration_s / (count + 1)
    for i in range(1, count + 1):
        start = step * i
        end = start + sample_duration_s
        if end > total_duration_s:
            continue
        if any(w.start_s < end and start < w.end_s for w in windows):
            continue
        samples.append((start, sample_duration_s))
    return samples


def evaluate_window(
    window: MuteWindow, measured_db: float, *, control_db: float, audio_min_drop_db: float
) -> tuple[WindowMeasurement, str | None]:
    """Pure: under-mute check for one already-measured window."""
    is_silent = measured_db <= control_db + audio_min_drop_db
    measurement = WindowMeasurement(
        start_s=window.start_s, end_s=window.end_s, mean_db=measured_db, is_silent=is_silent
    )
    if is_silent:
        return measurement, None
    violation = (
        f"window {window.start_s:.2f}-{window.end_s:.2f}s not silent enough: "
        f"{measured_db:.1f}dB vs control {control_db:.1f}dB "
        f"(need <= {audio_min_drop_db:.1f}dB drop)"
    )
    return measurement, violation


def evaluate_over_mute_budgets(
    windows: list[MuteWindow],
    total_duration_s: float,
    *,
    max_mute_ratio: float,
    max_window_s: float,
) -> tuple[float, float, list[str]]:
    """Pure: over-mute ratio/duration budgets.

    Returns (mute_ratio, max_observed_window_s, violations).
    """
    total_mute_s = sum(w.end_s - w.start_s for w in windows)
    mute_ratio = total_mute_s / total_duration_s if total_duration_s > 0 else 0.0
    max_observed_window = max((w.end_s - w.start_s for w in windows), default=0.0)

    violations = []
    if mute_ratio > max_mute_ratio:
        violations.append(f"mute ratio {mute_ratio:.2%} exceeds budget {max_mute_ratio:.2%}")
    if max_observed_window > max_window_s:
        violations.append(
            f"max window {max_observed_window:.1f}s exceeds budget {max_window_s:.1f}s"
        )
    return mute_ratio, max_observed_window, violations


def evaluate_control_integrity(control_dbs: list[float]) -> tuple[bool, list[str]]:
    """Pure: sampled non-window regions must not themselves be near-silent
    (catches a filter bug or hostile wordlist muting the whole file)."""
    mean_control_db = sum(control_dbs) / len(control_dbs) if control_dbs else _SILENCE_FLOOR_DB
    control_audio_ok = bool(control_dbs) and mean_control_db > _SILENCE_FLOOR_DB
    if control_audio_ok:
        return True, []
    return False, ["control-audio integrity check failed (no valid non-window audio found)"]


def audit(
    output_path: Path,
    windows: list[MuteWindow],
    total_duration_s: float,
    *,
    audio_min_drop_db: float,
    max_mute_ratio: float,
    max_window_s: float,
) -> AudioQCResult:
    """R14 symmetric audio QC, measured directly on the output container
    (never compared cross-file -- that would false-fail a lossy fallback
    re-encode). Orchestrates real ffmpeg measurement + the pure budget
    evaluators above.
    """
    control_ranges = _control_sample_ranges(windows, total_duration_s)
    control_dbs = [_mean_volume_db(output_path, s, d) for s, d in control_ranges]
    control_db = sum(control_dbs) / len(control_dbs) if control_dbs else _SILENCE_FLOOR_DB

    measurements: list[WindowMeasurement] = []
    violations: list[str] = []
    for w in windows:
        inset = min(0.1, (w.end_s - w.start_s) / 4)
        measure_start = w.start_s + inset
        measure_duration = max(w.end_s - w.start_s - 2 * inset, 0.01)
        db = _mean_volume_db(output_path, measure_start, measure_duration)
        measurement, violation = evaluate_window(
            w, db, control_db=control_db, audio_min_drop_db=audio_min_drop_db
        )
        measurements.append(measurement)
        if violation:
            violations.append(violation)

    mute_ratio, max_observed_window, budget_violations = evaluate_over_mute_budgets(
        windows, total_duration_s, max_mute_ratio=max_mute_ratio, max_window_s=max_window_s
    )
    violations += budget_violations

    control_audio_ok, control_violations = evaluate_control_integrity(control_dbs)
    violations += control_violations

    return AudioQCResult(
        window_measurements=measurements,
        mute_ratio=mute_ratio,
        max_window_s=max_observed_window,
        control_audio_ok=control_audio_ok,
        violations=violations,
    )
