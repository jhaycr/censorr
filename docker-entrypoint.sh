#!/bin/sh
set -e

ensure_queue_dirs() {
  Q=/app/queue
  if [ ! -d "$Q" ]; then
    mkdir -p "$Q" || true
  fi
  mkdir -p "$Q/incoming" "$Q/processing" "$Q/done" "$Q/failed" || true
  # If running as root, fix ownership to censorr (1000:1000) so webhook can write too
  if [ "$(id -u)" = "0" ]; then
    chown -R 1000:1000 "$Q" || true
  fi
}

# If no args or explicitly 'daemon', run worker loop.
# If 'worker', run worker loop.
# If 'webhook', start the Gunicorn webhook service.
# Otherwise, execute the censorr CLI with provided arguments.
if [ "$#" -eq 0 ] || [ "$1" = "daemon" ] || [ "$1" = "worker" ]; then
  echo "[censorr] Initializing queue directories"
  ensure_queue_dirs
  echo "[censorr] Starting worker loop as unprivileged user 'censorr' (UID 1000)"
  # Drop privileges in-process and run the worker as UID/GID 1000 to avoid running the worker as root
  exec python - <<'PY'
import os, runpy
os.setgid(1000)
os.setuid(1000)
runpy.run_module('src.worker.runner', run_name='__main__')
PY
elif [ "$1" = "webhook" ]; then
  echo "[censorr] Starting webhook service on port 8000"
  exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    src.webhook.runner:app
else
  exec censorr "$@"
fi
