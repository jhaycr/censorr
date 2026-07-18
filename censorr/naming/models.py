from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel


class MediaType(StrEnum):
    MOVIE = "movie"
    EPISODE = "episode"


class MediaTypeHint(StrEnum):
    """Authoritative media-type signal from an Arr webhook payload."""

    MOVIE = "movie"
    EPISODE = "episode"


class NamingPlan(BaseModel):
    video_path: Path
    sidecar_paths: list[Path] = []
    edition_tag_applied: str | None = None
    track_titles: dict[str, str] = {}
