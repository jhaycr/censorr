import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest

from censorr.config.schema import ResolvedConfig
from censorr.pipeline.context import PipelineContext
from censorr.pipeline.job import Job
from censorr.queue.file_queue import FileJobQueue
from censorr.service.worker import Worker
from tests.fixtures import build_movie_fixture

pytestmark = pytest.mark.ffmpeg


def make_cfg(tmp_path: Path) -> ResolvedConfig:
    return ResolvedConfig(service={"queue_path": str(tmp_path / "queue")})


def enqueue(cfg: ResolvedConfig, source: Path, **job_kwargs: object) -> str:
    queue = FileJobQueue(cfg.service.queue_path)
    job = Job(id=str(uuid4()), source=source, submitted_by="test", **job_kwargs)  # type: ignore[arg-type]
    return queue.enqueue(job)


def read_record(cfg: ResolvedConfig, job_id: str) -> dict:
    return json.loads((cfg.service.queue_path / "records" / f"{job_id}.json").read_text())


def test_worker_processes_job_end_to_end(tmp_path: Path) -> None:
    cfg = make_cfg(tmp_path)
    source = build_movie_fixture(tmp_path / "src", duration=90.0)
    job_id = enqueue(cfg, source)

    worker = Worker(cfg, worker_id="test-worker")
    claimed = worker.run_once()

    assert claimed is True
    done_files = list((cfg.service.queue_path / "done").glob("*.json"))
    assert len(done_files) == 1
    entry = json.loads(done_files[0].read_text())
    assert entry["result"] == {"status": "ok"}

    record = read_record(cfg, job_id)
    assert record["status"] == "done"
    assert record["progress"] == 1.0
    assert record["result"]["status"] == "ok"

    # Censoring stats: counts/ratios only -- never the matched words.
    stats = record["result"]["stats"]
    assert stats["entries_censored"] == 2  # the movie fixture's two profane entries
    assert stats["total_matches"] == 2
    assert stats["mute_windows"] == 2
    assert stats["muted_seconds"] > 0
    assert "word" not in json.dumps(stats).lower()

    output = (
        tmp_path / "src-clean" / "Test Movie (2024)"
        / "Test Movie (2024) {edition-Censorr}.mkv"
    )
    assert output.is_file()
    # Workdir cleaned on success (R11).
    assert not (cfg.service.queue_path / "workdirs" / job_id).exists()


def test_worker_skips_fingerprint_fresh_job(tmp_path: Path) -> None:
    cfg = make_cfg(tmp_path)
    source = build_movie_fixture(tmp_path / "src", duration=90.0)

    enqueue(cfg, source)
    worker = Worker(cfg, worker_id="test-worker")
    assert worker.run_once() is True

    second_id = enqueue(cfg, source)
    assert worker.run_once() is True

    record = read_record(cfg, second_id)
    assert record["result"]["status"] == "skipped"
    assert record["result"]["reason"] == "fingerprint_match"


def test_worker_completes_missing_source_as_ignored(tmp_path: Path) -> None:
    cfg = make_cfg(tmp_path)
    job_id = enqueue(cfg, tmp_path / "does-not-exist.mkv")

    worker = Worker(cfg, worker_id="test-worker")
    assert worker.run_once() is True

    record = read_record(cfg, job_id)
    assert record["result"]["status"] == "ignored"
    assert record["result"]["reason"] == "missing_source"


def test_mid_job_source_swap_fails_transient_then_succeeds_on_retry(tmp_path: Path) -> None:
    cfg = make_cfg(tmp_path)
    source = build_movie_fixture(tmp_path / "src", duration=90.0)
    job_id = enqueue(cfg, source)

    def swap_source_after_verify(stage_name: str, ctx: PipelineContext) -> None:
        if stage_name == "verify":
            # Simulate an Arr upgrade landing mid-job: same path, new content.
            stat = source.stat()
            os.utime(source, (stat.st_atime, stat.st_mtime + 100))

    sabotaged_worker = Worker(cfg, worker_id="test-worker", on_stage=swap_source_after_verify)
    assert sabotaged_worker.run_once() is True

    # Failed transient -> requeued with retries=1, record shows the failure.
    incoming = list((cfg.service.queue_path / "incoming").glob("*.json"))
    assert len(incoming) == 1
    assert json.loads(incoming[0].read_text())["retries"] == 1
    record = read_record(cfg, job_id)
    assert record["status"] == "failed"
    assert record["error"]["kind"] == "TransientError"

    # No partial file in the library.
    output = (
        tmp_path / "src-clean" / "Test Movie (2024)"
        / "Test Movie (2024) {edition-Censorr}.mkv"
    )
    assert not output.exists()

    # Retry with an honest worker: sees the new mtime, succeeds.
    honest_worker = Worker(cfg, worker_id="test-worker-2")
    assert honest_worker.run_once() is True

    record = read_record(cfg, job_id)
    assert record["status"] == "done"
    assert record["result"]["status"] == "ok"
    assert output.is_file()


def test_run_once_returns_false_on_empty_queue(tmp_path: Path) -> None:
    cfg = make_cfg(tmp_path)

    worker = Worker(cfg, worker_id="test-worker")

    assert worker.run_once() is False


def test_worker_gc_recovers_stale_processing_jobs(tmp_path: Path) -> None:
    cfg = ResolvedConfig(service={"queue_path": str(tmp_path / "queue"), "lease_seconds": 0})
    source = build_movie_fixture(tmp_path / "src", duration=90.0)
    enqueue(cfg, source)

    # A "crashed worker" claimed the job but never finished; lease expires
    # immediately (lease_seconds=0).
    crashed_queue = FileJobQueue(cfg.service.queue_path, lease_seconds=0)
    assert crashed_queue.claim("crashed-worker") is not None
    time.sleep(0.01)

    # A fresh worker's startup GC recovers it, then the claim processes it.
    worker = Worker(cfg, worker_id="fresh-worker")
    assert worker.run_once() is True

    done_files = list((cfg.service.queue_path / "done").glob("*.json"))
    assert len(done_files) == 1


def test_directory_job_expands_into_backfill(tmp_path: Path) -> None:
    cfg = make_cfg(tmp_path)
    root = tmp_path / "library"
    build_movie_fixture(root / "a", duration=90.0)
    build_movie_fixture(root / "b", duration=90.0)
    worker = Worker(cfg, worker_id="test-worker")

    # Process movie "a" first so it's fingerprint-fresh for the backfill.
    a_source = root / "a" / "Test Movie (2024)" / "Test Movie (2024).mkv"
    enqueue(cfg, a_source)
    assert worker.run_once() is True

    # Submit the whole library root as one directory job.
    backfill_id = enqueue(cfg, root)
    assert worker.run_once() is True

    record = read_record(cfg, backfill_id)
    assert record["status"] == "done"
    assert record["result"]["mode"] == "backfill"
    assert record["result"]["reason"] == "backfill: 1 queued, 1 already clean"

    # Exactly one child job (movie "b") was enqueued; running it publishes b.
    assert worker.run_once() is True
    b_output = (
        root / "b-clean" / "Test Movie (2024)" / "Test Movie (2024) {edition-Censorr}.mkv"
    )
    assert b_output.is_file()
    assert worker.run_once() is False  # queue drained
