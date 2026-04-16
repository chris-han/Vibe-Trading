"""Workspace provisioning helpers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspacePaths:
    workspace_slug: str
    workspace_root: Path
    agent_root: Path
    hermes_home: Path
    sessions_dir: Path
    runs_dir: Path
    uploads_dir: Path
    swarm_dir: Path


def workspace_paths(base_dir: Path, workspace_slug: str) -> WorkspacePaths:
    workspace_root = base_dir / workspace_slug
    agent_root = workspace_root / "agent"
    return WorkspacePaths(
        workspace_slug=workspace_slug,
        workspace_root=workspace_root,
        agent_root=agent_root,
        hermes_home=agent_root / ".hermes",
        sessions_dir=agent_root / "sessions",
        runs_dir=agent_root / "runs",
        uploads_dir=agent_root / "uploads",
        swarm_dir=agent_root / "swarm",
    )


def ensure_workspace(base_dir: Path, workspace_slug: str, template_hermes_home: Path) -> WorkspacePaths:
    paths = workspace_paths(base_dir, workspace_slug)
    for directory in (
        paths.agent_root,
        paths.hermes_home,
        paths.sessions_dir,
        paths.runs_dir,
        paths.uploads_dir,
        paths.swarm_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    config_src = template_hermes_home / "config.yaml"
    config_dest = paths.hermes_home / "config.yaml"
    if config_src.exists() and not config_dest.exists():
        shutil.copy2(config_src, config_dest)

    env_src = template_hermes_home / ".env"
    env_dest = paths.hermes_home / ".env"
    if env_src.exists() and not env_dest.exists():
        shutil.copy2(env_src, env_dest)

    for child in ("skills", "plugins", "memories", "logs", "home", "profiles"):
        (paths.hermes_home / child).mkdir(parents=True, exist_ok=True)

    return paths
