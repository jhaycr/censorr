"""Utility helpers for timestamped console logging (lightweight, no external deps)."""
from __future__ import annotations
import sys
from datetime import datetime, timezone
from typing import Any

ISO_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"

def ts() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FMT)

def tprint(*args: Any, prefix: str | None = None, file = sys.stdout, flush: bool = True, **kwargs):
    """Print with an RFC3339/ISO-8601 UTC timestamp prefix.
    Args:
        *args: message parts
        prefix: optional static prefix like an operation name
        file: stream
        flush: flush output (default True for real-time tailing)
    """
    if prefix:
        print(f"[{ts()}] [{prefix}]", *args, file=file, **kwargs)
    else:
        print(f"[{ts()}]", *args, file=file, **kwargs)
    if flush:
        try:
            file.flush()
        except Exception:
            pass
