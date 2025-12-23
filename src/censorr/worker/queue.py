"""Queue interfaces and an in-memory implementation for worker jobs."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple


class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


@dataclass
class JobPayload:
    input_file_path: str
    output_dir: Optional[str] = None
    include_language: Optional[list[str]] = None
    include_title: Optional[list[str]] = None
    include_any: Optional[list[str]] = None
    exclude_language: Optional[list[str]] = None
    exclude_title: Optional[list[str]] = None
    exclude_any: Optional[list[str]] = None
    config_path: Optional[str] = None
    default_threshold: float | None = None
    qc_threshold_db: float | None = None
    app_config_path: Optional[str] = None
    remux_mode: Optional[str] = None
    remux_naming_mode: Optional[str] = None
    remux_output_base: Optional[str] = None
    cleanup: bool = True
    extras: dict = field(default_factory=dict)


class InMemoryQueue:
    """Lightweight in-memory queue for local/dev use."""

    def __init__(self) -> None:
        self._queue: list[tuple[str, JobPayload]] = []
        self._lock = threading.Lock()
        self._status: Dict[str, JobStatus] = {}
        self._payloads: Dict[str, JobPayload] = {}
        self._results: Dict[str, str] = {}

    def enqueue(self, payload: JobPayload) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._queue.append((job_id, payload))
            self._status[job_id] = JobStatus.pending
            self._payloads[job_id] = payload
        return job_id

    def dequeue(self) -> Optional[Tuple[str, JobPayload]]:
        with self._lock:
            if not self._queue:
                return None
            job_id, payload = self._queue.pop(0)
            self._status[job_id] = JobStatus.processing
            return job_id, payload

    def mark_completed(self, job_id: str, result: Optional[str] = None) -> None:
        with self._lock:
            if job_id in self._status:
                self._status[job_id] = JobStatus.completed
                if result is not None:
                    self._results[job_id] = result

    def mark_failed(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._status:
                self._status[job_id] = JobStatus.failed

    def mark_cancelled(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._status:
                self._status[job_id] = JobStatus.cancelled

    def get_status(self, job_id: str) -> Optional[JobStatus]:
        with self._lock:
            return self._status.get(job_id)

    def get_payload(self, job_id: str) -> Optional[JobPayload]:
        with self._lock:
            return self._payloads.get(job_id)

    def get_result(self, job_id: str) -> Optional[str]:
        with self._lock:
            return self._results.get(job_id)
