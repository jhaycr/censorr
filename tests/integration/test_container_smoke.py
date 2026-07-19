"""Container smoke tests (@pytest.mark.docker): image builds, `serve`
healthcheck passes, and a webhook-submitted job produces a clean file on a
bind-mounted tmp tree. Requires a working docker daemon; skipped otherwise.
"""

import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures import build_movie_fixture

pytestmark = pytest.mark.docker

PROJECT_ROOT = Path(__file__).parent.parent.parent
IMAGE = "censorr:smoke"


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "--context", "default", *args], capture_output=True, text=True, check=check
    )


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return docker("info", check=False).returncode == 0


@pytest.fixture(scope="session")
def smoke_image() -> str:
    if not _docker_available():
        pytest.skip("docker daemon not available")
    build = docker("build", "-t", IMAGE, str(PROJECT_ROOT), check=False)
    assert build.returncode == 0, f"image build failed:\n{build.stderr[-2000:]}"
    return IMAGE


def test_image_builds_and_cli_responds(smoke_image: str) -> None:
    result = docker("run", "--rm", smoke_image, "version")

    assert result.stdout.strip()


def test_ffmpeg_present_in_image(smoke_image: str) -> None:
    result = docker("run", "--rm", "--entrypoint", "ffmpeg", smoke_image, "-version")

    assert "ffmpeg version" in result.stdout


def test_serve_healthcheck_and_webhook_e2e(smoke_image: str, tmp_path: Path) -> None:
    """End-to-end: bind-mounted media tree, webhook enqueue via the serve
    container, work container processes the job, clean file appears on the
    host mount."""
    media = tmp_path / "media"
    source = build_movie_fixture(media / "movies", duration=90.0)
    (media / "movies-clean").mkdir()

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "censorr.toml").write_text(
        '[naming]\n'
        'movie_clean_root = "/data/media/movies-clean"\n'
        '[service]\n'
        'queue_path = "/app/queue"\n'
    )
    queue = tmp_path / "queue"
    queue.mkdir()

    common_mounts = [
        "-v", f"{queue}:/app/queue",
        "-v", f"{config_dir}:/app/config:ro",
    ]

    serve_name = "censorr-smoke-serve"
    docker("rm", "-f", serve_name, check=False)
    docker(
        "run", "-d", "--name", serve_name, "-p", "18712:8000", *common_mounts, smoke_image, "serve"
    )
    try:
        deadline = time.monotonic() + 30
        healthy = False
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:18712/healthz", timeout=2) as resp:
                    healthy = resp.status == 200
                    if healthy:
                        break
            except OSError:
                time.sleep(0.5)
        assert healthy, docker("logs", serve_name, check=False).stderr

        payload: dict[str, Any] = {
            "eventType": "Download",
            "movie": {"title": "Test Movie", "year": 2024, "tags": ["censorr"]},
            "movieFile": {"path": "/data/media/movies/Test Movie (2024)/Test Movie (2024).mkv"},
            "isUpgrade": False,
        }
        request = urllib.request.Request(
            "http://127.0.0.1:18712/webhook/radarr",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as resp:  # noqa: S310 -- localhost
            body = json.loads(resp.read())
        assert body["status"] == "queued", body
        job_id = body["job_id"]

        work = docker(
            "run", "--rm",
            *common_mounts,
            "-v", f"{media / 'movies'}:/data/media/movies:ro",
            "-v", f"{media / 'movies-clean'}:/data/media/movies-clean",
            smoke_image, "work", "--once",
            check=False,
        )
        assert work.returncode == 0, work.stderr[-2000:]

        record = json.loads((queue / "records" / f"{job_id}.json").read_text())
        assert record["status"] == "done", record
        assert record["result"]["status"] == "ok", record

        clean_file = (
            media / "movies-clean" / "Test Movie (2024)"
            / "Test Movie (2024) {edition-Censorr}.mkv"
        )
        assert clean_file.is_file()
        assert source.is_file()  # original untouched
    finally:
        docker("rm", "-f", serve_name, check=False)
