#!/bin/sh
# Named volumes are created root-owned on first mount; fix ownership of the
# app-writable roots, then drop privileges. Never runs the app as root.
set -e

# The compose file mounts the config dir at /app/config; pass it explicitly
# to the commands that take it (censorr's own discovery only checks cwd and
# ~/.config). Other commands (version, --help) pass through untouched.
CONFIG_ARGS=""
case "$1" in
    serve|work|gc|process|inspect|reprocess|reconcile)
        if [ -f /app/config/censorr.toml ]; then
            CONFIG_ARGS="--config /app/config/censorr.toml"
        fi
        ;;
esac

if [ "$(id -u)" = "0" ]; then
    for d in /app/queue /app/work; do
        mkdir -p "$d"
        chown censorr:censorr "$d"
    done
    # shellcheck disable=SC2086
    exec su-exec censorr:censorr censorr "$@" $CONFIG_ARGS
fi

# shellcheck disable=SC2086
exec censorr "$@" $CONFIG_ARGS
