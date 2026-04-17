from __future__ import annotations

from pathlib import Path

from runtime_env import get_runs_dir, get_sessions_dir, get_swarm_root, get_swarm_runs_dir, get_uploads_dir
from src.auth.workspace import ensure_workspace, legacy_workspace_swarm_dir, workspace_paths, workspace_runs_dir, workspace_sessions_dir, workspace_swarm_dir, workspace_swarm_runs_dir, workspace_uploads_dir


def test_workspace_paths_use_hidden_swarm_dir(tmp_path: Path):
    paths = workspace_paths(tmp_path, "alice_zhang")

    assert paths.swarm_dir == workspace_swarm_dir(tmp_path / "alice_zhang" / "agent")


def test_swarm_helpers_use_hidden_runs_dir(tmp_path: Path):
    agent_root = tmp_path / "alice_zhang" / "agent"

    assert get_runs_dir(tmp_path) == tmp_path / "runs"
    assert get_sessions_dir(tmp_path) == tmp_path / "sessions"
    assert get_swarm_root(tmp_path) == tmp_path / ".swarm"
    assert get_swarm_runs_dir(tmp_path) == tmp_path / ".swarm" / "runs"
    assert get_uploads_dir(tmp_path) == tmp_path / "uploads"
    assert workspace_runs_dir(agent_root) == agent_root / "runs"
    assert workspace_sessions_dir(agent_root) == agent_root / "sessions"
    assert workspace_swarm_runs_dir(agent_root) == agent_root / ".swarm" / "runs"
    assert workspace_uploads_dir(agent_root) == agent_root / "uploads"


def test_ensure_workspace_migrates_legacy_swarm_directory(tmp_path: Path):
    workspace_root = tmp_path / "alice_zhang" / "agent"
    legacy_swarm_runs = legacy_workspace_swarm_dir(workspace_root) / "runs" / "swarm-123"
    legacy_swarm_runs.mkdir(parents=True)
    legacy_run_file = legacy_swarm_runs / "run.json"
    legacy_run_file.write_text('{"status":"completed"}\n', encoding="utf-8")

    template_hermes_home = tmp_path / "template-hermes"
    template_hermes_home.mkdir(parents=True)
    (template_hermes_home / "config.yaml").write_text("model: {}\n", encoding="utf-8")

    paths = ensure_workspace(tmp_path, "alice_zhang", template_hermes_home)

    assert paths.swarm_dir == workspace_swarm_dir(workspace_root)
    assert not legacy_workspace_swarm_dir(workspace_root).exists()
    assert (paths.swarm_dir / "runs" / "swarm-123" / "run.json").read_text(encoding="utf-8") == '{"status":"completed"}\n'


def test_ensure_workspace_preserves_existing_hidden_swarm_dir(tmp_path: Path):
    workspace_root = tmp_path / "alice_zhang" / "agent"
    hidden_swarm_runs = workspace_swarm_dir(workspace_root) / "runs" / "swarm-123"
    hidden_swarm_runs.mkdir(parents=True)
    hidden_run_file = hidden_swarm_runs / "run.json"
    hidden_run_file.write_text('{"status":"completed"}\n', encoding="utf-8")

    template_hermes_home = tmp_path / "template-hermes"
    template_hermes_home.mkdir(parents=True)

    paths = ensure_workspace(tmp_path, "alice_zhang", template_hermes_home)

    assert paths.swarm_dir == workspace_swarm_dir(workspace_root)
    assert hidden_run_file.exists()


def test_ensure_workspace_merges_legacy_and_hidden_swarm_runs(tmp_path: Path):
    workspace_root = tmp_path / "alice_zhang" / "agent"
    hidden_run_file = workspace_swarm_dir(workspace_root) / "runs" / "swarm-hidden" / "run.json"
    hidden_run_file.parent.mkdir(parents=True)
    hidden_run_file.write_text('{"status":"hidden"}\n', encoding="utf-8")

    legacy_run_file = legacy_workspace_swarm_dir(workspace_root) / "runs" / "swarm-legacy" / "run.json"
    legacy_run_file.parent.mkdir(parents=True)
    legacy_run_file.write_text('{"status":"legacy"}\n', encoding="utf-8")

    template_hermes_home = tmp_path / "template-hermes"
    template_hermes_home.mkdir(parents=True)

    paths = ensure_workspace(tmp_path, "alice_zhang", template_hermes_home)

    assert paths.swarm_dir == workspace_swarm_dir(workspace_root)
    assert (paths.swarm_dir / "runs" / "swarm-hidden" / "run.json").read_text(encoding="utf-8") == '{"status":"hidden"}\n'
    assert (paths.swarm_dir / "runs" / "swarm-legacy" / "run.json").read_text(encoding="utf-8") == '{"status":"legacy"}\n'
    assert not legacy_workspace_swarm_dir(workspace_root).exists()