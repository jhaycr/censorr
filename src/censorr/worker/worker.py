"""Minimal in-memory worker that runs jobs through the pipeline."""
from __future__ import annotations

from typing import Optional

from censorr.pipeline import RunPipeline
from censorr.worker.queue import InMemoryQueue, JobPayload, JobStatus


class InMemoryWorker:
    def __init__(self, queue: InMemoryQueue, pipeline: Optional[RunPipeline] = None) -> None:
        self.queue = queue
        self.pipeline = pipeline or RunPipeline()

    def _payload_kwargs(self, payload: JobPayload) -> dict:
        return {
            "input_file_path": payload.input_file_path,
            "output_dir": payload.output_dir,
            "include_language": payload.include_language,
            "include_title": payload.include_title,
            "include_any": payload.include_any,
            "exclude_language": payload.exclude_language,
            "exclude_title": payload.exclude_title,
            "exclude_any": payload.exclude_any,
            "config_path": payload.config_path,
            "default_threshold": payload.default_threshold or 85.0,
            "qc_threshold_db": payload.qc_threshold_db,
            "app_config_path": payload.app_config_path,
            "remux_mode": payload.remux_mode,
            "remux_naming_mode": payload.remux_naming_mode,
            "remux_output_base": payload.remux_output_base,
            "cleanup": payload.cleanup,
        }

    def process_next(self) -> bool:
        item = self.queue.dequeue()
        if not item:
            return False

        job_id, payload = item
        try:
            result_path = self.pipeline.run(**self._payload_kwargs(payload))
            self.queue.mark_completed(job_id, result_path)
        except Exception:
            self.queue.mark_failed(job_id)
            raise
        return True

    def run_all(self) -> None:
        while self.process_next():
            continue

    def get_status(self, job_id: str) -> Optional[JobStatus]:
        return self.queue.get_status(job_id)

    def get_result(self, job_id: str) -> Optional[str]:
        return self.queue.get_result(job_id)
