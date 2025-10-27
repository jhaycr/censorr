#!/bin/sh
set -e

# If no args or explicitly 'daemon', run worker loop.
# If 'worker', run worker loop.
# If 'webhook', start the Gunicorn webhook service.
# Otherwise, execute the censorr CLI with provided arguments.
if [ "$#" -eq 0 ] || [ "$1" = "daemon" ] || [ "$1" = "worker" ]; then
  echo "[censorr] Starting worker loop"
  exec python -m src.worker.runner
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
