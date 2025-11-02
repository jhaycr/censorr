import json
from io import BytesIO
from pathlib import Path

from src.webhook.wsgi_app import app


def _run_app(environ):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(app(environ, start_response))
    captured["body"] = body
    return captured


def _make_environ(body):
    payload = json.dumps(body).encode("utf-8")
    return {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/webhook",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(payload)),
        "wsgi.input": BytesIO(payload),
    }


def test_webhook_returns_503_when_globally_disabled(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"webhooks_enabled": False}))
    monkeypatch.setenv("CENSORR_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CENSORR_WEBHOOK_ENABLED", "0")

    environ = _make_environ({"source": "sonarr", "tags": {}})
    result = _run_app(environ)

    assert result["status"].startswith("503")
    body = json.loads(result["body"].decode())
    assert body == {"status": "disabled", "reason": "webhook_disabled"}


def test_webhook_ignores_when_preset_unknown(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "webhooks_enabled": True,
        "presets": {"movies": {}}
    }))
    monkeypatch.setenv("CENSORR_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")

    environ = _make_environ({
        "source": "radarr",
        "tags": {"censorr_profile": "1", "censorr_preset": "documentary"},
        "mediaPaths": ["/tmp/fake.mkv"],
    })
    result = _run_app(environ)

    assert result["status"].startswith("200")
    body = json.loads(result["body"].decode())
    assert body["status"] == "ignored"
    assert body["reason"] == "unknown_preset"
    assert body["preset"] == "documentary"
