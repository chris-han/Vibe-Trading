#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="semantier:vibe-trading"
CONTAINER_NAME="vibe-trading"
ENV_FILE=".env"
PORT="8899"

cd /home/chris/repo/Vibe-Trading

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE in $PWD" >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

docker run -d \
  --name "$CONTAINER_NAME" \
  --env-file "$ENV_FILE" \
  -p "$PORT:8899" \
  "$IMAGE_NAME"

echo "Started $CONTAINER_NAME on http://localhost:$PORT"