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


def test_health_ready_endpoints():
    health = run_get("/healthz")
    assert health["status"].startswith("200")
    ready = run_get("/readyz")
    assert ready["status"].startswith("200")
