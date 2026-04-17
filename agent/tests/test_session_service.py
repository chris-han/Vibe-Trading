from src.session.service import SessionService


def test_extract_useful_tool_output_prefers_swarm_final_report():
    parsed = {
        "status": "completed",
        "run_id": "swarm-123",
        "final_report": "# NVDA committee verdict\n\nInitiate a 6% long position.",
    }

    result = SessionService._extract_useful_tool_output("run_swarm", parsed, "")

    assert result == "# NVDA committee verdict\n\nInitiate a 6% long position."


def test_extract_useful_tool_output_builds_swarm_summary_from_tasks():
    parsed = {
        "status": "completed",
        "tasks": [
            {"agent_id": "bull_advocate", "summary": "Bull case favors upside."},
            {"agent_id": "risk_officer", "summary": "Risk should stay capped at 6%."},
        ],
    }

    result = SessionService._extract_useful_tool_output("run_swarm", parsed, "")

    assert "### bull_advocate" in result
    assert "Bull case favors upside." in result
    assert "### risk_officer" in result
    assert "Risk should stay capped at 6%." in result


def test_has_run_artifact_requires_metrics_or_saved_report(tmp_path):
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)

    assert SessionService._has_run_artifact(str(run_dir), None) is False

    (run_dir / "report.md").write_text("hello\n", encoding="utf-8")
    assert SessionService._has_run_artifact(str(run_dir), None) is True


def test_has_run_artifact_accepts_metrics_without_report(tmp_path):
    run_dir = tmp_path / "runs" / "r2"
    run_dir.mkdir(parents=True)

    assert SessionService._has_run_artifact(str(run_dir), {"sharpe": 1.2}) is True
