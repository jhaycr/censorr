import json
from io import BytesIO

from src.webhook.wsgi_app import app


def run_get(path):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "wsgi.input": BytesIO(b""),
    }
    body = b"".join(app(environ, start_response))
    captured["body"] = body
    return captured


def test_status_schema_and_defaults():
    result = run_get("/status")
    assert result["status"].startswith("200")
    body = json.loads(result["body"].decode())
    for key in ["processed", "ignored", "failed", "queued", "queue_depth"]:
        assert key in body
        assert isinstance(body[key], int)
