"""Deterministic shared skill script materialization helpers.

This module enforces the Semantier wrapper-first sandbox policy:
- Detect shared skill script absolute paths in terminal commands
- Copy scripts into task-local `.scripts/` inside task cwd
- Rewrite command paths to sandbox-relative paths
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

# Match absolute paths under .../agent/src/skills/.../scripts/...
_SHARED_SKILL_SCRIPT_ABS_PATH_RE = re.compile(
    r"(?P<path>/[^\s'\"`]*?/agent/src/skills/(?P<rel>[^\s'\"`]+?/scripts/[^\s'\"`]+))"
)


def _safe_relpath(path: Path, start: Path) -> str:
    """Return a stable relative path from *start* to *path*."""
    rel = os.path.relpath(path, start)
    return rel.replace("\\", "/")


def materialize_shared_skill_scripts_for_command(command: str, *, task_cwd: Path) -> tuple[str, list[str]]:
    """Materialize shared skill scripts referenced by absolute path in a command.

    Args:
        command: Raw shell command from terminal tool invocation.
        task_cwd: Task working directory where `.scripts/` is created.

    Returns:
        (rewritten_command, materialized_relative_paths)

    Raises:
        RuntimeError: If a referenced shared script exists but cannot be copied.
    """
    if not isinstance(command, str) or not command.strip():
        return command, []

    cwd = task_cwd.resolve()
    rewritten = command
    materialized: list[str] = []

    # De-duplicate by source path while preserving first-seen order.
    seen: set[str] = set()

    for match in _SHARED_SKILL_SCRIPT_ABS_PATH_RE.finditer(command):
        source_raw = match.group("path")
        if source_raw in seen:
            continue
        seen.add(source_raw)

        source_path = Path(source_raw).resolve()
        if not source_path.exists() or not source_path.is_file():
            # Skip unknown paths so we don't mask unrelated command behavior.
            continue

        rel_under_skills = match.group("rel")
        dest_path = (cwd / ".scripts" / rel_under_skills).resolve()

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)
        except Exception as exc:
            raise RuntimeError(f"could not copy '{source_path}' -> '{dest_path}': {exc}") from exc

        rel_for_command = _safe_relpath(dest_path, cwd)
        rewritten = rewritten.replace(source_raw, rel_for_command)
        materialized.append(rel_for_command)

    return rewritten, materialized
