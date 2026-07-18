from pathlib import Path

import pytest
from typer.testing import CliRunner

from censorr import __version__
from censorr.cli.main import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_inspect_missing_file_fails() -> None:
    result = runner.invoke(app, ["inspect", "/does/not/exist.mkv"])

    assert result.exit_code != 0


def test_process_without_dry_run_not_implemented(tmp_path: Path) -> None:
    fake_file = tmp_path / "movie.mkv"
    fake_file.write_bytes(b"not real media")

    result = runner.invoke(app, ["process", str(fake_file)])

    assert result.exit_code == 1


@pytest.mark.ffmpeg
def test_inspect_happy_path(movie_fixture: Path) -> None:
    result = runner.invoke(app, ["inspect", str(movie_fixture)])

    assert result.exit_code == 0
    assert "Planned output" in result.stdout


@pytest.mark.ffmpeg
def test_process_dry_run_happy_path(movie_fixture: Path) -> None:
    result = runner.invoke(app, ["process", str(movie_fixture), "--dry-run"])

    assert result.exit_code == 0
    assert "Planned output" in result.stdout
