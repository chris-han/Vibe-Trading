"""Workspace provisioning helpers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class WorkspacePaths:
    workspace_id: str
    workspace_slug: str
    workspace_root: Path
    agent_root: Path
    hermes_home: Path
    sessions_dir: Path
    runs_dir: Path
    uploads_dir: Path
    swarm_dir: Path


def workspace_swarm_dir(agent_root: Path) -> Path:
    """Return the canonical swarm storage root for a workspace agent dir."""
    return agent_root / ".swarm"


def workspace_sessions_dir(agent_root: Path) -> Path:
    """Return the canonical session storage directory for a workspace agent dir."""
    return agent_root / "sessions"


def workspace_runs_dir(agent_root: Path) -> Path:
    """Return the canonical run storage directory for a workspace agent dir."""
    return agent_root / "runs"


def workspace_uploads_dir(agent_root: Path) -> Path:
    """Return the canonical uploads storage directory for a workspace agent dir."""
    return agent_root / "uploads"


def workspace_swarm_runs_dir(agent_root: Path) -> Path:
    """Return the canonical swarm runs directory for a workspace agent dir."""
    return workspace_swarm_dir(agent_root) / "runs"


def legacy_workspace_swarm_dir(agent_root: Path) -> Path:
    """Return the pre-refactor swarm storage root for a workspace agent dir."""
    return agent_root / "swarm"


def _merge_directory_contents(source_dir: Path, target_dir: Path) -> None:
    """Recursively merge source contents into target without overwriting existing files."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in source_dir.iterdir():
        destination = target_dir / child.name
        if child.is_dir():
            if destination.exists() and destination.is_dir():
                _merge_directory_contents(child, destination)
                try:
                    child.rmdir()
                except OSError:
                    pass
                continue
            shutil.move(str(child), str(destination))
            continue

        if destination.exists():
            continue
        shutil.move(str(child), str(destination))


def _load_yaml_mapping(path: Path) -> dict:
    """Load a YAML mapping file, returning an empty dict for invalid payloads."""
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _merge_external_skill_dirs(config_dest: Path, config_src: Path) -> None:
    """Ensure workspace config keeps the shared template external skill dirs."""
    if not config_src.exists():
        return
    if not config_dest.exists():
        shutil.copy2(config_src, config_dest)
        return

    template_config = _load_yaml_mapping(config_src)
    workspace_config = _load_yaml_mapping(config_dest)
    template_skills = template_config.get("skills")
    if not isinstance(template_skills, dict):
        return

    template_external_dirs = template_skills.get("external_dirs")
    if isinstance(template_external_dirs, str):
        template_external_dirs = [template_external_dirs]
    if not isinstance(template_external_dirs, list):
        return

    normalized_template_dirs = []
    seen = set()
    for entry in template_external_dirs:
        value = str(entry).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized_template_dirs.append(value)
    if not normalized_template_dirs:
        return

    workspace_skills = workspace_config.get("skills")
    if not isinstance(workspace_skills, dict):
        workspace_skills = {}
    workspace_external_dirs = workspace_skills.get("external_dirs")
    if isinstance(workspace_external_dirs, str):
        workspace_external_dirs = [workspace_external_dirs]
    elif not isinstance(workspace_external_dirs, list):
        workspace_external_dirs = []

    merged_external_dirs = []
    seen = set()
    for entry in [*workspace_external_dirs, *normalized_template_dirs]:
        value = str(entry).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        merged_external_dirs.append(value)

    if merged_external_dirs == workspace_external_dirs:
        return

    workspace_skills["external_dirs"] = merged_external_dirs
    workspace_config["skills"] = workspace_skills
    config_dest.write_text(yaml.safe_dump(workspace_config, sort_keys=False), encoding="utf-8")


def migrate_workspace_swarm_dir(agent_root: Path) -> Path:
    """Move legacy workspace swarm data from swarm/ into the canonical .swarm/."""
    target_swarm_dir = workspace_swarm_dir(agent_root)
    legacy_swarm_dir = legacy_workspace_swarm_dir(agent_root)
    if not legacy_swarm_dir.exists() or legacy_swarm_dir == target_swarm_dir:
        return

    if not target_swarm_dir.exists():
        legacy_swarm_dir.rename(target_swarm_dir)
        return target_swarm_dir

    _merge_directory_contents(legacy_swarm_dir, target_swarm_dir)

    try:
        legacy_swarm_dir.rmdir()
    except OSError:
        pass

    return target_swarm_dir


def _migrate_workspace_root(base_dir: Path, workspace_id: str, legacy_workspace_slug: str | None) -> None:
    """Move or merge a legacy slug-keyed workspace into the user-id workspace."""
    legacy_slug = (legacy_workspace_slug or "").strip()
    if not legacy_slug or legacy_slug == workspace_id:
        return

    target_root = base_dir / workspace_id
    legacy_root = base_dir / legacy_slug
    if not legacy_root.exists() or legacy_root == target_root:
        return

    if not target_root.exists():
        legacy_root.rename(target_root)
        return

    _merge_directory_contents(legacy_root, target_root)
    try:
        legacy_root.rmdir()
    except OSError:
        pass


def workspace_paths(base_dir: Path, workspace_id: str, workspace_slug: str | None = None) -> WorkspacePaths:
    workspace_root = base_dir / workspace_id
    agent_root = workspace_root
    return WorkspacePaths(
        workspace_id=workspace_id,
        workspace_slug=(workspace_slug or workspace_id),
        workspace_root=workspace_root,
        agent_root=agent_root,
        hermes_home=agent_root / ".hermes",
        sessions_dir=workspace_sessions_dir(agent_root),
        runs_dir=workspace_runs_dir(agent_root),
        uploads_dir=workspace_uploads_dir(agent_root),
        swarm_dir=workspace_swarm_dir(agent_root),
    )


def ensure_workspace(
    base_dir: Path,
    workspace_id: str,
    template_hermes_home: Path,
    *,
    workspace_slug: str | None = None,
    legacy_workspace_slug: str | None = None,
) -> WorkspacePaths:
    _migrate_workspace_root(base_dir, workspace_id, legacy_workspace_slug)
    paths = workspace_paths(base_dir, workspace_id, workspace_slug)
    migrate_workspace_swarm_dir(paths.agent_root)
    for directory in (
        paths.agent_root,
        paths.hermes_home,
        paths.sessions_dir,
        paths.runs_dir,
        paths.swarm_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    config_src = template_hermes_home / "config.yaml"
    config_dest = paths.hermes_home / "config.yaml"
    _merge_external_skill_dirs(config_dest, config_src)

    env_src = template_hermes_home / ".env"
    env_dest = paths.hermes_home / ".env"
    if env_src.exists() and not env_dest.exists():
        shutil.copy2(env_src, env_dest)

    for child in ("skills", "memories", "logs", "home", "profiles"):
        (paths.hermes_home / child).mkdir(parents=True, exist_ok=True)

    return paths
