"""Crash-safe file-based job queue (v1's proven design + R9 additions).

Jobs move atomically through incoming/ -> processing/ -> done/ | failed/
by os.replace renames, so exactly one worker can claim a job and a
container crash never loses one. R9 additions over v1: same-source dedup
on enqueue (a still-queued job for the same source is replaced) and a
lease-renewal API (the worker's progress callback keeps long re-encodes
from being reclaimed by a second worker).
"""

import os
import time
import uuid
from pathlib import Path

from pydantic import BaseModel

from censorr.pipeline.job import Job


class QueueEntry(BaseModel):
    id: str
    created_at: float
    updated_at: float
    retries: int = 0
    max_retries: int
    status: str
    job: Job
    worker_id: str = ""
    lease_expires_at: float | None = None
    error: dict[str, str] | None = None
    result: dict[str, str] | None = None


class ClaimedJob(BaseModel):
    id: str
    path: Path
    entry: QueueEntry


def _write_atomic(path: Path, entry: QueueEntry) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(entry.model_dump_json())
    os.replace(tmp, path)


class FileJobQueue:
    def __init__(self, base: Path, *, max_retries: int = 3, lease_seconds: int = 1800) -> None:
        self.base = base
        self.incoming = base / "incoming"
        self.processing = base / "processing"
        self.done = base / "done"
        self.failed = base / "failed"
        self.max_retries = max_retries
        self.lease_seconds = lease_seconds
        for directory in (self.incoming, self.processing, self.done, self.failed):
            directory.mkdir(parents=True, exist_ok=True)

    def _list_sorted(self, directory: Path) -> list[Path]:
        files = [p for p in directory.iterdir() if p.is_file() and p.suffix == ".json"]
        files.sort()  # filenames lead with a timestamp, so this is FIFO-ish
        return files

    def _read(self, path: Path) -> QueueEntry:
        return QueueEntry.model_validate_json(path.read_text())

    def enqueue(self, job: Job) -> str:
        """R9 same-source dedup: replaces any still-queued (unclaimed) job
        for the same resolved source path. In-flight jobs are untouched --
        the pre-publish source re-stat handles those."""
        for existing_path in self._list_sorted(self.incoming):
            try:
                existing = self._read(existing_path)
            except ValueError:
                continue
            if existing.job.source == job.source:
                existing_path.unlink(missing_ok=True)

        now = time.time()
        entry = QueueEntry(
            id=job.id or str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            max_retries=self.max_retries,
            status="incoming",
            job=job,
        )
        path = self.incoming / f"{int(now)}-{entry.id}.json"
        _write_atomic(path, entry)
        return entry.id

    def claim(self, worker_id: str) -> ClaimedJob | None:
        for src in self._list_sorted(self.incoming):
            dst = self.processing / src.name
            try:
                os.replace(src, dst)  # atomic; exactly one worker wins
            except (FileNotFoundError, PermissionError):
                continue
            entry = self._read(dst)
            entry.status = "processing"
            entry.updated_at = time.time()
            entry.worker_id = worker_id
            entry.lease_expires_at = time.time() + self.lease_seconds
            _write_atomic(dst, entry)
            return ClaimedJob(id=entry.id, path=dst, entry=entry)
        return None

    def renew_lease(self, claimed: ClaimedJob) -> None:
        """R9: called from the worker's progress callback so a long
        re-encode is never reclaimed mid-run."""
        claimed.entry.lease_expires_at = time.time() + self.lease_seconds
        claimed.entry.updated_at = time.time()
        _write_atomic(claimed.path, claimed.entry)

    def complete(self, claimed: ClaimedJob, result: dict[str, str]) -> None:
        claimed.entry.status = "done"
        claimed.entry.updated_at = time.time()
        claimed.entry.result = result
        _write_atomic(claimed.path, claimed.entry)
        os.replace(claimed.path, self.done / claimed.path.name)

    def fail(self, claimed: ClaimedJob, error: dict[str, str], *, retryable: bool) -> None:
        claimed.entry.updated_at = time.time()
        claimed.entry.error = error
        if retryable and claimed.entry.retries < claimed.entry.max_retries:
            claimed.entry.retries += 1
            claimed.entry.status = "incoming"
            claimed.entry.worker_id = ""
            claimed.entry.lease_expires_at = None
            _write_atomic(claimed.path, claimed.entry)
            os.replace(claimed.path, self.incoming / claimed.path.name)
        else:
            claimed.entry.status = "failed"
            _write_atomic(claimed.path, claimed.entry)
            os.replace(claimed.path, self.failed / claimed.path.name)

    def recover_stale(self) -> int:
        """Requeue processing jobs whose lease expired (worker crashed);
        corrupt files land in failed/. Returns the number touched."""
        now = time.time()
        recovered = 0
        for path in self._list_sorted(self.processing):
            try:
                entry = self._read(path)
            except ValueError:
                os.replace(path, self.failed / path.name)
                recovered += 1
                continue
            if entry.lease_expires_at is None or entry.lease_expires_at <= now:
                entry.status = "incoming"
                entry.worker_id = ""
                entry.lease_expires_at = None
                entry.updated_at = now
                _write_atomic(path, entry)
                os.replace(path, self.incoming / path.name)
                recovered += 1
        return recovered
