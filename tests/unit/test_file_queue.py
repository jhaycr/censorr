import json
import time
from pathlib import Path
from uuid import uuid4

from censorr.pipeline.job import Job
from censorr.queue.file_queue import FileJobQueue


def make_job(source: str = "/media/movie.mkv") -> Job:
    return Job(id=str(uuid4()), source=Path(source), submitted_by="test")


def make_queue(tmp_path: Path, **kwargs: int) -> FileJobQueue:
    return FileJobQueue(tmp_path / "queue", **kwargs)


class TestEnqueueAndClaim:
    def test_enqueue_lands_in_incoming(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)

        job_id = queue.enqueue(make_job())

        files = list(queue.incoming.glob("*.json"))
        assert len(files) == 1
        assert job_id in files[0].name

    def test_claim_moves_to_processing_with_lease(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        queue.enqueue(make_job())

        claimed = queue.claim("worker-1")

        assert claimed is not None
        assert claimed.entry.status == "processing"
        assert claimed.entry.worker_id == "worker-1"
        assert claimed.entry.lease_expires_at is not None
        assert claimed.entry.lease_expires_at > time.time()
        assert list(queue.incoming.glob("*.json")) == []
        assert len(list(queue.processing.glob("*.json"))) == 1

    def test_claim_on_empty_queue_returns_none(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)

        assert queue.claim("worker-1") is None

    def test_second_claim_gets_nothing_for_single_job(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        queue.enqueue(make_job())

        first = queue.claim("worker-1")
        second = queue.claim("worker-2")

        assert first is not None
        assert second is None

    def test_fifo_ordering(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        first_job = make_job("/media/a.mkv")
        queue.enqueue(first_job)
        time.sleep(1.1)  # filename timestamps have 1s resolution
        queue.enqueue(make_job("/media/b.mkv"))

        claimed = queue.claim("worker-1")

        assert claimed is not None
        assert claimed.entry.job.source == Path("/media/a.mkv")


class TestSameSourceDedup:
    def test_still_queued_job_for_same_source_replaced(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        first_id = queue.enqueue(make_job("/media/movie.mkv"))
        second_id = queue.enqueue(make_job("/media/movie.mkv"))

        files = list(queue.incoming.glob("*.json"))
        assert len(files) == 1
        assert second_id in files[0].name
        assert first_id not in files[0].name

    def test_different_sources_both_kept(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        queue.enqueue(make_job("/media/a.mkv"))
        queue.enqueue(make_job("/media/b.mkv"))

        assert len(list(queue.incoming.glob("*.json"))) == 2

    def test_claimed_job_not_deduped(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        queue.enqueue(make_job("/media/movie.mkv"))
        claimed = queue.claim("worker-1")
        assert claimed is not None

        queue.enqueue(make_job("/media/movie.mkv"))

        # In-flight job untouched; new job queued alongside.
        assert len(list(queue.processing.glob("*.json"))) == 1
        assert len(list(queue.incoming.glob("*.json"))) == 1


class TestCompleteAndFail:
    def test_complete_moves_to_done(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        queue.enqueue(make_job())
        claimed = queue.claim("worker-1")
        assert claimed is not None

        queue.complete(claimed, {"status": "ok"})

        done_files = list(queue.done.glob("*.json"))
        assert len(done_files) == 1
        data = json.loads(done_files[0].read_text())
        assert data["status"] == "done"
        assert data["result"] == {"status": "ok"}

    def test_retryable_failure_requeues_with_incremented_retries(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        queue.enqueue(make_job())
        claimed = queue.claim("worker-1")
        assert claimed is not None

        queue.fail(claimed, {"kind": "TransientError", "message": "disk full"}, retryable=True)

        incoming = list(queue.incoming.glob("*.json"))
        assert len(incoming) == 1
        data = json.loads(incoming[0].read_text())
        assert data["retries"] == 1
        assert data["status"] == "incoming"
        assert data["worker_id"] == ""

    def test_non_retryable_failure_goes_to_failed(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        queue.enqueue(make_job())
        claimed = queue.claim("worker-1")
        assert claimed is not None

        queue.fail(claimed, {"kind": "QCError", "message": "under-mute"}, retryable=False)

        assert len(list(queue.failed.glob("*.json"))) == 1
        assert list(queue.incoming.glob("*.json")) == []

    def test_retry_exhaustion_lands_in_failed(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path, max_retries=2)
        queue.enqueue(make_job())

        for attempt in range(3):  # initial + 2 retries
            claimed = queue.claim("worker-1")
            assert claimed is not None, f"claim failed on attempt {attempt}"
            queue.fail(claimed, {"kind": "TransientError", "message": "boom"}, retryable=True)

        failed = list(queue.failed.glob("*.json"))
        assert len(failed) == 1
        data = json.loads(failed[0].read_text())
        assert data["retries"] == 2
        assert queue.claim("worker-1") is None


class TestLease:
    def test_renew_lease_extends_expiry(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path, lease_seconds=100)
        queue.enqueue(make_job())
        claimed = queue.claim("worker-1")
        assert claimed is not None
        original_expiry = claimed.entry.lease_expires_at
        assert original_expiry is not None

        time.sleep(0.05)
        queue.renew_lease(claimed)

        assert claimed.entry.lease_expires_at is not None
        assert claimed.entry.lease_expires_at > original_expiry

    def test_expired_lease_recovered_to_incoming(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path, lease_seconds=0)  # leases expire immediately
        queue.enqueue(make_job())
        claimed = queue.claim("worker-1")
        assert claimed is not None

        recovered = queue.recover_stale()

        assert recovered == 1
        assert len(list(queue.incoming.glob("*.json"))) == 1
        assert list(queue.processing.glob("*.json")) == []

    def test_live_lease_not_recovered(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path, lease_seconds=3600)
        queue.enqueue(make_job())
        queue.claim("worker-1")

        recovered = queue.recover_stale()

        assert recovered == 0
        assert len(list(queue.processing.glob("*.json"))) == 1

    def test_corrupt_processing_file_moved_to_failed(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        corrupt = queue.processing / "9999999999-corrupt.json"
        corrupt.write_text("this is not json")

        recovered = queue.recover_stale()

        assert recovered == 1
        assert (queue.failed / corrupt.name).is_file()
