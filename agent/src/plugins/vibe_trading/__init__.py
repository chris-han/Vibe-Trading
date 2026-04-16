"""Hermes entry-point plugin for Vibe-Trading tools."""

from __future__ import annotations

import sys
from pathlib import Path


_TOOL_SPECS = (
    ("setup_backtest_run", "🗂️", "SETUP_BACKTEST_RUN", "setup_backtest_run"),
    ("backtest", "📈", "BACKTEST", "backtest"),
    ("factor_analysis", "📊", "FACTOR_ANALYSIS", "factor_analysis"),
    ("options_pricing", "📉", "OPTIONS_PRICING", "options_pricing"),
    ("pattern", "🕯️", "PATTERN", "pattern"),
    ("list_swarm_presets", "🐝", "LIST_SWARM_PRESETS", "list_swarm_presets"),
    ("run_swarm", "🐝", "RUN_SWARM", "run_swarm"),
)


def _ensure_hermes_agent_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    hermes_agent_root = repo_root / "hermes-agent"
    agent_root = repo_root / "agent"
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))
    if str(hermes_agent_root) not in sys.path:
        sys.path.insert(0, str(hermes_agent_root))


def register(ctx) -> None:
    _ensure_hermes_agent_on_path()

    from . import schemas, tools

    for name, emoji, schema_name, handler_name in _TOOL_SPECS:
        schema = getattr(schemas, schema_name)
        handler = getattr(tools, handler_name)
        ctx.register_tool(
            name=name,
            toolset=schemas.TOOLSET_NAME,
            schema=schema,
            handler=handler,
            description=schema.get("description", ""),
            emoji=emoji,
        )