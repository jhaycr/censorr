from unittest.mock import MagicMock

from censorr.worker.queue import InMemoryQueue, JobPayload, JobStatus
from censorr.worker.worker import InMemoryWorker


def test_in_memory_queue_lifecycle():
    queue = InMemoryQueue()
    payload = JobPayload(input_file_path="input", output_dir="out")
    job_id = queue.enqueue(payload)

    assert queue.get_status(job_id) == JobStatus.pending
    popped = queue.dequeue()
    assert popped is not None
    jid, pl = popped
    assert jid == job_id
    assert pl == payload
    assert queue.get_status(job_id) == JobStatus.processing

    queue.mark_completed(job_id, result="/out/final.mkv")
    assert queue.get_status(job_id) == JobStatus.completed
    assert queue.get_result(job_id) == "/out/final.mkv"

    # mark_failed and mark_cancelled should not error even if status already set
    queue.mark_failed(job_id)
    queue.mark_cancelled(job_id)
    assert queue.get_status(job_id) == JobStatus.cancelled


def test_in_memory_worker_processes_job(monkeypatch):
    # Arrange payload and queue
    payload = JobPayload(input_file_path="input.mkv", output_dir="/tmp/out")
    queue = InMemoryQueue()
    job_id = queue.enqueue(payload)

    # Mock pipeline to avoid running actual commands
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = "/tmp/out/final.mkv"

    worker = InMemoryWorker(queue, pipeline=mock_pipeline)

    processed = worker.process_next()
    assert processed is True
    assert queue.get_status(job_id) == JobStatus.completed
    assert queue.get_result(job_id) == "/tmp/out/final.mkv"
    mock_pipeline.run.assert_called_once_with(
        input_file_path="input.mkv",
        output_dir="/tmp/out",
        include_language=None,
        include_title=None,
        include_any=None,
        exclude_language=None,
        exclude_title=None,
        exclude_any=None,
        config_path=None,
        default_threshold=85.0,
        qc_threshold_db=None,
        app_config_path=None,
        remux_mode=None,
        remux_naming_mode="movie",
        remux_output_base=None,
        cleanup=True,
    )

    # No additional jobs left
    assert worker.process_next() is False
