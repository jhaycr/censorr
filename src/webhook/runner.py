"""Gunicorn entry point.

Use: gunicorn -w 2 -b 0.0.0.0:8080 src.webhook.runner:app
"""

from .wsgi_app import app

__all__ = ["app"]
