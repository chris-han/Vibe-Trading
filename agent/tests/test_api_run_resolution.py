from pathlib import Path
from types import SimpleNamespace

import api_server
from fastapi.testclient import TestClient


def test_resolve_run_dir_falls_back_to_legacy_root(tmp_path: Path, monkeypatch):
    configured_runs = tmp_path / "chris" / "runs"
    configured_runs.mkdir(parents=True)

    legacy_runs = tmp_path / "runs"
    expected = legacy_runs / "20260412_081103_28_cf78e7"
    expected.mkdir(parents=True)

    monkeypatch.setattr(api_server, "RUNS_DIR", configured_runs)
    monkeypatch.setattr(api_server, "LEGACY_RUNS_DIR", legacy_runs)

    resolved = api_server._resolve_run_dir(expected.name)

    assert resolved == expected


def test_collect_run_dirs_prefers_primary_root_on_duplicates(tmp_path: Path, monkeypatch):
    configured_runs = tmp_path / "chris" / "runs"
    legacy_runs = tmp_path / "runs"

    preferred = configured_runs / "shared_run"
    fallback = legacy_runs / "shared_run"
    unique_legacy = legacy_runs / "legacy_only"

    preferred.mkdir(parents=True)
    fallback.mkdir(parents=True)
    unique_legacy.mkdir(parents=True)

    monkeypatch.setattr(api_server, "RUNS_DIR", configured_runs)
    monkeypatch.setattr(api_server, "LEGACY_RUNS_DIR", legacy_runs)

    run_dirs = api_server._collect_run_dirs()
    by_name = {d.name: d for d in run_dirs}

    assert by_name["shared_run"] == preferred
    assert by_name["legacy_only"] == unique_legacy


def test_workspace_run_lookup_falls_back_to_global_runs_root(tmp_path: Path, monkeypatch):
    workspace_runs = tmp_path / "workspaces" / "chris_han" / "agent" / "runs"
    global_runs = tmp_path / "chris" / "runs"

    expected = global_runs / "20260415_203540_20_cbe68a"
    expected.mkdir(parents=True)

    monkeypatch.setattr(api_server, "RUNS_DIR", global_runs)
    monkeypatch.setattr(api_server, "LEGACY_RUNS_DIR", tmp_path / "agent" / "runs")

    resolved = api_server._resolve_run_dir(expected.name, runs_dir=workspace_runs)

    assert resolved == expected


def test_get_run_result_returns_report_from_fallback_global_run(tmp_path: Path, monkeypatch):
    workspace_runs = tmp_path / "workspaces" / "chris_han" / "agent" / "runs"
    workspace_sessions = tmp_path / "workspaces" / "chris_han" / "agent" / "sessions"
    global_runs = tmp_path / "chris" / "runs"

    run_dir = global_runs / "20260415_203540_20_cbe68a"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text('{"status": "success"}', encoding="utf-8")
    (run_dir / "req.json").write_text('{"prompt": "summarize the uploaded report"}', encoding="utf-8")
    (run_dir / "report.md").write_text("# Full report\n\nRecovered from the fallback run root.", encoding="utf-8")

    monkeypatch.setattr(api_server, "RUNS_DIR", global_runs)
    monkeypatch.setattr(api_server, "LEGACY_RUNS_DIR", tmp_path / "agent" / "runs")
    monkeypatch.setattr(
        api_server,
        "_resolve_request_context",
        lambda request, require_login=False: SimpleNamespace(
            workspace=SimpleNamespace(runs_dir=workspace_runs, sessions_dir=workspace_sessions)
        ),
    )

    client = TestClient(api_server.app)
    response = client.get(f"/runs/{run_dir.name}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] == run_dir.name
    assert body["run_directory"] == str(run_dir)
    assert body["report_markdown"] == "# Full report\n\nRecovered from the fallback run root."
