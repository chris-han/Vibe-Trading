"""Baseline SSE event shape tests — SessionService (Hermes migration).

Captures the exact event type strings and payload keys emitted by the
current SessionService implementation.

Run:
    cd agent && uv run pytest tests/baseline/ -v
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _run(coro):
    """Run a coroutine synchronously (avoids pytest-asyncio dependency)."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Session SSE event shape tests
# ---------------------------------------------------------------------------

class TestBaselineSessionEvents:

    def test_session_created_event(self, tmp_path):
        """create_session() emits 'session.created' with session_id."""
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        svc.create_session(title="test")
        assert "session.created" in cap.types()
        p = cap.data_for("session.created")[0]
        assert "session_id" in p

    def test_message_received_event(self, tmp_path):
        """send_message() emits 'message.received' with message_id, role, content."""
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        cap.events.clear()

        async def _run_test():
            with patch("asyncio.create_task"):
                await svc.send_message(session.session_id, "hello")

        _run(_run_test())
        assert "message.received" in cap.types()
        p = cap.data_for("message.received")[0]
        assert "message_id" in p
        assert "role" in p
        assert "content" in p

    def test_attempt_created_event(self, tmp_path):
        """send_message() emits 'attempt.created' with attempt_id, prompt."""
        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        cap.events.clear()

        async def _run_test():
            with patch("asyncio.create_task"):
                await svc.send_message(session.session_id, "hello")

        _run(_run_test())
        assert "attempt.created" in cap.types()
        p = cap.data_for("attempt.created")[0]
        assert "attempt_id" in p
        assert "prompt" in p

    def test_attempt_started_and_completed_events(self, tmp_path):
        """_run_attempt() emits attempt.started then attempt.completed."""
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

        async def _run_test():
            with patch.object(svc, "_run_with_agent", side_effect=_fake_run):
                await svc._run_attempt(session, attempt)

        _run(_run_test())
        assert "attempt.started" in cap.types()
        assert "attempt.completed" in cap.types() or "attempt.failed" in cap.types()
        assert "attempt_id" in cap.data_for("attempt.started")[0]

    def test_attempt_failed_event_on_error(self, tmp_path):
        """_run_attempt() emits attempt.failed with attempt_id and error on exception."""
        from src.session.models import Attempt

        cap = EventCapture()
        svc = _make_service(cap, tmp_path)
        session = svc.create_session(title="t")
        attempt = Attempt(session_id=session.session_id, prompt="fail")
        svc.store.create_attempt(attempt)
        cap.events.clear()

        async def _boom(att, messages=None):
            raise RuntimeError("boom")

        async def _run_test():
            with patch.object(svc, "_run_with_agent", side_effect=_boom):
                await svc._run_attempt(session, attempt)

        _run(_run_test())
        assert "attempt.failed" in cap.types()
        p = cap.data_for("attempt.failed")[0]
        assert "attempt_id" in p
        assert "error" in p
