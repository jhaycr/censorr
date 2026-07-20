from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from censorr.naming.models import MediaTypeHint


class Job(BaseModel):
    id: str
    source: Path
    preset: str | None = None
    force: bool = False
    media_type_hint: MediaTypeHint | None = None
    is_upgrade: bool = False
    deleted_files: list[Path] = []
    submitted_by: str = "cli"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobStats(BaseModel):
    """Counts and ratios only -- deliberately never the matched words
    themselves, so records/UI/logs stay free of profanity."""

    entries_censored: int = 0
    total_matches: int = 0
    mute_windows: int = 0
    muted_seconds: float = 0.0
    mute_ratio: float = 0.0
    masked_entry_ratio: float = 0.0


class JobResult(BaseModel):
    status: str
    reason: str | None = None
    mode: str
    outputs: list[Path] = []
    stats: JobStats | None = None


class JobErrorInfo(BaseModel):
    kind: str
    message: str
    ffmpeg_tail: str | None = None


class JobRecord(BaseModel):
    """Atomic JSON under service.queue_path/records/<job.id>.json; served by
    GET /jobs/{id} once Step 14 exists. Written on every publish (Step 11)
    or terminal failure so the record survives independent of the workdir.
    """

    job: Job
    status: JobStatus
    result: JobResult | None = None
    stage: str | None = None
    progress: float = 0.0
    fingerprint: str | None = None
    error: JobErrorInfo | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
