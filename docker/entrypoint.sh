#!/bin/sh
# Named volumes are created root-owned on first mount; fix ownership of the
# app-writable roots, then drop privileges. Never runs the app as root.
set -e

if [ "$(id -u)" = "0" ]; then
    for d in /app/queue /app/work; do
        mkdir -p "$d"
        chown censorr:censorr "$d"
    done
    exec su-exec censorr:censorr censorr "$@"
fi

exec censorr "$@"
