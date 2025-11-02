"""Unit tests for webhook security features (T014): shared secret and oversized payload rejection."""

import json
import os
from io import BytesIO
from unittest import mock

import pytest

from src.webhook.wsgi_app import app


def make_environ(body: bytes, headers: dict = None, content_length: int = None):
    """Helper to construct WSGI environ dict for tests."""
    headers = headers or {}
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/webhook",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(content_length if content_length is not None else len(body)),
        "wsgi.input": BytesIO(body),
        "wsgi.errors": BytesIO(),
    }
    # Add HTTP headers
    for key, value in headers.items():
        environ[f"HTTP_{key.upper().replace('-', '_')}"] = value
    return environ


def test_no_secret_configured_allows_all():
    """When CENSORR_WEBHOOK_SECRET is not set, requests without secret pass validation."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("os.getenv", side_effect=lambda k, d=None: {"CENSORR_WEBHOOK_ALLOWLIST": "test_tag"}.get(k, d)):
            payload = {"source": "test", "tags": {"test_tag": "value"}, "mediaPaths": []}
            body = json.dumps(payload).encode("utf-8")
            environ = make_environ(body)
            
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=0)
                
                response_started = []
                def start_response(status, headers):
                    response_started.append(status)
                
                result = list(app(environ, start_response))
                
                assert response_started[0].startswith("202")


def test_valid_secret_allows_request():
    """When CENSORR_WEBHOOK_SECRET is set and request has matching X-Webhook-Secret header, request passes."""
    with mock.patch.dict(os.environ, {"CENSORR_WEBHOOK_SECRET": "test-secret-123"}, clear=True):
        with mock.patch("os.getenv", side_effect=lambda k, d=None: {
            "CENSORR_WEBHOOK_SECRET": "test-secret-123",
            "CENSORR_WEBHOOK_ALLOWLIST": "test_tag"
        }.get(k, d)):
            payload = {"source": "test", "tags": {"test_tag": "value"}, "mediaPaths": []}
            body = json.dumps(payload).encode("utf-8")
            environ = make_environ(body, headers={"X-Webhook-Secret": "test-secret-123"})
            
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=0)
                
                response_started = []
                def start_response(status, headers):
                    response_started.append(status)
                
                result = list(app(environ, start_response))
                
                assert response_started[0].startswith("202")


def test_invalid_secret_returns_401():
    """When CENSORR_WEBHOOK_SECRET is set and request has wrong secret, return 401."""
    with mock.patch.dict(os.environ, {"CENSORR_WEBHOOK_SECRET": "test-secret-123"}, clear=True):
        with mock.patch("os.getenv", side_effect=lambda k, d=None: {
            "CENSORR_WEBHOOK_SECRET": "test-secret-123",
            "CENSORR_WEBHOOK_ALLOWLIST": "test_tag"
        }.get(k, d)):
            payload = {"source": "test", "tags": {"test_tag": "value"}, "mediaPaths": []}
            body = json.dumps(payload).encode("utf-8")
            environ = make_environ(body, headers={"X-Webhook-Secret": "wrong-secret"})
            
            response_started = []
            def start_response(status, headers):
                response_started.append(status)
            
            result = list(app(environ, start_response))
            response_body = json.loads(b"".join(result))
            
            assert response_started[0].startswith("401")
            assert response_body["status"] == "failed"
            assert response_body["reason"] == "unauthorized"


def test_missing_secret_returns_401():
    """When CENSORR_WEBHOOK_SECRET is set and request has no secret header, return 401."""
    with mock.patch.dict(os.environ, {"CENSORR_WEBHOOK_SECRET": "test-secret-123"}, clear=True):
        with mock.patch("os.getenv", side_effect=lambda k, d=None: {
            "CENSORR_WEBHOOK_SECRET": "test-secret-123",
            "CENSORR_WEBHOOK_ALLOWLIST": "test_tag"
        }.get(k, d)):
            payload = {"source": "test", "tags": {"test_tag": "value"}, "mediaPaths": []}
            body = json.dumps(payload).encode("utf-8")
            environ = make_environ(body)  # No secret header
            
            response_started = []
            def start_response(status, headers):
                response_started.append(status)
            
            result = list(app(environ, start_response))
            response_body = json.loads(b"".join(result))
            
            assert response_started[0].startswith("401")
            assert response_body["status"] == "failed"
            assert response_body["reason"] == "unauthorized"


def test_oversized_payload_returns_413():
    """When payload exceeds CENSORR_WEBHOOK_MAX_SIZE, return 413."""
    with mock.patch.dict(os.environ, {"CENSORR_WEBHOOK_MAX_SIZE": "100"}, clear=True):
        with mock.patch("os.getenv", side_effect=lambda k, d=None: {
            "CENSORR_WEBHOOK_MAX_SIZE": "100",
            "CENSORR_WEBHOOK_ALLOWLIST": "test_tag"
        }.get(k, d)):
            # Create payload larger than 100 bytes
            large_payload = {"source": "test", "tags": {"test_tag": "value"}, "data": "x" * 200}
            body = json.dumps(large_payload).encode("utf-8")
            environ = make_environ(body)
            
            response_started = []
            def start_response(status, headers):
                response_started.append(status)
            
            result = list(app(environ, start_response))
            response_body = json.loads(b"".join(result))
            
            assert response_started[0].startswith("413")
            assert response_body["status"] == "failed"
            assert response_body["reason"] == "payload_too_large"


def test_default_max_size_is_1mb():
    """By default, CENSORR_WEBHOOK_MAX_SIZE is 1MB (1048576 bytes)."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("os.getenv", side_effect=lambda k, d=None: {
            "CENSORR_WEBHOOK_ALLOWLIST": "test_tag"
        }.get(k, d)):
            # Create payload just under 1MB
            payload = {"source": "test", "tags": {"test_tag": "value"}, "data": "x" * (1048000)}
            body = json.dumps(payload).encode("utf-8")
            environ = make_environ(body)
            
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=0)
                
                response_started = []
                def start_response(status, headers):
                    response_started.append(status)
                
                result = list(app(environ, start_response))
                
                # Should succeed (not 413)
                assert response_started[0].startswith("202")
