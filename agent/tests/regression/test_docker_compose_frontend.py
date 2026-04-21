from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = ROOT / "docker-compose.yml"


def test_compose_pins_runtime_to_single_baked_frontend():
    source = COMPOSE_PATH.read_text(encoding="utf-8")

    assert "VIBE_TRADING_FRONTEND_ROOT: /app/frontend" in source
    assert "VIBE_TRADING_FRONTEND_DIST: /app/frontend/dist" in source