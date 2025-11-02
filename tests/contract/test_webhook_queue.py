import json
from io import BytesIO
from pathlib import Path

from src.webhook.wsgi_app import app


def make_env(payload):
    data = json.dumps(payload).encode()
    return {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/webhook",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": BytesIO(data),
    }


def run(environ):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(app(environ, start_response))
    captured["body"] = body
    return captured


def test_webhook_enqueues_job(tmp_path, monkeypatch):
    # Use a temp queue path
    monkeypatch.setenv("CENSORR_QUEUE_PATH", str(tmp_path))
    # Allowlist hit
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    payload = {
        "source": "sonarr",
        "eventType": "EpisodeImported",
        "tags": {"censorr_profile": "1", "censorr_preset": "tv"},
        "mediaPaths": ["/media/tv/Show/Season 01/E01.mkv"],
    }
    res = run(make_env(payload))
    assert res["status"].startswith("202")
    body = json.loads(res["body"].decode())
    assert body["status"] == "accepted"
    assert "job_id" in body

    # Verify a job file is present in incoming
    inc = Path(tmp_path) / "incoming"
    files = list(inc.glob("*.json"))
    assert len(files) == 1


def test_webhook_allowlist_miss_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("CENSORR_QUEUE_PATH", str(tmp_path))
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    payload = {
        "source": "radarr",
        "eventType": "MovieImported",
        "tags": {"foo": "bar"},
        "mediaPaths": ["/media/movies/Inception.mkv"],
    }
    res = run(make_env(payload))
    assert res["status"].startswith("200")
    body = json.loads(res["body"].decode())
    assert body["status"] == "ignored"
