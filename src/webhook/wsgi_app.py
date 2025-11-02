"""Minimal stdlib WSGI application for Censorr webhook service.

Responsibilities (per spec-003):
- Provide /webhook endpoint that applies a minimal allowlist filter on tags.
- If allowlist misses, return 200 ignored.
- If allowlist hits, forward the raw payload to the CLI (which owns business logic),
  and map CLI exit codes to HTTP responses.
- Expose /status counters since process start.
- Expose /healthz and /readyz endpoints.

Environment variables:
- CENSORR_WEBHOOK_ALLOWLIST: comma-separated tag names to allow; default includes
  "censorr_profile". If empty, allowlist is disabled (all events allowed).
- CENSORR_WEBHOOK_SECRET: optional shared secret for authentication. If set, requests
  must include matching X-Webhook-Secret header.
- CENSORR_WEBHOOK_MAX_SIZE: maximum payload size in bytes; default 1MB (1048576).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Callable, Dict, Iterable, Tuple
import subprocess
import uuid
import time
from pathlib import Path

from src.models.config import Config


# In-memory counters (since process start)
COUNTERS = {
    "processed": 0,
    "ignored": 0,
    "failed": 0,
    "queued": 0,  # Placeholder: queue is owned by CLI per spec
}


def _resolve_config_path() -> str | None:
    path = os.getenv("CENSORR_CONFIG_PATH")
    if path:
        return path
    return None


def _load_config() -> Config:
    try:
        return Config.load_with_fallback(_resolve_config_path())
    except Exception as exc:  # pragma: no cover - defensive guard
        _log_structured("ERROR", "Failed to load configuration", error=str(exc))
        return Config()


def _webhooks_enabled(config: Config) -> bool:
    env_val = os.getenv("CENSORR_WEBHOOK_ENABLED")
    if env_val is not None:
        return env_val.strip().lower() not in {"0", "false", "no", "off"}
    return bool(getattr(config, "webhooks_enabled", True))


def _known_presets(config: Config) -> set[str]:
    return set(config.presets.keys())


def _log_structured(level: str, message: str, **kwargs):
    """Log structured JSON to stdout (info/debug) or stderr (warning/error)."""
    log_entry = {
        "timestamp": time.time(),
        "level": level,
        "message": message,
        **kwargs
    }
    log_line = json.dumps(log_entry)
    if level in ("ERROR", "WARNING"):
        print(log_line, file=sys.stderr, flush=True)
    else:
        print(log_line, file=sys.stdout, flush=True)


def _json_response(status: str, body: Dict, start_response: Callable[[str, list], None]) -> Iterable[bytes]:
    payload = json.dumps(body).encode("utf-8")
    start_response(status, [("Content-Type", "application/json"), ("Content-Length", str(len(payload)))])
    return [payload]


def _text_response(status: str, text: str, start_response: Callable[[str, list], None]) -> Iterable[bytes]:
    payload = text.encode("utf-8")
    start_response(status, [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(payload)))])
    return [payload]


def _read_body(environ: Dict) -> Tuple[bytes, str]:
    max_size = int(os.getenv("CENSORR_WEBHOOK_MAX_SIZE", "1048576"))  # 1MB default
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    
    if length > max_size:
        # Return empty body with special marker for oversized detection
        return b"", "oversized"
    
    body = environ.get("wsgi.input")
    if not body:
        return b"", environ.get("CONTENT_TYPE", "")
    
    # Read with safety limit
    if length > 0:
        data = body.read(min(length, max_size))
    else:
        # No content-length, read cautiously up to max_size
        data = body.read(max_size + 1)
        if len(data) > max_size:
            return b"", "oversized"
    
    content_type = environ.get("CONTENT_TYPE", "")
    return data, content_type


def _get_allowlist() -> Tuple[bool, set]:
    raw = os.getenv("CENSORR_WEBHOOK_ALLOWLIST")
    if raw is None:
        # Default allowlist per spec: include 'censorr_profile'
        return True, {"censorr_profile"}
    raw = raw.strip()
    if raw == "":
        # Empty string disables allowlist (accept all)
        return False, set()
    return True, {t.strip() for t in raw.split(",") if t.strip()}


def _apply_allowlist(payload: Dict) -> Tuple[bool, str]:
    enabled, allow = _get_allowlist()
    if not enabled:
        return True, "allowlist_disabled"
    tags = payload.get("tags")
    if not isinstance(tags, dict):
        return False, "missing_or_invalid_tags"
    for tag in allow:
        if tag in tags:
            return True, "allowlist_hit"
    return False, "allowlist_miss"


def _invoke_cli(payload: Dict) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", os.getenv("CENSORR_CLI_MODULE", "src.cli.main"), "webhook"]
    input_data = json.dumps(payload)
    return subprocess.run(
        cmd,
        input=input_data,
        text=True,
        capture_output=True,
        check=False,
    )


def _validate_secret(environ: Dict) -> bool:
    """Validate shared secret if CENSORR_WEBHOOK_SECRET is set."""
    expected_secret = os.getenv("CENSORR_WEBHOOK_SECRET")
    if not expected_secret:
        # No secret configured, validation passes
        return True
    
    # Check X-Webhook-Secret header
    header_secret = environ.get("HTTP_X_WEBHOOK_SECRET", "")
    return header_secret == expected_secret


def _handle_webhook(environ: Dict, start_response: Callable[[str, list], None]) -> Iterable[bytes]:
    request_id = str(uuid.uuid4())
    config = _load_config()

    if not _webhooks_enabled(config):
        _log_structured(
            "INFO",
            "Webhook processing disabled",
            request_id=request_id,
            decision="disabled",
            status=503,
        )
        return _json_response(
            "503 Service Unavailable",
            {"status": "disabled", "reason": "webhook_disabled"},
            start_response,
        )
    
    # Validate shared secret if configured
    if not _validate_secret(environ):
        COUNTERS["failed"] += 1
        _log_structured("WARNING", "Webhook request with invalid or missing secret", 
                        request_id=request_id, decision="failed", status=401, reason="unauthorized")
        return _json_response("401 Unauthorized", {"status": "failed", "reason": "unauthorized"}, start_response)
    
    data, content_type = _read_body(environ)
    
    if content_type == "oversized":
        COUNTERS["failed"] += 1
        max_size = os.getenv("CENSORR_WEBHOOK_MAX_SIZE", "1048576")
        _log_structured("WARNING", "Webhook request payload too large", 
                        request_id=request_id, decision="failed", status=413, reason="payload_too_large",
                        max_size=max_size)
        return _json_response("413 Payload Too Large", {"status": "failed", "reason": "payload_too_large"}, start_response)
    
    if not data:
        COUNTERS["failed"] += 1
        _log_structured("WARNING", "Webhook request with empty body", 
                        request_id=request_id, decision="failed", status=400, reason="empty_body")
        return _json_response("400 Bad Request", {"status": "failed", "reason": "empty_body"}, start_response)

    if "application/json" not in content_type:
        COUNTERS["failed"] += 1
        _log_structured("WARNING", "Webhook request with unsupported content type", 
                        request_id=request_id, decision="failed", status=400, reason="unsupported_content_type",
                        content_type=content_type)
        return _json_response("400 Bad Request", {"status": "failed", "reason": "unsupported_content_type"}, start_response)

    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception as e:
        COUNTERS["failed"] += 1
        _log_structured("WARNING", "Webhook request with malformed JSON", 
                        request_id=request_id, decision="failed", status=400, reason="malformed_json",
                        error=str(e))
        return _json_response("400 Bad Request", {"status": "failed", "reason": "malformed_json"}, start_response)

    source = payload.get("source", "unknown")
    allowed, reason = _apply_allowlist(payload)
    if not allowed:
        COUNTERS["ignored"] += 1
        _log_structured("INFO", "Webhook event ignored by allowlist", 
                        request_id=request_id, source=source, decision="ignored", status=200, reason=reason)
        return _json_response("200 OK", {"status": "ignored", "reason": reason}, start_response)

    tags = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}
    preset = tags.get("censorr_preset") if isinstance(tags, dict) else None
    if not preset:
        COUNTERS["ignored"] += 1
        _log_structured(
            "INFO",
            "Webhook event ignored due to missing preset tag",
            request_id=request_id,
            source=source,
            decision="ignored",
            status=200,
            reason="missing_preset",
        )
        return _json_response(
            "200 OK", {"status": "ignored", "reason": "missing_preset"}, start_response
        )

    presets = _known_presets(config)
    if presets and preset not in presets:
        COUNTERS["ignored"] += 1
        _log_structured(
            "WARNING",
            "Webhook event ignored due to unknown preset",
            request_id=request_id,
            source=source,
            decision="ignored",
            status=200,
            reason="unknown_preset",
            preset=preset,
        )
        return _json_response(
            "200 OK",
            {"status": "ignored", "reason": "unknown_preset", "preset": preset},
            start_response,
        )

    try:
        result = _invoke_cli(payload)
    except Exception as exc:
        COUNTERS["failed"] += 1
        _log_structured(
            "ERROR",
            "Webhook CLI invocation error",
            request_id=request_id,
            source=source,
            decision="failed",
            status=500,
            reason="cli_invocation_error",
            error=str(exc),
            preset=preset,
        )
        return _json_response(
            "500 Internal Server Error",
            {"status": "failed", "reason": "cli_invocation_error"},
            start_response,
        )

    exit_code = result.returncode
    raw_stdout = result.stdout
    raw_stderr = result.stderr
    cli_stdout = str(raw_stdout) if raw_stdout else ""
    cli_stderr = str(raw_stderr) if raw_stderr else ""

    if exit_code == 0:
        COUNTERS["processed"] += 1
        COUNTERS["queued"] += 1
        _log_structured(
            "INFO",
            "Webhook accepted by CLI",
            request_id=request_id,
            source=source,
            decision="accepted",
            status=202,
            preset=preset,
            exit_code=exit_code,
        )
        if cli_stdout:
            _log_structured("DEBUG", "CLI stdout", request_id=request_id, stdout=cli_stdout)
        if cli_stderr:
            _log_structured("DEBUG", "CLI stderr", request_id=request_id, stderr=cli_stderr)
        body = {"status": "accepted", "preset": preset}
        return _json_response("202 Accepted", body, start_response)

    if exit_code == 2:
        COUNTERS["ignored"] += 1
        _log_structured(
            "INFO",
            "Webhook ignored by CLI",
            request_id=request_id,
            source=source,
            decision="ignored",
            status=200,
            preset=preset,
            exit_code=exit_code,
        )
        body = {"status": "ignored", "reason": "cli_ignored", "preset": preset}
        return _json_response("200 OK", body, start_response)

    if exit_code == 3:
        COUNTERS["failed"] += 1
        _log_structured(
            "WARNING",
            "Webhook rejected by CLI",
            request_id=request_id,
            source=source,
            decision="failed",
            status=400,
            preset=preset,
            exit_code=exit_code,
            stderr=cli_stderr,
        )
        body = {"status": "failed", "reason": "cli_failed", "preset": preset}
        return _json_response("400 Bad Request", body, start_response)

    COUNTERS["failed"] += 1
    _log_structured(
        "ERROR",
        "Webhook CLI returned unexpected code",
        request_id=request_id,
        source=source,
        decision="failed",
        status=500,
        preset=preset,
        exit_code=exit_code,
    stderr=cli_stderr,
    )
    body = {"status": "failed", "reason": "cli_error", "preset": preset}
    return _json_response("500 Internal Server Error", body, start_response)


def _handle_status(start_response: Callable[[str, list], None]) -> Iterable[bytes]:
    body = {
        "processed": COUNTERS["processed"],
        "ignored": COUNTERS["ignored"],
        "failed": COUNTERS["failed"],
        "queued": COUNTERS["queued"],
        "queue_depth": COUNTERS["queued"],
    }
    return _json_response("200 OK", body, start_response)


def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/")

    if method == "POST" and path == "/webhook":
        return _handle_webhook(environ, start_response)
    if method == "GET" and path == "/status":
        return _handle_status(start_response)
    if method == "GET" and path == "/healthz":
        return _text_response("200 OK", "ok", start_response)
    if method == "GET" and path == "/readyz":
        # Consider ready if Python process is up; CLI owned worker readiness is out of scope here
        return _text_response("200 OK", "ready", start_response)

    return _text_response("404 Not Found", "not found", start_response)


__all__ = ["app"]
