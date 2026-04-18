from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
VITE_CONFIG_PATH = REPO_ROOT / "frontend" / "vite.config.ts"


def test_vite_dev_server_proxies_auth_routes_to_backend():
    source = VITE_CONFIG_PATH.read_text(encoding="utf-8")

    assert '"/auth": { target: "http://localhost:8899", changeOrigin: true }' in source, (
        "frontend/vite.config.ts must proxy /auth to the FastAPI backend in dev mode. "
        "Without this, /auth/me and /auth/feishu/login are handled by the SPA dev server "
        "and return the React router 404 page instead of the backend auth response."
    )