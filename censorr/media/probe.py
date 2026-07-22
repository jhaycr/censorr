import json
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class StreamInfo(BaseModel):
    index: int
    codec_type: str
    codec_name: str
    language: str | None = None
    title: str | None = None
    disposition: dict[str, bool] = {}
    duration_s: float | None = None
    channels: int | None = None
    bit_rate: int | None = None  # bits/s; None when the container doesn't expose it


class MediaInfo(BaseModel):
    path: Path
    duration_s: float
    streams: list[StreamInfo]
    format_tags: dict[str, str] = {}

    def video_streams(self) -> list[StreamInfo]:
        return [s for s in self.streams if s.codec_type == "video"]

    def audio_streams(self) -> list[StreamInfo]:
        return [s for s in self.streams if s.codec_type == "audio"]

    def subtitle_streams(self) -> list[StreamInfo]:
        return [s for s in self.streams if s.codec_type == "subtitle"]


def probe(path: Path) -> MediaInfo:
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    data = json.loads(result.stdout)
    streams = [_parse_stream(s) for s in data.get("streams", [])]
    duration_s = float(data["format"]["duration"])
    format_tags = data["format"].get("tags", {})
    return MediaInfo(path=path, duration_s=duration_s, streams=streams, format_tags=format_tags)


def _parse_stream(raw: dict[str, Any]) -> StreamInfo:
    tags = raw.get("tags", {})
    disposition = {k: bool(v) for k, v in raw.get("disposition", {}).items()}
    duration = raw.get("duration")
    return StreamInfo(
        index=raw["index"],
        codec_type=raw["codec_type"],
        codec_name=raw.get("codec_name", ""),
        language=tags.get("language"),
        title=tags.get("title"),
        disposition=disposition,
        duration_s=float(duration) if duration is not None else None,
        channels=raw.get("channels"),
        bit_rate=_parse_bitrate(raw, tags),
    )


def _parse_bitrate(raw: dict[str, Any], tags: dict[str, Any]) -> int | None:
    """Stream bit_rate in bits/s. Matroska often omits the stream-level field
    and carries an mkvmerge `BPS` tag instead, so fall back to that."""
    for value in (raw.get("bit_rate"), tags.get("BPS")):
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None
