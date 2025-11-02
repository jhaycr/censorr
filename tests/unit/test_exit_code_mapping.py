import json
from io import BytesIO
from unittest.mock import patch, Mock

from src.webhook.wsgi_app import app


def run(env):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(app(env, start_response))
    captured["body"] = body
    return captured


def make_env(payload):
    data = json.dumps(payload).encode()
    return {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/webhook",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": BytesIO(data),
    }


@patch("src.webhook.wsgi_app.subprocess.run")
def test_exit_code_0_maps_202(mock_run, monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    mock_run.return_value = Mock(returncode=0)
    env = make_env({"tags": {"censorr_profile": "1", "censorr_preset": "movies"}, "mediaPaths": ["/a"]})
    res = run(env)
    assert res["status"].startswith("202")


@patch("src.webhook.wsgi_app.subprocess.run")
def test_exit_code_2_maps_200(mock_run, monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    mock_run.return_value = Mock(returncode=2)
    env = make_env({"tags": {"censorr_profile": "1", "censorr_preset": "movies"}, "mediaPaths": ["/a"]})
    res = run(env)
    assert res["status"].startswith("200")


@patch("src.webhook.wsgi_app.subprocess.run")
def test_exit_code_3_maps_400(mock_run, monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    mock_run.return_value = Mock(returncode=3)
    env = make_env({"tags": {"censorr_profile": "1", "censorr_preset": "movies"}, "mediaPaths": ["/a"]})
    res = run(env)
    assert res["status"].startswith("400")


@patch("src.webhook.wsgi_app.subprocess.run")
def test_exit_code_1_maps_500(mock_run, monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    mock_run.return_value = Mock(returncode=1)
    env = make_env({"tags": {"censorr_profile": "1", "censorr_preset": "movies"}, "mediaPaths": ["/a"]})
    res = run(env)
    assert res["status"].startswith("500")
