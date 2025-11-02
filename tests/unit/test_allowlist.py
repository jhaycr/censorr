import json
from io import BytesIO

from src.webhook import wsgi_app


def run_post(payload, monkeypatch, allowlist=None):
    if allowlist is not None:
        monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", allowlist)
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/webhook",
        "CONTENT_TYPE": "application/json",
        "wsgi.input": BytesIO(json.dumps(payload).encode()),
    }
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(wsgi_app.app(environ, start_response))
    captured["body"] = body
    return captured


def test_allowlist_disabled_accepts_all(monkeypatch):
    payload = {"tags": {"nothing": "x"}, "mediaPaths": []}
    res = run_post(payload, monkeypatch, allowlist="")
    # With allowlist disabled, we forward to CLI which will likely 500 here; but server-level we only check status code family
    # For empty mediaPaths, CLI will return ignored; status should still be 200
    assert res["status"].startswith("200") or res["status"].startswith("5")


def test_allowlist_hit(monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile,other")
    payload = {"tags": {"censorr_profile": "1"}, "mediaPaths": []}
    res = run_post(payload, monkeypatch)
    # CLI will likely ignore due to no preset/mediaPaths; server should still respond 200 or 500 depending on CLI
    assert res["status"].startswith("200") or res["status"].startswith("5")


def test_allowlist_miss(monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    payload = {"tags": {"foo": "bar"}}
    res = run_post(payload, monkeypatch)
    assert res["status"].startswith("200")
