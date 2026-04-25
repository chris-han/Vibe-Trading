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

# Match script references inside task sandbox paths:
# - .scripts/<skill>/scripts/<file>
# - /workspace/run/artifacts/.scripts/<skill>/scripts/<file>
_SANDBOX_SKILL_SCRIPT_PATH_RE = re.compile(
    r"(?P<path>(?:/workspace/run/artifacts/)?\.scripts/(?P<skill>[^/\s'\"`]+)/scripts/(?P<file>[^/\s'\"`]+))"
)


def _safe_relpath(path: Path, start: Path) -> str:
    """Return a stable relative path from *start* to *path*."""
    rel = os.path.relpath(path, start)
    return rel.replace("\\", "/")


def _copy_if_missing(source_path: Path, dest_path: Path) -> None:
    """Copy source_path to dest_path if needed, preserving metadata."""
    if dest_path.exists() and dest_path.is_file():
        return
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, dest_path)


def _find_source_for_sandbox_skill_path(skill_name: str, script_file: str) -> Path | None:
    """Resolve shared skill source for a sandbox `.scripts/<skill>/scripts/<file>` path."""
    skills_root = Path(__file__).resolve().parent
    if not skills_root.exists():
        return None

    candidates = sorted(skills_root.glob(f"**/{skill_name}/scripts/{script_file}"))
    if len(candidates) == 1 and candidates[0].is_file():
        return candidates[0].resolve()
    return None


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

        # Canonical sandbox location mirrors skill docs:
        # .scripts/<skill-name>/scripts/<script-file>
        rel_path_obj = Path(rel_under_skills)
        try:
            scripts_idx = rel_path_obj.parts.index("scripts")
        except ValueError:
            scripts_idx = -1

        if scripts_idx <= 0:
            continue

        skill_name = rel_path_obj.parts[scripts_idx - 1]
        script_file = rel_path_obj.parts[-1]
        canonical_rel = f".scripts/{skill_name}/scripts/{script_file}"
        dest_path = (cwd / canonical_rel).resolve()

        try:
            _copy_if_missing(source_path, dest_path)
        except Exception as exc:
            raise RuntimeError(f"could not copy '{source_path}' -> '{dest_path}': {exc}") from exc

        rel_for_command = _safe_relpath(dest_path, cwd)
        rewritten = rewritten.replace(source_raw, rel_for_command)
        materialized.append(rel_for_command)

    # Also support commands that already reference sandbox `.scripts/...` paths.
    seen_sandbox_paths: set[str] = set()
    for match in _SANDBOX_SKILL_SCRIPT_PATH_RE.finditer(rewritten):
        raw_path = match.group("path")
        if raw_path in seen_sandbox_paths:
            continue
        seen_sandbox_paths.add(raw_path)

        skill_name = match.group("skill")
        script_file = match.group("file")
        source_path = _find_source_for_sandbox_skill_path(skill_name, script_file)
        if source_path is None:
            continue

        normalized_rel = f".scripts/{skill_name}/scripts/{script_file}"
        dest_path = (cwd / normalized_rel).resolve()
        try:
            _copy_if_missing(source_path, dest_path)
        except Exception as exc:
            raise RuntimeError(f"could not copy '{source_path}' -> '{dest_path}': {exc}") from exc

        if normalized_rel not in materialized:
            materialized.append(normalized_rel)

        # Normalize absolute /workspace/run/artifacts/.scripts/... references to relative.
        if raw_path.startswith("/workspace/run/artifacts/.scripts/"):
            rewritten = rewritten.replace(raw_path, normalized_rel)

    return rewritten, materialized
