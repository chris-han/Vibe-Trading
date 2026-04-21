from pathlib import Path
from types import SimpleNamespace

import api_server
from fastapi.testclient import TestClient
from src.ui_services import load_run_report


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


def test_load_run_report_synthesizes_backtest_report_from_metrics(tmp_path: Path):
    run_dir = tmp_path / "runs" / "20260421_171206_49_2cfa61"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)

    (run_dir / "req.json").write_text(
        '{"prompt": "Backtest a risk-parity portfolio of MSFT, BTC-USDT, and AAPL for full-year 2025"}',
        encoding="utf-8",
    )
    (artifacts_dir / "metrics.csv").write_text(
        "final_value,total_return,annual_return,max_drawdown,sharpe,trade_count,benchmark_return,excess_return\n"
        "1003372.3238935024,0.0033723238935023936,0.0013827073249346178,-0.05654206268889818,0.05382347424523173,57,0.092701,-0.089329\n",
        encoding="utf-8",
    )

    report = load_run_report(run_dir)

    assert report is not None
    assert "# Backtest Report" in report
    assert "risk-parity portfolio" in report
    assert "57" in report
    assert "-8.93%" in report
