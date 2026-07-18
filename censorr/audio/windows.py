import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from censorr.detect.matcher import Match
from censorr.subtitles.io import SubtitleEntry


class MuteWindow(BaseModel):
    start_s: float
    end_s: float
    source: str
    reason: str


class AudioSettings(BaseModel):
    buffer_s: float = 0.2


class MuteWindowProvider(Protocol):
    """R15 seam: a pure function of entries/matches/source/settings -> windows.
    Post-MVP word-alignment providers narrow windows toward the word but never
    below word boundaries + buffer (Q13) -- under-muting is never acceptable.
    """

    def windows(
        self,
        entries: list[SubtitleEntry],
        matches: dict[int, list[Match]],
        source: Path,
        settings: AudioSettings,
    ) -> list[MuteWindow]: ...


def merge_windows(windows: list[MuteWindow]) -> list[MuteWindow]:
    """Merge overlapping or touching windows. Deterministic: sorted by
    (start_s, end_s) before merging, so provider call order never affects
    the result (N4)."""
    if not windows:
        return []
    ordered = sorted(windows, key=lambda w: (w.start_s, w.end_s))
    merged = [ordered[0]]
    for window in ordered[1:]:
        last = merged[-1]
        if window.start_s <= last.end_s:
            reason = (
                last.reason
                if last.reason == window.reason
                else f"{last.reason}+{window.reason}"
            )
            merged[-1] = MuteWindow(
                start_s=last.start_s,
                end_s=max(last.end_s, window.end_s),
                source=last.source,
                reason=reason,
            )
        else:
            merged.append(window)
    return merged


class EntrySpanProvider:
    """MVP provider (R2): the full subtitle-entry span plus buffer_s on each
    side. Never trims -- a single-word, single-line strong-profanity entry
    still gets the whole entry span + both buffers.
    """

    def windows(
        self,
        entries: list[SubtitleEntry],
        matches: dict[int, list[Match]],
        source: Path,
        settings: AudioSettings,
    ) -> list[MuteWindow]:
        raw = [
            MuteWindow(
                start_s=max(0.0, entry.start_s - settings.buffer_s),
                end_s=entry.end_s + settings.buffer_s,
                source="entry_span",
                reason="matched_entry",
            )
            for entry in entries
            if matches.get(entry.index)
        ]
        return merge_windows(raw)


class ExternalFileProvider:
    """--mute-windows JSON: a list of {"start_s", "end_s"} objects, trusted
    as-authored and merged in verbatim (no buffer applied)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def windows(
        self,
        entries: list[SubtitleEntry],
        matches: dict[int, list[Match]],
        source: Path,
        settings: AudioSettings,
    ) -> list[MuteWindow]:
        data = json.loads(self._path.read_text())
        raw = [
            MuteWindow(
                start_s=float(item["start_s"]),
                end_s=float(item["end_s"]),
                source="external",
                reason="external_file",
            )
            for item in data
        ]
        return merge_windows(raw)
