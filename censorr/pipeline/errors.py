class CensorrError(Exception):
    """Base for all censorr exceptions (design §6)."""


class JobValidationError(CensorrError):
    """Bad input/config/payload; output==source invariant; shallow path.
    Deterministic. Exit 3, queue: failed, no retry.
    """


class QCError(CensorrError):
    """Output failed verification (R14). Deterministic. Exit 4, queue:
    failed, no retry (workdir retained for inspection).
    """


class TransientError(CensorrError):
    """I/O, FFmpeg crash, disk full, source changed mid-job. Exit 1, queue:
    retried up to max_retries, then failed.
    """


def exit_code_for(exc: CensorrError) -> int:
    if isinstance(exc, QCError):
        return 4
    if isinstance(exc, JobValidationError):
        return 3
    return 1
