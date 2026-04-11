"""Repo-local Hermes plugin for Vibe-Trading tools."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_hermes_agent_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    hermes_agent_root = repo_root / "hermes-agent"
    agent_root = repo_root / "agent"
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))
    if str(hermes_agent_root) not in sys.path:
        sys.path.insert(0, str(hermes_agent_root))


def _iter_tool_specs():
    _ensure_hermes_agent_on_path()

    from src.hermes_tool_adapter.vibe_trading_compat import TOOL_REGISTRATIONS as compat_tools
    from src.hermes_tool_adapter.vibe_trading_finance import TOOL_REGISTRATIONS as finance_tools

    return [*compat_tools, *finance_tools]


def register(ctx) -> None:
    for spec in _iter_tool_specs():
        ctx.register_tool(
            name=spec["name"],
            toolset=spec["toolset"],
            schema=spec["schema"],
            handler=spec["handler"],
            check_fn=spec.get("check_fn"),
            requires_env=spec.get("requires_env"),
            is_async=spec.get("is_async", False),
            description=spec.get("description", ""),
            emoji=spec.get("emoji", ""),
        )
