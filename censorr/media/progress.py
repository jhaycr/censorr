import os
import re
import subprocess
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime

_OUT_TIME_RE = re.compile(r"^out_time_ms=(-?\d+)$")

HEARTBEAT_INTERVAL_S = 10.0


def heartbeats_enabled() -> bool:
    return os.environ.get("CENSORR_NO_HEARTBEAT") != "1"


def emit_heartbeat(elapsed_s: float, context: str) -> None:
    """FR-064 format: `<UTC ISO-8601> HEARTBEAT elapsed=<N>s context="..."`."""
    if not heartbeats_enabled():
        return
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f'{timestamp} HEARTBEAT elapsed={int(elapsed_s)}s context="{context}"')


def parse_progress_lines(lines: Iterable[str], total_duration_s: float) -> Iterator[float]:
    """Parse ffmpeg `-progress pipe:1` key=value lines into a 0.0-1.0 fraction stream."""
    for line in lines:
        stripped = line.strip()
        match = _OUT_TIME_RE.match(stripped)
        if match:
            out_time_ms = int(match.group(1))
            if total_duration_s > 0 and out_time_ms >= 0:
                yield min(1.0, (out_time_ms / 1_000_000) / total_duration_s)
        elif stripped == "progress=end":
            yield 1.0


def run_with_progress(
    args: list[str],
    *,
    total_duration_s: float,
    on_progress: Callable[[float], None] | None = None,
    context: str = "ffmpeg",
) -> None:
    """Run an ffmpeg command that already has `-progress pipe:1` in `args`,
    forwarding fraction updates and emitting interval-based HEARTBEAT lines.
    """
    process = subprocess.Popen(  # noqa: S603
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    assert process.stdout is not None
    start = time.monotonic()
    last_heartbeat = start
    for fraction in parse_progress_lines(process.stdout, total_duration_s):
        if on_progress is not None:
            on_progress(fraction)
        now = time.monotonic()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL_S:
            emit_heartbeat(now - start, context)
            last_heartbeat = now

    returncode = process.wait()
    if returncode != 0:
        stderr = process.stderr.read() if process.stderr else ""
        raise subprocess.CalledProcessError(returncode, args, stderr=stderr)
