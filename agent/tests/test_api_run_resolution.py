from pathlib import Path
from types import SimpleNamespace

import api_server
from fastapi.testclient import TestClient


def test_resolve_run_dir_uses_configured_root(tmp_path: Path, monkeypatch):
    configured_runs = tmp_path / "chris" / "runs"
    configured_runs.mkdir(parents=True)

    expected = configured_runs / "20260412_081103_28_cf78e7"
    expected.mkdir(parents=True)

    monkeypatch.setattr(api_server, "RUNS_DIR", configured_runs)

    resolved = api_server._resolve_run_dir(expected.name)

    assert resolved == expected


def test_collect_run_dirs_includes_session_scoped_runs(tmp_path: Path, monkeypatch):
    configured_runs = tmp_path / "chris" / "runs"
    session_runs = tmp_path / "chris" / "sessions" / "sess-1" / "runs"

    preferred = configured_runs / "shared_run"
    nested = session_runs / "nested_run"

    preferred.mkdir(parents=True)
    nested.mkdir(parents=True)

    monkeypatch.setattr(api_server, "RUNS_DIR", configured_runs)

    run_dirs = api_server._collect_run_dirs(sessions_dir=tmp_path / "chris" / "sessions")
    by_name = {d.name: d for d in run_dirs}

    assert by_name["shared_run"] == preferred
    assert by_name["nested_run"] == nested


def test_workspace_run_lookup_does_not_fall_back_to_public_root(tmp_path: Path, monkeypatch):
    workspace_runs = tmp_path / "workspaces" / "chris_han" / "runs"
    global_runs = tmp_path / "chris" / "runs"

    expected = global_runs / "20260415_203540_20_cbe68a"
    expected.mkdir(parents=True)

    monkeypatch.setattr(api_server, "RUNS_DIR", global_runs)

    resolved = api_server._resolve_run_dir(expected.name, runs_dir=workspace_runs)

    assert resolved is None


def test_get_run_result_returns_404_when_run_only_exists_in_public_root(tmp_path: Path, monkeypatch):
    workspace_runs = tmp_path / "workspaces" / "chris_han" / "runs"
    workspace_sessions = tmp_path / "workspaces" / "chris_han" / "sessions"
    global_runs = tmp_path / "chris" / "runs"

    run_dir = global_runs / "20260415_203540_20_cbe68a"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text('{"status": "success"}', encoding="utf-8")
    (run_dir / "req.json").write_text('{"prompt": "summarize the uploaded report"}', encoding="utf-8")
    (run_dir / "report.md").write_text("# Full report\n\nRecovered from the fallback run root.", encoding="utf-8")

    monkeypatch.setattr(api_server, "RUNS_DIR", global_runs)
    monkeypatch.setattr(
        api_server,
        "_resolve_request_context",
        lambda request, require_login=False: SimpleNamespace(
            workspace=SimpleNamespace(runs_dir=workspace_runs, sessions_dir=workspace_sessions)
        ),
    )

    client = TestClient(api_server.app)
    response = client.get(f"/runs/{run_dir.name}")

    assert response.status_code == 404, response.text
