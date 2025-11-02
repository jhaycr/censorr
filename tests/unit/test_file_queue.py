import json
import os
import time
from pathlib import Path

from src.queue.file_queue import FileJobQueue


def test_enqueue_creates_job_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CENSORR_QUEUE_PATH", str(tmp_path))
    q = FileJobQueue.from_env()
    job_id = q.enqueue({"hello": "world"})
    inc = q.incoming
    files = list(inc.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["id"] == job_id
    assert data["status"] == "incoming"


def test_claim_complete_flow(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CENSORR_QUEUE_PATH", str(tmp_path))
    q = FileJobQueue.from_env()
    q.enqueue({"n": 1})
    job = q.claim("w1")
    assert job is not None
    assert job.data["status"] == "processing"
    q.complete(job, {"exit_code": 0, "reason": "accepted"})
    assert not any(q.processing.glob("*.json"))
    done = list(q.done.glob("*.json"))
    assert len(done) == 1
    data = json.loads(done[0].read_text())
    assert data["status"] == "done"
    assert data["result"]["exit_code"] == 0


def test_fail_retry_and_permanent(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CENSORR_QUEUE_PATH", str(tmp_path))
    monkeypatch.setenv("CENSORR_QUEUE_MAX_RETRIES", "1")
    q = FileJobQueue.from_env()
    q.enqueue({"n": 1})
    # First fail transient -> goes back to incoming
    job = q.claim("w1")
    q.fail(job, {"message": "transient", "kind": "transient"}, retryable=True)
    assert any(q.incoming.glob("*.json"))
    # Claim again and fail permanent -> goes to failed
    job2 = q.claim("w1")
    q.fail(job2, {"message": "nope", "kind": "permanent"}, retryable=False)
    assert not any(q.processing.glob("*.json"))
    assert any(q.failed.glob("*.json"))


def test_recover_stale_requeues(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CENSORR_QUEUE_PATH", str(tmp_path))
    monkeypatch.setenv("CENSORR_QUEUE_LEASE_SECONDS", "1")
    q = FileJobQueue.from_env()
    q.enqueue({"x": 1})
    job = q.claim("w1")
    assert job is not None
    # Force lease to expire by editing file
    p = job.path
    data = json.loads(p.read_text())
    data["lease_expires_at"] = time.time() - 10
    p.write_text(json.dumps(data))
    n = q.recover_stale()
    assert n == 1
    assert any(q.incoming.glob("*.json"))
    assert not any(q.processing.glob("*.json"))
