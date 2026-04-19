#!/bin/sh
set -eu

BOOTSTRAP_HERMES_DIR=/app/bootstrap/hermes
TARGET_HERMES_DIR=/app/agent/.hermes

mkdir -p "$TARGET_HERMES_DIR" /app/workspaces/public

if [ -d "$BOOTSTRAP_HERMES_DIR" ]; then
    if [ -f "$BOOTSTRAP_HERMES_DIR/config.yaml" ] && [ ! -f "$TARGET_HERMES_DIR/config.yaml" ]; then
        cp "$BOOTSTRAP_HERMES_DIR/config.yaml" "$TARGET_HERMES_DIR/config.yaml"
    fi

    if [ -f "$BOOTSTRAP_HERMES_DIR/.env" ] && [ ! -f "$TARGET_HERMES_DIR/.env" ]; then
        cp "$BOOTSTRAP_HERMES_DIR/.env" "$TARGET_HERMES_DIR/.env"
    fi

    for child in skills memories logs home profiles; do
        mkdir -p "$TARGET_HERMES_DIR/$child"
    done
fi

exec "$@"