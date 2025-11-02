"""File-based job queue for Censorr.

Design goals:
- Minimal dependencies, safe across container crashes and multiple workers
- Producers write jobs into incoming/ atomically
- Workers claim by atomic rename incoming/ -> processing/
- On success, move to done/ with result metadata
- On permanent failure, move to failed/ with error metadata
- Retries for transient failures, bounded by max_retries
- Crash recovery: requeue stale items in processing/ whose lease expired

Directory layout (under base path, default /app/queue):
- incoming/
- processing/
- done/
- failed/

Job file format (JSON):
{
  "id": "<uuid>",
  "created_at": <unix_ts>,
  "updated_at": <unix_ts>,
  "retries": 0,
  "max_retries": 3,
  "status": "incoming|processing|done|failed",
  "payload": {...},
  "worker_id": "",  # set when claimed
  "lease_expires_at": <unix_ts|null>,
  "result": {"exit_code": int, "reason": str}|null,
  "error": {"message": str, "kind": str}|null
}
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _now() -> float:
    return time.time()


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)  # atomic on same filesystem


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


@dataclass
class ClaimedJob:
    id: str
    path: Path  # path in processing/
    data: Dict[str, Any]


class FileJobQueue:
    def __init__(self, base: Path, max_retries: int = 3, lease_seconds: int = 1800):
        self.base = base
        self.incoming = self.base / "incoming"
        self.processing = self.base / "processing"
        self.done = self.base / "done"
        self.failed = self.base / "failed"
        self.max_retries = max_retries
        self.lease_seconds = lease_seconds
        for d in (self.incoming, self.processing, self.done, self.failed):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "FileJobQueue":
        base = Path(os.getenv("CENSORR_QUEUE_PATH", "/app/queue")).resolve()
        max_retries = int(os.getenv("CENSORR_QUEUE_MAX_RETRIES", "3"))
        lease_seconds = int(os.getenv("CENSORR_QUEUE_LEASE_SECONDS", "1800"))
        return cls(base, max_retries=max_retries, lease_seconds=lease_seconds)

    def enqueue(self, payload: Dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        now = _now()
        data: Dict[str, Any] = {
            "id": job_id,
            "created_at": now,
            "updated_at": now,
            "retries": 0,
            "max_retries": self.max_retries,
            "status": "incoming",
            "payload": payload,
            "worker_id": "",
            "lease_expires_at": None,
            "result": None,
            "error": None,
        }
        # Filename embeds timestamp for rough ordering; uniqueness ensured by UUID
        filename = f"{int(now)}-{job_id}.json"
        path = self.incoming / filename
        _write_json_atomic(path, data)
        return job_id

    def _list_sorted(self, directory: Path) -> Tuple[Path, ...]:
        files = [p for p in directory.iterdir() if p.is_file() and p.suffix == ".json"]
        files.sort()  # lexicographic sort respects leading timestamp
        return tuple(files)

    def claim(self, worker_id: str) -> Optional[ClaimedJob]:
        # Try to claim by atomic rename incoming -> processing
        for src in self._list_sorted(self.incoming):
            dst = self.processing / src.name
            try:
                os.replace(src, dst)  # atomic; only one worker succeeds
            except FileNotFoundError:
                continue
            except PermissionError:
                # Could be another process manipulating; skip
                continue
            # Update job metadata in processing file
            data = _read_json(dst)
            data["status"] = "processing"
            data["updated_at"] = _now()
            data["worker_id"] = worker_id
            data["lease_expires_at"] = _now() + self.lease_seconds
            _write_json_atomic(dst, data)
            return ClaimedJob(id=data["id"], path=dst, data=data)
        return None

    def complete(self, job: ClaimedJob, result: Dict[str, Any]) -> None:
        data = job.data
        data["status"] = "done"
        data["updated_at"] = _now()
        data["result"] = result
        _write_json_atomic(job.path, data)
        os.replace(job.path, self.done / job.path.name)

    def fail(self, job: ClaimedJob, error: Dict[str, Any], retryable: bool) -> None:
        data = job.data
        data["updated_at"] = _now()
        data["error"] = error
        data["result"] = None

        if retryable and int(data.get("retries", 0)) < int(data.get("max_retries", self.max_retries)):
            data["retries"] = int(data.get("retries", 0)) + 1
            data["status"] = "incoming"
            data["worker_id"] = ""
            data["lease_expires_at"] = None
            # Write back to processing then move back to incoming for retry
            _write_json_atomic(job.path, data)
            os.replace(job.path, self.incoming / job.path.name)
        else:
            data["status"] = "failed"
            _write_json_atomic(job.path, data)
            os.replace(job.path, self.failed / job.path.name)

    def recover_stale(self) -> int:
        """Requeue stale processing jobs whose lease has expired.

        Returns number of recovered jobs.
        """
        now = _now()
        recovered = 0
        for p in self._list_sorted(self.processing):
            try:
                data = _read_json(p)
            except Exception:
                # Corrupt file; move to failed
                os.replace(p, (self.failed / p.name))
                recovered += 1
                continue
            lease = data.get("lease_expires_at")
            if lease is None or lease <= now:
                # Requeue
                data["status"] = "incoming"
                data["worker_id"] = ""
                data["lease_expires_at"] = None
                data["updated_at"] = now
                _write_json_atomic(p, data)
                os.replace(p, self.incoming / p.name)
                recovered += 1
        return recovered
