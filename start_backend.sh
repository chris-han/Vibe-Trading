#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$ROOT/agent"
WORKSPACES_DIR="$ROOT/workspaces"
RUNTIME_DIR="$ROOT/.runtime"
BACKEND_PORT="${BACKEND_PORT:-8899}"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
BACKEND_LOG_FILE="$RUNTIME_DIR/backend.log"

mkdir -p "$RUNTIME_DIR"

stop_pid() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    return 0
  fi
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in {1..40}; do
      if ! kill -0 "$pid" 2>/dev/null; then
        return 0
      fi
      sleep 0.25
    done
    kill -9 "$pid" 2>/dev/null || true
  fi
}

stop_backend() {
  if [[ -f "$BACKEND_PID_FILE" ]]; then
    local pid
    pid="$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)"
    stop_pid "$pid"
    rm -f "$BACKEND_PID_FILE"
  fi

  for pid in $(lsof -tiTCP:"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null || true); do
    stop_pid "$pid"
  done
}

stop_gateways() {
  if [[ ! -d "$WORKSPACES_DIR" ]]; then
    return 0
  fi

  while IFS= read -r -d '' pid_file; do
    local pid
    pid="$(python3 - "$pid_file" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
raw = path.read_text(encoding="utf-8").strip()
if not raw:
    print("")
elif raw.startswith("{"):
    try:
        print(int(json.loads(raw).get("pid") or 0) or "")
    except Exception:
        print("")
else:
    try:
        print(int(raw))
    except Exception:
        print("")
PY
)
"
    stop_pid "$pid"
    rm -f "$pid_file"
  done < <(find "$WORKSPACES_DIR" -path '*/.hermes/gateway.pid' -print0 2>/dev/null)
}

echo "[backend] stopping backend on port $BACKEND_PORT..."
stop_backend

echo "[backend] stopping workspace gateways..."
stop_gateways

echo "[backend] starting API server on port $BACKEND_PORT..."
(
  cd "$AGENT_DIR"
  nohup ./.venv/bin/python api_server.py --port "$BACKEND_PORT" >>"$BACKEND_LOG_FILE" 2>&1 &
  echo $! >"$BACKEND_PID_FILE"
)

BACKEND_PID="$(cat "$BACKEND_PID_FILE")"

for _ in {1..60}; do
  if curl -fsS "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "[backend] failed to start; see $BACKEND_LOG_FILE" >&2
    exit 1
  fi
  sleep 0.5
done

if ! curl -fsS "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
  echo "[backend] timed out waiting for health check; see $BACKEND_LOG_FILE" >&2
  exit 1
fi

echo "[backend] backend is up (pid=$BACKEND_PID)"

echo "[backend] restarting configured workspace gateways..."
(
  cd "$AGENT_DIR"
  ./.venv/bin/python - <<'PY'
from __future__ import annotations

from pathlib import Path

import api_server


def workspace_has_messaging_config(hermes_home: Path) -> bool:
    config = api_server._load_yaml_mapping(hermes_home / "config.yaml")
    platforms = config.get("platforms")
    if not isinstance(platforms, dict):
        return False

    for name in ("weixin", "feishu"):
        block = platforms.get(name)
        if isinstance(block, dict) and block.get("enabled"):
            return True
    return False


started: list[str] = []
skipped: list[str] = []

for workspace_dir in sorted(api_server.WORKSPACES_DIR.iterdir()):
    if not workspace_dir.is_dir():
        continue
    hermes_home = workspace_dir / ".hermes"
    if not hermes_home.exists():
        continue
    if not workspace_has_messaging_config(hermes_home):
        skipped.append(workspace_dir.name)
        continue
    ok = api_server._ensure_workspace_gateway_running(hermes_home, force_restart=True)
    if ok:
        started.append(workspace_dir.name)
    else:
        skipped.append(workspace_dir.name)

print(f"[backend] gateways restarted for: {', '.join(started) if started else '(none)'}")
print(f"[backend] gateways skipped: {', '.join(skipped) if skipped else '(none)'}")
PY
)

echo "[backend] log=$BACKEND_LOG_FILE"
echo "[backend] url=http://127.0.0.1:$BACKEND_PORT"