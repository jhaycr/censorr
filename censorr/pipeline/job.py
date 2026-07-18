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


class JobResult(BaseModel):
    status: str
    reason: str | None = None
    mode: str
    outputs: list[Path] = []
