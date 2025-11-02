import json
from pathlib import Path
from unittest import mock

from src.queue.file_queue import FileJobQueue
from src.worker.runner import run_once


def test_worker_processes_job_done_and_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("CENSORR_QUEUE_PATH", str(tmp_path))
    monkeypatch.setenv("CENSORR_QUEUE_MAX_RETRIES", "2")
    q = FileJobQueue.from_env()

    # Enqueue one job that will succeed
    q.enqueue({"tags": {"censorr_preset": "ok"}})
    # Enqueue one job that will fail permanently (exit 3)
    q.enqueue({"tags": {"censorr_preset": "bad"}})

    # Mock CLI invocation: return 0 for first claim, then 3 for second
    calls = []

    def fake_run(payload):
        calls.append(payload)
        if payload["tags"].get("censorr_preset") == "ok":
            return 0
        return 3

    monkeypatch.setattr("src.worker.runner._invoke_cli_with_payload", fake_run)

    # Process both jobs (order-agnostic)
    assert run_once(q) is True
    assert run_once(q) is True
    # Verify one done and one failed
    assert len(list(q.done.glob("*.json"))) == 1
    assert len(list(q.failed.glob("*.json"))) == 1
