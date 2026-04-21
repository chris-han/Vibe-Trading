from __future__ import annotations

from pathlib import Path

from runtime_env import get_runs_dir, get_sessions_dir, get_swarm_root, get_swarm_runs_dir, get_uploads_dir
from src.auth.workspace import ensure_workspace, workspace_paths, workspace_runs_dir, workspace_sessions_dir, workspace_swarm_dir, workspace_swarm_runs_dir, workspace_uploads_dir


def test_workspace_paths_use_hidden_swarm_dir(tmp_path: Path):
    paths = workspace_paths(tmp_path, "alice_zhang")

    assert paths.swarm_dir == workspace_swarm_dir(tmp_path / "alice_zhang")


def test_swarm_helpers_use_hidden_runs_dir(tmp_path: Path):
    agent_root = tmp_path / "alice_zhang"

    assert get_runs_dir(tmp_path) == tmp_path / "runs"
    assert get_sessions_dir(tmp_path) == tmp_path / "sessions"
    assert get_swarm_root(tmp_path) == tmp_path / ".swarm"
    assert get_swarm_runs_dir(tmp_path) == tmp_path / ".swarm" / "runs"
    assert get_uploads_dir(tmp_path) == tmp_path / "uploads"
    assert workspace_runs_dir(agent_root) == agent_root / "runs"
    assert workspace_sessions_dir(agent_root) == agent_root / "sessions"
    assert workspace_swarm_runs_dir(agent_root) == agent_root / ".swarm" / "runs"
    assert workspace_uploads_dir(agent_root) == agent_root / "uploads"


def test_ensure_workspace_preserves_existing_hidden_swarm_dir(tmp_path: Path):
    workspace_root = tmp_path / "alice_zhang"
    hidden_swarm_runs = workspace_swarm_dir(workspace_root) / "runs" / "swarm-123"
    hidden_swarm_runs.mkdir(parents=True)
    hidden_run_file = hidden_swarm_runs / "run.json"
    hidden_run_file.write_text('{"status":"completed"}\n', encoding="utf-8")

    template_hermes_home = tmp_path / "template-hermes"
    template_hermes_home.mkdir(parents=True)

    paths = ensure_workspace(tmp_path, "alice_zhang", template_hermes_home)

    assert paths.swarm_dir == workspace_swarm_dir(workspace_root)
    assert hidden_run_file.exists()


def test_ensure_workspace_uses_workspace_id_for_storage_root(tmp_path: Path):
    template_hermes_home = tmp_path / "template-hermes"
    template_hermes_home.mkdir(parents=True)

    paths = ensure_workspace(
        tmp_path,
        "user-123",
        template_hermes_home,
        workspace_slug="alice_zhang",
    )

    assert paths.workspace_root == tmp_path / "user-123"
    assert paths.workspace_slug == "alice_zhang"
    assert not (tmp_path / "alice_zhang").exists()


def test_ensure_workspace_does_not_copy_template_skills_or_plugins(tmp_path: Path):
    template_hermes_home = tmp_path / "template-hermes"
    template_skill = template_hermes_home / "skills" / "research" / "starter-skill" / "SKILL.md"
    template_plugin = template_hermes_home / "plugins" / "starter-plugin" / "plugin.yaml"
    template_skill.parent.mkdir(parents=True)
    template_plugin.parent.mkdir(parents=True)
    template_skill.write_text("# starter\n", encoding="utf-8")
    template_plugin.write_text("name: starter-plugin\n", encoding="utf-8")

    paths = ensure_workspace(tmp_path, "alice_zhang", template_hermes_home)

    assert not (paths.hermes_home / "skills" / "research" / "starter-skill" / "SKILL.md").exists()
    assert not (paths.hermes_home / "plugins").exists()


def test_ensure_workspace_preserves_existing_local_user_skills(tmp_path: Path):
    template_hermes_home = tmp_path / "template-hermes"
    template_skill = template_hermes_home / "skills" / "research" / "starter-skill" / "SKILL.md"
    template_skill.parent.mkdir(parents=True)
    template_skill.write_text("# starter\n", encoding="utf-8")

    paths = ensure_workspace(tmp_path, "alice_zhang", template_hermes_home)
    user_skill = paths.hermes_home / "skills" / "research" / "starter-skill" / "SKILL.md"
    user_skill.parent.mkdir(parents=True, exist_ok=True)
    user_skill.write_text("# user-customized\n", encoding="utf-8")

    ensure_workspace(tmp_path, "alice_zhang", template_hermes_home)

    assert user_skill.read_text(encoding="utf-8") == "# user-customized\n"


def test_ensure_workspace_merges_template_external_skill_dirs(tmp_path: Path):
    template_hermes_home = tmp_path / "template-hermes"
    template_hermes_home.mkdir(parents=True)
    (template_hermes_home / "config.yaml").write_text(
        "skills:\n  external_dirs:\n    - ${VIBE_TRADING_ROOT}/agent/src/skills\n    - ${VIBE_TRADING_ROOT}/hermes-agent/skills\n",
        encoding="utf-8",
    )

    workspace_home = tmp_path / "alice_zhang" / ".hermes"
    workspace_home.mkdir(parents=True)
    (workspace_home / "config.yaml").write_text(
        "skills:\n  external_dirs:\n    - /custom/user/skills\n",
        encoding="utf-8",
    )

    paths = ensure_workspace(tmp_path, "alice_zhang", template_hermes_home)
    config_text = (paths.hermes_home / "config.yaml").read_text(encoding="utf-8")

    assert "/custom/user/skills" in config_text
    assert "${VIBE_TRADING_ROOT}/agent/src/skills" in config_text
    assert "${VIBE_TRADING_ROOT}/hermes-agent/skills" in config_text


def test_ensure_workspace_does_not_create_plugins_dir(tmp_path: Path):
    template_hermes_home = tmp_path / "template-hermes"
    template_hermes_home.mkdir(parents=True)

    paths = ensure_workspace(tmp_path, "alice_zhang", template_hermes_home)

    assert not (paths.hermes_home / "plugins").exists()


def test_ensure_workspace_does_not_create_workspace_uploads_dir(tmp_path: Path):
    template_hermes_home = tmp_path / "template-hermes"
    template_hermes_home.mkdir(parents=True)

    paths = ensure_workspace(tmp_path, "alice_zhang", template_hermes_home)

    assert paths.uploads_dir == paths.agent_root / "uploads"
    assert not paths.uploads_dir.exists()