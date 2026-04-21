#!/usr/bin/env python3
"""Semantier wrapper for the Hermes dashboard.

Runs the upstream Hermes dashboard app under request-scoped HERMES_HOME
middleware so a single dashboard process can serve per-workspace state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
HERMES_AGENT_ROOT = REPO_ROOT / "hermes-agent"
if str(HERMES_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_AGENT_ROOT))

from hermes_constants import reset_active_hermes_home, set_active_hermes_home
from hermes_cli.web_server import app as hermes_dashboard_app

HERMES_HOME_HEADER = "x-hermes-home"
REQUIRE_HERMES_HOME_PREFIXES = (
    "/api/",
    "/v1/",
)
OPTIONAL_HERMES_HOME_PATHS = {
    "/api/status",
    "/api/config/defaults",
    "/api/config/schema",
    "/api/model/info",
    "/api/dashboard/themes",
    "/api/dashboard/plugins",
    "/api/dashboard/plugins/rescan",
}


class RequestScopedHermesHomeMiddleware:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        header_map = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        raw = header_map.get(HERMES_HOME_HEADER, "").strip()
        if raw:
            candidate = Path(raw).expanduser()
            if not candidate.is_absolute():
                payload = json.dumps(
                    {"detail": "X-Hermes-Home must be an absolute path"}
                ).encode("utf-8")
                await send(
                    {
                        "type": "http.response.start",
                        "status": 400,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(payload)).encode("ascii")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": payload})
                return
            token = set_active_hermes_home(candidate)
        else:
            requires_hermes_home = (
                path.startswith(REQUIRE_HERMES_HOME_PREFIXES)
                and path not in OPTIONAL_HERMES_HOME_PATHS
            )
            if requires_hermes_home:
                payload = json.dumps(
                    {"detail": "X-Hermes-Home header is required"}
                ).encode("utf-8")
                await send(
                    {
                        "type": "http.response.start",
                        "status": 428,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(payload)).encode("ascii")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": payload})
                return
            token = None

        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                reset_active_hermes_home(token)


app = RequestScopedHermesHomeMiddleware(hermes_dashboard_app)


def start_server(
    host: str = "127.0.0.1",
    port: int = 9119,
    log_level: str = "warning",
) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    start_server()
