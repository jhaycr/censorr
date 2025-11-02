import json
from io import BytesIO
from unittest.mock import patch, Mock

from src.webhook.wsgi_app import app


def make_environ(path="/webhook", method="POST", body=None, content_type="application/json"):
    data = json.dumps(body or {}).encode("utf-8")
    return {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": BytesIO(data),
    }


def run_app(environ):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(app(environ, start_response))
    captured["body"] = body
    return captured


def test_webhook_allowlist_miss_returns_ignored(monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    payload = {
        "source": "radarr",
        "eventType": "Test",
        "tags": {"unrelated": "x"},
        "mediaPaths": ["/tmp/fake.mp4"],
    }
    env = make_environ(body=payload)
    result = run_app(env)
    assert result["status"].startswith("200")
    body = json.loads(result["body"].decode())
    assert body["status"] == "ignored"
    assert body["reason"] in {"allowlist_miss", "missing_or_invalid_tags"}


@patch("src.webhook.wsgi_app.subprocess.run")
def test_webhook_allowlist_hit_and_cli_accepts_returns_202(mock_run, monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    mock_run.return_value = Mock(returncode=0)
    payload = {
        "source": "sonarr",
        "eventType": "Test",
        "tags": {"censorr_profile": "1", "censorr_preset": "movies"},
        "mediaPaths": ["/tmp/fake.mp4"],
    }
    env = make_environ(body=payload)
    result = run_app(env)
    assert result["status"].startswith("202")
    body = json.loads(result["body"].decode())
    assert body["status"] == "accepted"


@patch("src.webhook.wsgi_app.subprocess.run")
def test_webhook_allowlist_hit_and_cli_ignored_returns_200(mock_run, monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    mock_run.return_value = Mock(returncode=2)
    payload = {
        "source": "radarr",
        "eventType": "Test",
        "tags": {"censorr_profile": "1"},  # missing censorr_preset to be ignored by CLI
        "mediaPaths": ["/tmp/fake.mp4"],
    }
    env = make_environ(body=payload)
    result = run_app(env)
    assert result["status"].startswith("200")
    body = json.loads(result["body"].decode())
    assert body["status"] == "ignored"


@patch("src.webhook.wsgi_app.subprocess.run")
def test_webhook_allowlist_hit_and_cli_failed_returns_400(mock_run, monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    mock_run.return_value = Mock(returncode=3)
    payload = {
        "source": "radarr",
        "eventType": "Test",
        "tags": {"censorr_profile": "1", "censorr_preset": "movies"},
        "mediaPaths": ["/tmp/fake.mp4"],
    }
    env = make_environ(body=payload)
    result = run_app(env)
    assert result["status"].startswith("400")
    body = json.loads(result["body"].decode())
    assert body["status"] == "failed"


def test_webhook_malformed_payload_returns_400(monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/webhook",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": "3",
        "wsgi.input": BytesIO(b"{x}"),
    }
    result = run_app(environ)
    assert result["status"].startswith("400")
    body = json.loads(result["body"].decode())
    assert body["status"] == "failed"
    assert body["reason"] == "malformed_json"
