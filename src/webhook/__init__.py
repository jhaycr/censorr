"""Webhook service package for Censorr.

Contains a minimal stdlib WSGI app intended to be served by Gunicorn
inside the container. The server applies only a tag-allowlist filter
and forwards accepted events to the CLI, which owns business logic.
"""

__all__ = [
    "app",
]
