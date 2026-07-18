import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request

from censorr import __version__
from censorr.config.schema import ResolvedConfig
from censorr.pipeline.job import Job
from censorr.queue.file_queue import FileJobQueue
from censorr.service.arr_models import JobSubmission
from censorr.service.logging import log_event

router = APIRouter()


@router.post("/jobs", status_code=202)
def submit_job(submission: JobSubmission, request: Request) -> dict[str, str]:
    queue: FileJobQueue = request.app.state.queue
    job = Job(
        id=str(uuid4()),
        source=Path(submission.path),
        preset=submission.preset,
        force=submission.force,
        submitted_by="api",
    )
    job_id = queue.enqueue(job)
    log_event("job_enqueued", job_id=job_id, source=submission.path, preset=submission.preset)
    return {"status": "queued", "job_id": job_id}


def _load_records(cfg: ResolvedConfig) -> list[dict[str, object]]:
    records_dir = cfg.service.queue_path / "records"
    if not records_dir.is_dir():
        return []
    records = []
    for path in records_dir.glob("*.json"):
        try:
            records.append(json.loads(path.read_text()))
        except (ValueError, OSError):
            continue
    records.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return records


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, object]:
    cfg: ResolvedConfig = request.app.state.cfg
    record_path = cfg.service.queue_path / "records" / f"{job_id}.json"
    if not record_path.is_file():
        raise HTTPException(status_code=404, detail="job not found")
    return json.loads(record_path.read_text())  # type: ignore[no-any-return]


@router.get("/jobs")
def list_jobs(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, object]]:
    cfg: ResolvedConfig = request.app.state.cfg
    records = _load_records(cfg)
    if status is not None:
        records = [r for r in records if r.get("status") == status]
    return records[:limit]


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status")
def status_endpoint(request: Request) -> dict[str, object]:
    queue: FileJobQueue = request.app.state.queue
    return {
        "version": __version__,
        "queue_depth": len(list(queue.incoming.glob("*.json"))),
        "processing": len(list(queue.processing.glob("*.json"))),
        "done": len(list(queue.done.glob("*.json"))),
        "failed": len(list(queue.failed.glob("*.json"))),
    }
