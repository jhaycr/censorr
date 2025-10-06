#!/bin/sh
set -e

# If no args or explicitly 'daemon', run as a long-running idle service.
# Otherwise, execute the censorr CLI with provided arguments.
if [ "$#" -eq 0 ] || [ "$1" = "daemon" ]; then
  echo "[censorr] Starting in daemon mode (idle). Use 'docker exec' to run jobs."
  # Keep container alive
  tail -f /dev/null
else
  exec censorr "$@"
fi
