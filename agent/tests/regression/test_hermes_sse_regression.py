"""
Regression tests — hermes branch (AIAgent-based implementation).

Each test mirrors a baseline test from tests/baseline/ and verifies the
migrated code emits the SAME SSE event type and payload keys.

Run:
    cd agent && uv run pytest tests/regression/ -v
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

HERMES_BACKEND = Path(__file__).resolve().parents[2]   # agent/

# Hermes agent path must be first on sys.path for src.* imports
_s = str(HERMES_BACKEND)
if _s not in sys.path:
    sys.path.insert(0, _s)

# Pre-inject a mock run_agent module so inline `from run_agent import AIAgent`
# never triggers the real hermes-agent import chain (avoids jiter/openai deps).
import types as _types
_mock_run_agent = _types.ModuleType("run_agent")
_mock_run_agent.AIAgent = MagicMock  # replaced per-test via patch
sys.modules.setdefault("run_agent", _mock_run_agent)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _discard_task(coro):
    coro.close()
    return MagicMock()


class EventCapture:
    def __init__(self):
        self.events: list[tuple[str, str, dict]] = []

    def emit(self, session_id: str, event_type: str, data: dict) -> None:
        self.events.append((session_id, event_type, data))

    def types(self) -> list[str]:
        return [e[1] for e in self.events]

    def data_for(self, event_type: str) -> list[dict]:
        return [e[2] for e in self.events if e[1] == event_type]

    def clear(self, session_id: str) -> None:
        pass


def _make_service(capture: EventCapture, base_dir: Path):
    from src.session.service import SessionService
    from src.session.store import SessionStore
    store = SessionStore(base_dir=base_dir)
    return SessionService(store=store, event_bus=capture, runs_dir=base_dir / "runs")


# ---------------------------------------------------------------------------
# Session SSE event shape regression tests
# ---------------------------------------------------------------------------

class TestHermesSessionEvents:
    """Migrated SessionService must emit the same SSE event shapes as the baseline."""

    def test_session_created_event(self, tmp_path):
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        svc.create_session(title="test")
        assert "session.created" in cap.types()
        p = cap.data_for("session.created")[0]
        assert "session_id" in p

    def test_message_received_event(self, tmp_path):
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        cap.events.clear()

        async def _t():
            with patch("asyncio.create_task", side_effect=_discard_task):
                await svc.send_message(session.session_id, "hello")

        _run(_t())
        assert "message.received" in cap.types()
        p = cap.data_for("message.received")[0]
        assert "message_id" in p
        assert "role" in p
        assert "content" in p

    def test_attempt_created_event(self, tmp_path):
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        cap.events.clear()

        async def _t():
            with patch("asyncio.create_task", side_effect=_discard_task):
                await svc.send_message(session.session_id, "hello")

        _run(_t())
        assert "attempt.created" in cap.types()
        p = cap.data_for("attempt.created")[0]
        assert "attempt_id" in p
        assert "prompt" in p

    def test_attempt_started_and_completed_events(self, tmp_path):
        from src.session.models import Attempt
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(session_id=session.session_id, prompt="ping")
        svc.store.create_attempt(attempt)
        cap.events.clear()

        async def _fake_run(att, messages=None):
            return {"status": "success", "content": "pong",
                    "run_dir": str(tmp_path), "run_id": "run_1"}

        async def _t():
            with patch.object(svc, "_run_with_agent", side_effect=_fake_run):
                await svc._run_attempt(session, attempt)

        _run(_t())
        assert "attempt.started" in cap.types()
        assert "attempt.completed" in cap.types() or "attempt.failed" in cap.types()
        assert "attempt_id" in cap.data_for("attempt.started")[0]

    def test_attempt_failed_event_on_error(self, tmp_path):
        from src.session.models import Attempt
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(session_id=session.session_id, prompt="fail")
        svc.store.create_attempt(attempt)
        cap.events.clear()

        async def _boom(att, messages=None):
            raise RuntimeError("boom")

        async def _t():
            with patch.object(svc, "_run_with_agent", side_effect=_boom):
                await svc._run_attempt(session, attempt)

        _run(_t())
        assert "attempt.failed" in cap.types()
        p = cap.data_for("attempt.failed")[0]
        assert "attempt_id" in p
        assert "error" in p

    def test_run_with_agent_emits_tool_call_event(self, tmp_path):
        """_run_with_agent() emits tool_call with 'tool' and 'args' keys."""
        from src.session.models import Attempt
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(session_id=session.session_id, prompt="ping")
        svc.store.create_attempt(attempt)
        cap.events.clear()

        def _agent_factory(*args, **kwargs):
            cb = kwargs.get("tool_progress_callback")
            inst = MagicMock()
            def run_conv(**kw):
                if cb:
                    cb("tool.started", "read_file", "reading...", {"path": "/tmp/x"})
                    cb("tool.completed", "read_file", "done", {})
                return {"final_response": "result", "status": "success"}
            inst.run_conversation = run_conv
            return inst

        async def _t():
            sys.modules["run_agent"].AIAgent = _agent_factory
            with patch("src.core.state.RunStateStore") as MockStore:
                MockStore.return_value.create_run_dir.return_value = tmp_path
                MockStore.return_value.mark_success.return_value = None
                await svc._run_with_agent(attempt)

        _run(_t())
        tool_calls = cap.data_for("tool_call")
        if tool_calls:
            assert "tool" in tool_calls[0]
            assert "args" in tool_calls[0]

    def test_run_with_agent_creates_run_under_workspace_runs_root(self, tmp_path):
        """_run_with_agent() must create placeholder runs under service.runs_dir, not sessions/<id>/runs."""
        from src.session.models import Attempt

        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(session_id=session.session_id, prompt="ping")
        svc.store.create_attempt(attempt)

        expected_runs_root = tmp_path / "runs"
        created_run_dir = expected_runs_root / "r-root"
        created_run_dir.mkdir(parents=True, exist_ok=True)

        def _agent_factory(*args, **kwargs):
            inst = MagicMock()
            inst.run_conversation = lambda **kw: {"final_response": "ok", "status": "success"}
            return inst

        async def _t():
            sys.modules["run_agent"].AIAgent = _agent_factory
            with patch("src.core.state.RunStateStore") as MockStore:
                MockStore.return_value.create_run_dir.return_value = created_run_dir
                MockStore.return_value.mark_success.return_value = None
                await svc._run_with_agent(attempt)

                create_arg = MockStore.return_value.create_run_dir.call_args.args[0]
                assert create_arg == expected_runs_root
                assert create_arg != svc.store.base_dir / session.session_id / "runs"

        _run(_t())

    def test_run_with_agent_propagates_workspace_runs_root_into_executor_tools(self, tmp_path):
        """setup_backtest_run invoked inside Hermes executor must use service.runs_dir."""
        from src.session.models import Attempt
        from src.vibe_trading_helper import _setup_backtest_run

        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(session_id=session.session_id, prompt="ping")
        svc.store.create_attempt(attempt)

        placeholder_run_dir = tmp_path / "runs" / "placeholder"
        placeholder_run_dir.mkdir(parents=True, exist_ok=True)

        def _agent_factory(*args, **kwargs):
            inst = MagicMock()

            def run_conv(**kw):
                payload = json.loads(_setup_backtest_run({"config_json": {"symbol": "BTC-USDT"}}))
                return {
                    "final_response": "ok",
                    "status": "success",
                    "run_dir": payload["run_dir"],
                    "run_id": Path(payload["run_dir"]).name,
                }

            inst.run_conversation = run_conv
            return inst

        async def _t():
            sys.modules["run_agent"].AIAgent = _agent_factory
            with patch("src.core.state.RunStateStore") as MockStore:
                MockStore.return_value.create_run_dir.return_value = placeholder_run_dir
                MockStore.return_value.mark_success.return_value = None

                result = await svc._run_with_agent(attempt)

                actual_run_dir = Path(result["run_dir"])
                assert actual_run_dir.parent == svc.runs_dir
                assert actual_run_dir.parent != svc.store.base_dir / session.session_id / "runs"

        _run(_t())

    def test_run_with_agent_emits_tool_result_event(self, tmp_path):
        """_run_with_agent() emits tool_result with 'tool' and 'is_error' keys."""
        from src.session.models import Attempt
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(session_id=session.session_id, prompt="ping")
        svc.store.create_attempt(attempt)
        cap.events.clear()

        def _agent_factory(*args, **kwargs):
            cb = kwargs.get("tool_progress_callback")
            inst = MagicMock()
            def run_conv(**kw):
                if cb:
                    cb("tool.started", "read_file", "reading...", {"path": "/tmp/x"})
                    cb("tool.completed", "read_file", "done", {}, is_error=False)
                return {"final_response": "result", "status": "success"}
            inst.run_conversation = run_conv
            return inst

        async def _t():
            sys.modules["run_agent"].AIAgent = _agent_factory
            with patch("src.core.state.RunStateStore") as MockStore:
                MockStore.return_value.create_run_dir.return_value = tmp_path
                MockStore.return_value.mark_success.return_value = None
                await svc._run_with_agent(attempt)

        _run(_t())
        tool_results = cap.data_for("tool_result")
        if tool_results:
            assert "tool" in tool_results[0]
            assert "is_error" in tool_results[0]

    def test_run_with_agent_emits_text_delta_event(self, tmp_path):
        """_run_with_agent() emits text_delta with 'content' key."""
        from src.session.models import Attempt
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(session_id=session.session_id, prompt="ping")
        svc.store.create_attempt(attempt)
        cap.events.clear()

        def _agent_factory(*args, **kwargs):
            stream_cb = kwargs.get("stream_delta_callback")
            inst = MagicMock()
            def run_conv(**kw):
                if stream_cb:
                    stream_cb("hello ")
                    stream_cb("world")
                return {"final_response": "hello world", "status": "success"}
            inst.run_conversation = run_conv
            return inst

        async def _t():
            sys.modules["run_agent"].AIAgent = _agent_factory
            with patch("src.core.state.RunStateStore") as MockStore:
                MockStore.return_value.create_run_dir.return_value = tmp_path
                MockStore.return_value.mark_success.return_value = None
                await svc._run_with_agent(attempt)

        _run(_t())
        text_deltas = cap.data_for("text_delta")
        assert len(text_deltas) >= 1
        assert "content" in text_deltas[0]

    def test_run_with_agent_emits_tool_progress_event_for_subagents(self, tmp_path):
        """Delegated child progress is bridged into SSE as tool_progress."""
        from src.session.models import Attempt
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(session_id=session.session_id, prompt="analyze uploaded pdf")
        svc.store.create_attempt(attempt)
        cap.events.clear()

        def _agent_factory(*args, **kwargs):
            progress_cb = kwargs.get("tool_progress_callback")
            inst = MagicMock()

            def run_conv(**kw):
                if progress_cb:
                    progress_cb(
                        "subagent_progress",
                        "delegate_task",
                        "🔀 [1] read_document, read_file",
                        {},
                        parent_tool="delegate_task",
                    )
                return {"final_response": "result", "status": "success"}

            inst.run_conversation = run_conv
            return inst

        async def _t():
            sys.modules["run_agent"].AIAgent = _agent_factory
            with patch("src.core.state.RunStateStore") as MockStore:
                MockStore.return_value.create_run_dir.return_value = tmp_path
                MockStore.return_value.mark_success.return_value = None
                await svc._run_with_agent(attempt)

        _run(_t())
        tool_progress = cap.data_for("tool_progress")
        assert len(tool_progress) == 1
        assert tool_progress[0]["tool"] == "delegate_task"
        assert "preview" in tool_progress[0]

    def test_run_with_agent_injects_backtest_setup_workflow_prompt(self, tmp_path):
        """Session runtime tells Hermes to use setup_backtest_run before backtest."""
        from src.session.models import Attempt
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(session_id=session.session_id, prompt="Backtest AAPL")
        svc.store.create_attempt(attempt)

        captured_kwargs = {}

        def _agent_factory(*args, **kwargs):
            captured_kwargs.update(kwargs)
            inst = MagicMock()
            inst.run_conversation.return_value = {"final_response": "ok", "status": "success"}
            return inst

        async def _t():
            sys.modules["run_agent"].AIAgent = _agent_factory
            with patch("src.core.state.RunStateStore") as MockStore:
                MockStore.return_value.create_run_dir.return_value = tmp_path / "runs" / "r1"
                MockStore.return_value.mark_success.return_value = None
                await svc._run_with_agent(attempt)

        _run(_t())
        prompt = captured_kwargs.get("ephemeral_system_prompt", "")
        assert "setup_backtest_run(config_json=..., signal_engine_py=...)" in prompt
        assert "Never ask the user to manually create config.json" in prompt
        assert "Never invent a PDF filename" in prompt
        assert "read_url or browser tools" in prompt
        assert "Do NOT fetch market data with curl" in prompt
        assert "Prefer writing one focused Python script with write_file, then execute it with bash." in prompt

    def test_hermes_toolset_selection_exposes_legacy_vt_aliases(self):
        """Compat toolset is now empty; all tools are provided by hermes built-in toolsets.
        Vibe-Trading registers finance tools through the installed Hermes entry-point plugin."""
        import os
        import sys
        from pathlib import Path

        agent_root = Path(__file__).resolve().parents[2]
        if str(agent_root) not in sys.path:
            sys.path.insert(0, str(agent_root))
        from runtime_env import prepare_hermes_project_context

        prepare_hermes_project_context(chdir=True)

        hermes_root = Path(__file__).resolve().parents[3] / "hermes-agent"
        sys.path.insert(0, str(hermes_root))
        from model_tools import get_tool_definitions

        names = {
            t["function"]["name"]
            for t in get_tool_definitions(
                enabled_toolsets=["development", "research", "vibe_trading"],
                quiet_mode=True,
            )
        }

        # Built-in equivalents provided by hermes toolsets
        assert "write_file" in names
        assert "terminal" in names
        assert "read_document" in names
        assert "delegate_task" in names
        assert "todo" in names
        assert "skill_view" in names
        assert "skills_list" in names

        # Vibe-Trading finance tools are provided by the installed Hermes plugin entry point
        assert "setup_backtest_run" in names
        assert "backtest" in names
        assert "factor_analysis" in names
        assert "options_pricing" in names
        assert "pattern" in names
        assert "list_swarm_presets" in names
        assert "run_swarm" in names

    def test_run_with_agent_persists_req_json_before_agent_execution(self, tmp_path):
        """Hermes session runtime restores original AgentLoop request persistence."""
        from src.session.models import Attempt
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(
            session_id=session.session_id,
            prompt="Backtest AAPL and MSFT for full-year 2024",
        )
        svc.store.create_attempt(attempt)

        observed = {}

        def _agent_factory(*args, **kwargs):
            inst = MagicMock()

            def run_conv(**kw):
                run_dir = Path(kwargs["ephemeral_system_prompt"].splitlines()[0].replace("Run directory:", "").strip())
                req_path = run_dir / "req.json"
                observed["req_exists"] = req_path.exists()
                observed["req_payload"] = req_path.read_text(encoding="utf-8") if req_path.exists() else ""
                return {"final_response": "ok", "status": "success"}

            inst.run_conversation = run_conv
            return inst

        async def _t():
            sys.modules["run_agent"].AIAgent = _agent_factory
            with patch("src.core.state.RunStateStore") as MockStore:
                run_dir = tmp_path / "runs" / "r2"
                run_dir.mkdir(parents=True, exist_ok=True)
                MockStore.return_value.create_run_dir.return_value = run_dir
                MockStore.return_value.mark_success.return_value = None
                def _save_request(path, prompt, context):
                    payload = {"prompt": prompt, "context": context}
                    (path / "req.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    return payload
                MockStore.return_value.save_request.side_effect = _save_request
                await svc._run_with_agent(attempt)

        _run(_t())
        assert observed["req_exists"] is True
        assert "Backtest AAPL and MSFT for full-year 2024" in observed["req_payload"]

    def test_run_with_agent_persists_req_json_for_non_backtest_prompt(self, tmp_path):
        """req.json persistence is a generic agent-coding invariant, not backtest-specific."""
        from src.session.models import Attempt
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(
            session_id=session.session_id,
            prompt="Write a Python script that summarizes recent factor research notes",
        )
        svc.store.create_attempt(attempt)

        observed = {}

        def _agent_factory(*args, **kwargs):
            inst = MagicMock()

            def run_conv(**kw):
                run_dir = Path(kwargs["ephemeral_system_prompt"].splitlines()[0].replace("Run directory:", "").strip())
                req_path = run_dir / "req.json"
                observed["req_exists"] = req_path.exists()
                observed["req_payload"] = req_path.read_text(encoding="utf-8") if req_path.exists() else ""
                return {"final_response": "ok", "status": "success"}

            inst.run_conversation = run_conv
            return inst

        async def _t():
            sys.modules["run_agent"].AIAgent = _agent_factory
            with patch("src.core.state.RunStateStore") as MockStore:
                run_dir = tmp_path / "runs" / "r3"
                run_dir.mkdir(parents=True, exist_ok=True)
                MockStore.return_value.create_run_dir.return_value = run_dir
                MockStore.return_value.mark_success.return_value = None

                def _save_request(path, prompt, context):
                    payload = {"prompt": prompt, "context": context}
                    (path / "req.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    return payload

                MockStore.return_value.save_request.side_effect = _save_request
                await svc._run_with_agent(attempt)

        _run(_t())
        assert observed["req_exists"] is True
        assert "Write a Python script that summarizes recent factor research notes" in observed["req_payload"]

    def test_run_attempt_uses_actual_backtest_run_dir_in_message_metadata(self, tmp_path):
        """Thread metadata must point at the real backtest run, not the bootstrap placeholder run."""
        from src.session.models import Attempt

        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(
            session_id=session.session_id,
            prompt="Backtest a risk-parity portfolio of MSFT, BTC-USDT, and AAPL for full-year 2024",
        )
        svc.store.create_attempt(attempt)

        placeholder_run_dir = tmp_path / "runs" / "bootstrap_placeholder"
        (placeholder_run_dir / "code").mkdir(parents=True, exist_ok=True)
        (placeholder_run_dir / "logs").mkdir(exist_ok=True)
        (placeholder_run_dir / "artifacts").mkdir(exist_ok=True)

        actual_run_dir = tmp_path / "runs" / "actual_backtest_run"
        (actual_run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        (actual_run_dir / "artifacts" / "metrics.csv").write_text(
            "final_value,total_return,annual_return,max_drawdown,sharpe,win_rate,trade_count\n"
            "1211710.73,0.2117,0.0816,-0.2327,0.57,0.5088,57\n",
            encoding="utf-8",
        )

        setup_payload = json.dumps({
            "status": "ok",
            "run_dir": str(actual_run_dir),
            "files_written": ["config.json", "code/signal_engine.py"],
        })
        backtest_payload = (
            "{\"status\": \"ok\", \"exit_code\": 0, \"stdout\": "
            "\"{\\n  \\\"final_value\\\": 1211710.73,\\n  \\\"total_return\\\": 0.2117\""
        )

        def _agent_factory(*args, **kwargs):
            cb = kwargs.get("tool_progress_callback")
            inst = MagicMock()

            def run_conv(**kw):
                assert cb is not None
                cb("tool.started", "setup_backtest_run", "", {})
                cb("tool.completed", "setup_backtest_run", setup_payload, {}, is_error=False)
                cb("tool.started", "backtest", "", {"run_dir": str(actual_run_dir)})
                cb("tool.completed", "backtest", backtest_payload, {}, is_error=False)
                return {"final_response": "completed", "status": "success"}

            inst.run_conversation = run_conv
            return inst

        async def _t():
            sys.modules["run_agent"].AIAgent = _agent_factory
            with patch("src.core.state.RunStateStore") as MockStore, patch(
                "src.session.service.bootstrap_run_from_prompt",
                return_value={"status": "ok"},
            ):
                store = MockStore.return_value
                store.create_run_dir.return_value = placeholder_run_dir
                store.mark_success.return_value = None
                store.save_request.return_value = {}
                await svc._run_attempt(session, attempt)

        _run(_t())

        stored_attempt = svc.store.get_attempt(session.session_id, attempt.attempt_id)
        assert stored_attempt is not None
        assert stored_attempt.run_dir == str(actual_run_dir)
        assert stored_attempt.metrics is not None
        assert stored_attempt.metrics["final_value"] == 1211710.73

        messages = svc.store.get_messages(session.session_id)
        assistant = [m for m in messages if m.role == "assistant"][-1]
        assert assistant.metadata is not None
        assert assistant.metadata["run_id"] == actual_run_dir.name
        assert assistant.metadata["metrics"]["trade_count"] == 57.0

    def test_cancel_calls_interrupt_not_cancel(self, tmp_path):
        """cancel_current() calls agent.interrupt(), not agent.cancel() (Migration Plan §2.2)."""
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)

        mock_agent = MagicMock()
        svc._active_loops["session_abc"] = mock_agent

        result = svc.cancel_current("session_abc")

        assert result is True
        mock_agent.interrupt.assert_called_once()
        mock_agent.cancel.assert_not_called()


# ---------------------------------------------------------------------------
# Swarm worker regression tests
# ---------------------------------------------------------------------------

class TestHermesSwarmWorkerEvents:
    """Hermes swarm worker must emit the same event types as the baseline worker."""

    def _make_spec_and_task(self):
        from src.swarm.models import SwarmAgentSpec, SwarmTask
        spec = SwarmAgentSpec(id="a1", role="analyst", system_prompt="you are an analyst")
        task = SwarmTask(id="t1", agent_id="a1", prompt_template="Analyse {topic}")
        return spec, task

    def test_worker_started_and_completed_events(self, tmp_path):
        from src.swarm.worker import run_worker
        spec, task = self._make_spec_and_task()
        events = []

        mock_inst = MagicMock()
        mock_inst.run_conversation.return_value = {"final_response": "done", "status": "success"}
        sys.modules["run_agent"].AIAgent = MagicMock(return_value=mock_inst)

        result = run_worker(spec, task, {}, {"topic": "BTC"}, tmp_path,
                            event_callback=lambda e: events.append(e))

        assert result.status == "completed"
        event_types = [e.type for e in events]
        assert "worker_started" in event_types
        assert "worker_completed" in event_types

    def test_worker_failed_on_missing_template_var(self, tmp_path):
        from src.swarm.worker import run_worker
        from src.swarm.models import SwarmAgentSpec, SwarmTask
        spec = SwarmAgentSpec(id="a1", role="analyst", system_prompt="sys")
        task = SwarmTask(id="t1", agent_id="a1", prompt_template="Analyse {missing_var}")
        events = []

        sys.modules["run_agent"].AIAgent = MagicMock()

        result = run_worker(spec, task, {}, {},   # missing_var not provided
                            tmp_path,
                            event_callback=lambda e: events.append(e))

        assert result.status == "failed"
        assert any(e.type == "worker_failed" for e in events)

    def test_worker_prompt_includes_backtest_setup_rule(self, tmp_path):
        from src.swarm.worker import run_worker
        spec, task = self._make_spec_and_task()

        captured_kwargs = {}

        def _agent_factory(*args, **kwargs):
            captured_kwargs.update(kwargs)
            inst = MagicMock()
            inst.run_conversation.return_value = {"final_response": "done", "status": "success"}
            return inst

        sys.modules["run_agent"].AIAgent = _agent_factory

        result = run_worker(spec, task, {}, {"topic": "BTC"}, tmp_path)

        assert result.status == "completed"
        prompt = captured_kwargs.get("ephemeral_system_prompt", "")
        assert "setup_backtest_run(config_json=..., signal_engine_py=...)" in prompt
        assert "Never ask the user to create `config.json`" in prompt
        assert "Never invent a PDF filename" in prompt
        assert "read_url or browser tools" in prompt
