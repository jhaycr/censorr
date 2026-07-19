"""Failure-injection tests for publish's cross-filesystem move -- a
destination I/O error (e.g. a flaky network mount) must surface as a
TransientError the queue can retry, never a raw traceback."""

import errno
import os
from pathlib import Path

import pytest

from censorr.pipeline import stages
from censorr.pipeline.errors import TransientError
from censorr.pipeline.stages import _atomic_move


def test_same_filesystem_rename(tmp_path: Path) -> None:
    source = tmp_path / "output.mkv"
    source.write_bytes(b"payload")
    dest = tmp_path / "final" / "output.mkv"

    _atomic_move(source, dest)

    assert dest.read_bytes() == b"payload"
    assert not source.exists()


def test_cross_filesystem_copy_verify_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "output.mkv"
    source.write_bytes(b"payload")
    dest = tmp_path / "final" / "output.mkv"

    real_replace = os.replace
    calls = {"n": 0}

    def fake_replace(src: object, dst: object) -> None:
        calls["n"] += 1
        if calls["n"] == 1:  # first call: pretend dest is another filesystem
            raise OSError(errno.EXDEV, "cross-device link")
        real_replace(src, dst)

    monkeypatch.setattr(stages.os, "replace", fake_replace)

    _atomic_move(source, dest)

    assert dest.read_bytes() == b"payload"
    assert not source.exists()
    assert not dest.with_name(dest.name + ".part").exists()


def test_copy_io_error_raises_transient_and_cleans_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "output.mkv"
    source.write_bytes(b"payload")
    dest = tmp_path / "final" / "output.mkv"

    def exdev_replace(src: object, dst: object) -> None:
        raise OSError(errno.EXDEV, "cross-device link")

    def failing_copy(src: object, dst: object) -> None:
        Path(str(dst)).write_bytes(b"partial")  # simulate a partial write...
        raise OSError(errno.EIO, "I/O error")  # ...then the mount hiccups

    monkeypatch.setattr(stages.os, "replace", exdev_replace)
    monkeypatch.setattr(stages.shutil, "copy2", failing_copy)

    with pytest.raises(TransientError, match="failed to copy"):
        _atomic_move(source, dest)

    assert source.exists()  # temp output retained for the retry
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()  # partial cleaned


def test_non_exdev_replace_error_is_transient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "output.mkv"
    source.write_bytes(b"payload")
    dest = tmp_path / "final" / "output.mkv"

    def eio_replace(src: object, dst: object) -> None:
        raise OSError(errno.EIO, "I/O error")

    monkeypatch.setattr(stages.os, "replace", eio_replace)

    with pytest.raises(TransientError, match="failed to move"):
        _atomic_move(source, dest)

    assert source.exists()
