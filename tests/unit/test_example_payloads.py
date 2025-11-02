import json
from io import BytesIO
from unittest.mock import patch, Mock

from src.webhook.wsgi_app import app


def run(environ):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(app(environ, start_response))
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
def test_radarr_media_import_example(mock_run, monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    # Simulate CLI accepting
    mock_run.return_value = Mock(returncode=0)
    payload = {
        "source": "radarr",
        "eventType": "MovieImported",
        "tags": {
            "censorr_profile": "true",
            "censorr_preset": "movies",
        },
        "mediaPaths": ["/media/movies/Inception (2010)/Inception.mkv"],
    }
    res = run(make_env(payload))
    assert res["status"].startswith("202")


@patch("src.webhook.wsgi_app.subprocess.run")
def test_sonarr_import_example_missing_preset_ignored(mock_run, monkeypatch):
    monkeypatch.setenv("CENSORR_WEBHOOK_ALLOWLIST", "censorr_profile")
    # Simulate CLI ignoring
    mock_run.return_value = Mock(returncode=2)
    payload = {
        "source": "sonarr",
        "eventType": "EpisodeImported",
        "tags": {
            "censorr_profile": "true",
        },
        "mediaPaths": ["/media/tv/Show/Season 01/Show - S01E01 - Pilot.mkv"],
    }
    res = run(make_env(payload))
    assert res["status"].startswith("200")
