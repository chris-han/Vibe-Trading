import asyncio
import sys
import types

from hermes_constants import get_hermes_home
from src.session.events import EventBus
from src.session.models import Attempt
from src.session.models import AttemptStatus
from src.session.store import SessionStore
from src.session.service import SessionService


def test_run_with_agent_uses_workspace_hermes_home(tmp_path, monkeypatch):
    repo_root = tmp_path / 'repo'
    hermes_home = tmp_path / 'workspace' / '.hermes'
    hermes_home.mkdir(parents=True)

    captured: dict[str, str] = {}

    fake_run_agent = types.ModuleType('run_agent')

    class FakeAIAgent:
        def __init__(self, **kwargs):
            pass

        def run_conversation(self, **kwargs):
            captured['hermes_home'] = str(get_hermes_home())
            return {'final_response': 'workspace skill inventory active'}

    fake_run_agent.AIAgent = FakeAIAgent
    monkeypatch.setitem(sys.modules, 'run_agent', fake_run_agent)

    fake_state_module = types.ModuleType('src.core.state')

    class FakeRunStateStore:
        def create_run_dir(self, runs_dir):
            run_dir = runs_dir / 'run-1'
            run_dir.mkdir(parents=True, exist_ok=True)
            return run_dir

        def save_request(self, run_dir, prompt, metadata):
            return None

        def mark_success(self, run_dir):
            return None

        def mark_failure(self, run_dir, reason):
            return None

    fake_state_module.RunStateStore = FakeRunStateStore
    monkeypatch.setitem(sys.modules, 'src.core.state', fake_state_module)

    monkeypatch.setattr(
        'src.session.service.prepare_hermes_project_context',
        lambda chdir=False: repo_root,
    )
    monkeypatch.setattr('src.session.service.ensure_runtime_env', lambda: None)
    monkeypatch.setattr('src.session.service.get_hermes_agent_kwargs', lambda: {})
    monkeypatch.setattr('src.session.service.build_session_runtime_prompt', lambda *args: '')
    monkeypatch.setattr('src.session.service.is_backtest_prompt', lambda prompt: False)

    store = SessionStore(tmp_path / 'sessions')
    event_bus = EventBus()
    service = SessionService(
        store=store,
        event_bus=event_bus,
        runs_dir=tmp_path / 'runs',
        hermes_home=hermes_home,
    )
    session = service.create_session()
    attempt = Attempt(session_id=session.session_id, prompt='list workspace skills')

    result = asyncio.run(service._run_with_agent(attempt, messages=[]))

    assert result['status'] == 'success'
    assert captured['hermes_home'] == str(hermes_home)



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


def test_reportable_tool_result_accepts_successful_document_reads():
    parsed = {"status": "ok", "file": "earnings.pdf", "text": "Revenue increased 17%."}

    assert SessionService._is_reportable_tool_result("read_document", parsed) is True


def test_reportable_tool_result_rejects_non_document_tools():
    parsed = {"status": "ok", "message": "done"}

    assert SessionService._is_reportable_tool_result("search_files", parsed) is False


def test_format_result_message_appends_full_report_link_for_completed_attempt(tmp_path):
    run_dir = tmp_path / 'runs' / '20260422_010101_aa11'
    run_dir.mkdir(parents=True)

    attempt = Attempt(session_id='s1', prompt='p')
    attempt.status = AttemptStatus.COMPLETED
    attempt.summary = 'Execution complete.'
    attempt.run_dir = str(run_dir)

    result = SessionService._format_result_message(attempt)

    assert 'Execution complete.' in result
    assert '[Full report](/runs/20260422_010101_aa11)' in result
    assert f'Run directory: {run_dir}' in result


def test_format_result_message_keeps_failure_text_and_report_link(tmp_path):
    run_dir = tmp_path / 'runs' / '20260422_010101_bb22'
    run_dir.mkdir(parents=True)

    attempt = Attempt(session_id='s1', prompt='p')
    attempt.status = AttemptStatus.FAILED
    attempt.error = 'tool crashed'
    attempt.run_dir = str(run_dir)

    result = SessionService._format_result_message(attempt)

    assert 'Execution failed: tool crashed' in result
    assert '[Full report](/runs/20260422_010101_bb22)' in result
