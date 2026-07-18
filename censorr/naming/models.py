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


class JobValidationError(Exception):
    """Deterministic bad input/config error (design §6). Defined here because
    naming/plex.py's output!=source invariant needs it before pipeline/errors.py
    exists (Step 8); Step 8 folds this into the full CensorrError taxonomy.
    """
