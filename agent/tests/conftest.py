"""
Shared pytest configuration for Vibe-Trading migration tests.

Two suites share this conftest:
  tests/baseline/   -> runs against main worktree (original AgentLoop implementation)
  tests/regression/ -> runs against hermes branch (AIAgent-based implementation)

The MAIN_WORKTREE environment variable (or the default path below) must point to
the git worktree where the `main` branch is checked out.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERMES_BRANCH_BACKEND = Path(__file__).resolve().parents[1]          # agent/
MAIN_WORKTREE_AGENT   = Path(
    os.environ.get("MAIN_WORKTREE", "/home/chris/repo/Vibe-Trading-main/agent")
)

# ---------------------------------------------------------------------------
# Fixtures (shared)
# ---------------------------------------------------------------------------
import pytest


@pytest.fixture(scope="session")
def main_agent_path() -> Path:
    """Absolute path to the main-branch agent directory."""
    assert MAIN_WORKTREE_AGENT.exists(), (
        f"Main worktree not found at {MAIN_WORKTREE_AGENT}. "
        "Run: git worktree add /home/chris/repo/Vibe-Trading-main main"
    )
    return MAIN_WORKTREE_AGENT


@pytest.fixture(scope="session")
def hermes_backend_path() -> Path:
    """Absolute path to the hermes-branch agent directory."""
    return HERMES_BRANCH_BACKEND


def _add_path_once(p: Path) -> None:
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


@pytest.fixture(scope="session")
def main_sys_path(main_agent_path):
    """Insert main-branch agent dir into sys.path for the test session."""
    _add_path_once(main_agent_path)
    yield main_agent_path
    # Leave path in place — test teardown order is not worth managing here.


@pytest.fixture(scope="session")
def hermes_sys_path(hermes_backend_path):
    """Insert hermes-branch agent dir into sys.path for the test session."""
    _add_path_once(hermes_backend_path)
    yield hermes_backend_path
