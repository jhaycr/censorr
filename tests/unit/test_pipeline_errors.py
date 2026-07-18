from censorr.pipeline.errors import (
    CensorrError,
    JobValidationError,
    QCError,
    TransientError,
    exit_code_for,
)


def test_all_taxonomy_members_derive_from_censorr_error() -> None:
    assert issubclass(JobValidationError, CensorrError)
    assert issubclass(QCError, CensorrError)
    assert issubclass(TransientError, CensorrError)


def test_exit_code_contract() -> None:
    assert exit_code_for(JobValidationError("bad input")) == 3
    assert exit_code_for(QCError("failed verification")) == 4
    assert exit_code_for(TransientError("disk full")) == 1


def test_unknown_censorr_error_defaults_to_transient_code() -> None:
    class SomeFutureError(CensorrError):
        pass

    assert exit_code_for(SomeFutureError("x")) == 1
