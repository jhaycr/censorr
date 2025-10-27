"""Worker process to consume file-based queue jobs and invoke the CLI.

Behavior:
- Periodically recover stale jobs from processing/ when leases expire
- Claim jobs atomically from incoming/ by rename to processing/
- Invoke Typer CLI webhook handler with payload from the job
- On exit_code 0: mark done with result accepted
- On exit_code 2: mark done with result ignored (not an error)
- On exit_code 3: permanent failure -> move to failed
- On any other nonzero: retry up to max_retries, then move to failed
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import subprocess

from src.queue.file_queue import FileJobQueue, ClaimedJob


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _invoke_cli_with_payload(payload: dict) -> int:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "src.cli.main", "webhook"],
            input=json.dumps(payload).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return int(proc.returncode)
    except Exception:
        return 1


def run_once(q: FileJobQueue) -> bool:
    """Run a single iteration: recover stale and try to process one job.

    Returns True if a job was processed (done/failed/requeued), else False.
    """
    q.recover_stale()
    job = q.claim(_worker_id())
    if not job:
        return False
    payload = job.data.get("payload", {})
    exit_code = _invoke_cli_with_payload(payload)

    if exit_code == 0:
        q.complete(job, {"exit_code": 0, "reason": "accepted"})
    elif exit_code == 2:
        # Not an error; job considered complete
        q.complete(job, {"exit_code": 2, "reason": "ignored"})
    elif exit_code == 3:
        # Permanent failure (validation), do not retry
        q.fail(job, {"message": "cli_failed_validation", "kind": "permanent", "exit_code": 3}, retryable=False)
    else:
        # Transient error: retry
        q.fail(job, {"message": "cli_error", "kind": "transient", "exit_code": exit_code}, retryable=True)
    return True


def main() -> None:
    q = FileJobQueue.from_env()
    poll = float(os.getenv("CENSORR_WORKER_POLL_INTERVAL", "2"))
    while True:
        did = run_once(q)
        if not did:
            time.sleep(poll)


if __name__ == "__main__":
    main()
