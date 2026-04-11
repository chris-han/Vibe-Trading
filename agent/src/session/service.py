"""Session lifecycle orchestration for message flow, attempt creation, and execution scheduling.

V5: Uses AgentLoop instead of the fixed pipeline behind the generate skill.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Dedicated thread pool limited to four concurrent agents to avoid exhausting the default executor.
_AGENT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent")

_BACKTEST_WORKFLOW_PROMPT = (
    "Backtest workflow rules:\n"
    "- If the user asks for a new backtest or strategy test, do NOT call backtest(run_dir=...) first.\n"
    "- First call load_skill(\"strategy-generate\") when you need the SignalEngine contract.\n"
    "- Then call setup_backtest_run(config_json=..., signal_engine_py=...) to create the run directory and write config.json/code.\n"
    "- Only after setup_backtest_run succeeds, call backtest(run_dir=...).\n"
    "- Never ask the user to manually create config.json or code/signal_engine.py when the tool can create them.\n"
)

_DOCUMENT_WORKFLOW_PROMPT = (
    "Document workflow rules:\n"
    "- User uploaded files are stored at sessions/<session_id>/uploads/ relative to the working directory.\n"
    "- To find uploads, use search_files with path=sessions/<session_id>/uploads (replace <session_id> with the Session value from the header above).\n"
    "- If the user provides an exact uploaded PDF path, call read_document(file_path=...) to extract the text.\n"
    "- Never invent a PDF filename; only call read_document when the exact local path is known.\n"
    "- If no local path is available, use read_url or browser tools to fetch the report from the source site.\n"
    "- Prefer reading the first relevant pages first with pages='1-5' when the document is long.\n"
    "- Treat low-text pages as scanned/image pages; OCR is optional and controlled by HERMES_ENABLE_PDF_OCR.\n"
    "- Do not claim you cannot read PDFs when read_document is available.\n"
)

_MARKET_DATA_WORKFLOW_PROMPT = (
    "Market data workflow rules:\n"
    "- For finance or research tasks, call load_skill first to get approved data access methods and symbol conventions.\n"
    "- execute_code is forbidden in this runtime. Use write_file plus bash instead.\n"
    "- Do NOT fetch market data with curl, ad hoc HTTP endpoints, or raw requests scripts.\n"
    "- Use the project-supported Python patterns from load_skill (for example yfinance or OKX API helpers).\n"
    "- Prefer writing one focused Python script with write_file, then execute it with bash.\n"
    "- The terminal already starts in the agent/ working directory; use ./.venv/bin/python for script execution.\n"
    "- For package installs, use ./.venv/bin/python -m pip. Do NOT call pip/pip3 directly.\n"
    "- Do NOT embed long Python programs directly in bash commands.\n"
    "- If an external endpoint or symbol looks suspicious, validate it against the loaded skill before using it.\n"
)


from runtime_env import ensure_runtime_env, get_hermes_agent_kwargs, prepare_hermes_project_context
from src.backtest.bootstrap import bootstrap_run_from_prompt, is_backtest_prompt
from src.session.events import EventBus
from src.session.models import (
    Attempt,
    AttemptStatus,
    Message,
    Session,
    SessionEvent,
    SessionEventType,
    SessionStatus,
)
from src.session.store import SessionStore


class SessionService:
    """Session lifecycle service.

    Attributes:
        store: Session persistence store.
        event_bus: SSE event bus.
        runs_dir: Root runs directory.
    """

    def __init__(
        self,
        store: SessionStore,
        event_bus: EventBus,
        runs_dir: Path,
    ) -> None:
        """Initialize the session service.

        Args:
            store: Session persistence store.
            event_bus: SSE event bus.
            runs_dir: Root runs directory.
        """
        self.store = store
        self.event_bus = event_bus
        self.runs_dir = runs_dir
        self._active_loops: Dict[str, "AgentLoop"] = {}

    def create_session(self, title: str = "", config: Optional[Dict[str, Any]] = None) -> Session:
        """Create a new session.

        Args:
            title: Session title.
            config: Session configuration.

        Returns:
            The newly created Session.
        """
        session = Session(title=title, config=config or {})
        self.store.create_session(session)
        self.event_bus.emit(session.session_id, "session.created", {"session_id": session.session_id, "title": title})
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Return a session by ID."""
        return self.store.get_session(session_id)

    def list_sessions(self, limit: int = 50) -> list[Session]:
        """List all sessions."""
        return self.store.list_sessions(limit)

    def _collect_run_dirs(self, session_id: str) -> list[Path]:
        """Collect all run_dir paths recorded in attempts for a session."""
        run_dirs: list[Path] = []
        try:
            attempts = self.store.list_attempts(session_id)
            for attempt in attempts:
                if attempt.run_dir:
                    p = Path(attempt.run_dir)
                    if p.exists() and p.is_dir():
                        run_dirs.append(p)
        except Exception:
            pass
        return run_dirs

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its associated run artifact directories."""
        import shutil
        run_dirs = self._collect_run_dirs(session_id)
        self.event_bus.clear(session_id)
        ok = self.store.delete_session(session_id)
        for rd in run_dirs:
            shutil.rmtree(rd, ignore_errors=True)
        return ok

    def delete_sessions(self, session_ids: list[str]) -> Dict[str, Any]:
        """Delete multiple sessions in one service call."""
        import shutil
        deleted: list[str] = []
        missing: list[str] = []
        for session_id in session_ids:
            run_dirs = self._collect_run_dirs(session_id)
            self.event_bus.clear(session_id)
            if self.store.delete_session(session_id):
                deleted.append(session_id)
                for rd in run_dirs:
                    shutil.rmtree(rd, ignore_errors=True)
            else:
                missing.append(session_id)
        return {
            "deleted": deleted,
            "missing": missing,
        }

    def _update_session_state(
        self,
        session_id: str,
        *,
        status: Optional[SessionStatus] = None,
        last_attempt_id: Optional[str] = None,
    ) -> Optional[Session]:
        """Persist the latest session lifecycle state."""
        session = self.store.get_session(session_id)
        if not session:
            return None
        if status is not None:
            session.status = status
        if last_attempt_id is not None:
            session.last_attempt_id = last_attempt_id
        session.updated_at = datetime.now().isoformat()
        self.store.update_session(session)
        return session

    def _record_event(
        self,
        session_id: str,
        event_type: str,
        *,
        attempt_id: Optional[str] = None,
        role: Optional[str] = None,
        content: Optional[str] = None,
        reasoning: Optional[str] = None,
        tool: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        args: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionEvent:
        """Persist a canonical session event."""
        event = SessionEvent(
            session_id=session_id,
            attempt_id=attempt_id,
            event_type=event_type,
            role=role,
            content=content,
            reasoning=reasoning,
            tool=tool,
            tool_call_id=tool_call_id,
            args=args,
            status=status,
            metadata=metadata or {},
        )
        self.store.append_event(event)
        return event

    async def send_message(self, session_id: str, content: str, role: str = "user") -> Dict[str, Any]:
        """Send a message to a session and trigger execution.

        Args:
            session_id: Session ID.
            content: Message content.
            role: Message role.

        Returns:
            Dictionary containing message_id and attempt_id.
        """
        session = self.store.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        message = Message(session_id=session_id, role=role, content=content)
        self.store.append_message(message)
        self.event_bus.emit(session_id, "message.received", {"message_id": message.message_id, "role": role, "content": content})

        if role != "user":
            return {"message_id": message.message_id}

        attempt = Attempt(session_id=session_id, parent_attempt_id=session.last_attempt_id, prompt=content)
        self.store.create_attempt(attempt)
        self._update_session_state(
            session_id,
            status=SessionStatus.RUNNING,
            last_attempt_id=attempt.attempt_id,
        )
        self._record_event(
            session_id,
            SessionEventType.ATTEMPT_CREATED.value,
            attempt_id=attempt.attempt_id,
            metadata={"prompt": content},
        )
        self.event_bus.emit(session_id, "attempt.created", {"attempt_id": attempt.attempt_id, "prompt": content})

        asyncio.create_task(self._run_attempt(session, attempt))
        return {"message_id": message.message_id, "attempt_id": attempt.attempt_id}

    async def resume_attempt(self, session_id: str, attempt_id: str, user_input: str) -> Dict[str, Any]:
        """Resume an attempt that is waiting for user input.

        Args:
            session_id: Session ID.
            attempt_id: Attempt ID.
            user_input: User reply content.

        Returns:
            Dictionary containing status and attempt_id.
        """
        session = self.store.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        attempt = self.store.get_attempt(session_id, attempt_id)
        if not attempt:
            raise ValueError(f"Attempt {attempt_id} not found")
        if attempt.status != AttemptStatus.WAITING_USER:
            raise ValueError(f"Attempt {attempt_id} is not waiting for user input")

        message = Message(session_id=session_id, role="user", content=user_input, linked_attempt_id=attempt_id)
        self.store.append_message(message)

        # Append the user's reply to the prompt and rerun the attempt.
        attempt.prompt = f"{attempt.prompt}\n\nUser reply: {user_input}"
        attempt.status = AttemptStatus.RUNNING
        self.store.update_attempt(attempt)
        self._update_session_state(
            session_id,
            status=SessionStatus.RUNNING,
            last_attempt_id=attempt_id,
        )
        self._record_event(
            session_id,
            SessionEventType.ATTEMPT_STARTED.value,
            attempt_id=attempt_id,
            metadata={"resumed": True},
        )
        self.event_bus.emit(session_id, "attempt.resumed", {"attempt_id": attempt_id, "user_input": user_input})

        asyncio.create_task(self._run_attempt(session, attempt))
        return {"status": "resumed", "attempt_id": attempt_id}

    def get_messages(self, session_id: str, limit: int = 100) -> list[Message]:
        """Return the message history."""
        return self.store.get_messages(session_id, limit)

    def get_events(self, session_id: str, limit: int = 1000) -> list[SessionEvent]:
        """Return canonical session events."""
        return self.store.get_events(session_id, limit)

    def export_atropos_trajectory(self, session_id: str) -> Dict[str, Any]:
        """Project canonical events into an Atropos/Hermes trajectory entry."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        events = self.store.get_events(session_id, limit=100000)
        conversations: list[Dict[str, str]] = []
        used_tools: set[str] = set()

        def _render_assistant(turn: Optional[Dict[str, Any]]) -> Optional[str]:
            if not turn:
                return None
            parts: list[str] = []
            reasoning = "".join(turn["reasoning"]).strip()
            if reasoning:
                parts.append(f"<think>\n{reasoning}\n</think>")
            tool_calls = turn["tool_calls"]
            if tool_calls:
                for tc in tool_calls:
                    parts.append("<tool_call>\n" + json.dumps(tc, ensure_ascii=False) + "\n</tool_call>")
            text = "".join(turn["text"]).strip()
            if text:
                parts.append(text)
            rendered = "\n".join(parts).strip()
            return rendered or None

        def _flush_assistant(turn: Optional[Dict[str, Any]]) -> None:
            rendered = _render_assistant(turn)
            if rendered:
                conversations.append({"from": "gpt", "value": rendered})

        def _flush_tool_results(results: list[Dict[str, Any]]) -> None:
            if not results:
                return
            payload = "\n".join(
                "<tool_response>\n" + json.dumps(item, ensure_ascii=False) + "\n</tool_response>"
                for item in results
            )
            conversations.append({"from": "tool", "value": payload})

        current_assistant: Optional[Dict[str, Any]] = None
        pending_tool_results: list[Dict[str, Any]] = []

        for event in events:
            if event.event_type == SessionEventType.MESSAGE_CREATED.value:
                if event.role == "user":
                    _flush_assistant(current_assistant)
                    current_assistant = None
                    _flush_tool_results(pending_tool_results)
                    pending_tool_results = []
                    conversations.append({"from": "human", "value": event.content or ""})
                    continue
                if event.role == "assistant":
                    _flush_tool_results(pending_tool_results)
                    pending_tool_results = []
                    if current_assistant is None:
                        current_assistant = {"reasoning": [], "text": [], "tool_calls": []}
                    if event.content and not "".join(current_assistant["text"]).strip():
                        current_assistant["text"].append(event.content)
                    _flush_assistant(current_assistant)
                    current_assistant = None
                    continue

            if event.event_type == SessionEventType.REASONING_DELTA.value:
                _flush_tool_results(pending_tool_results)
                pending_tool_results = []
                if current_assistant is None:
                    current_assistant = {"reasoning": [], "text": [], "tool_calls": []}
                if event.reasoning:
                    current_assistant["reasoning"].append(event.reasoning)
                continue

            if event.event_type == SessionEventType.TEXT_DELTA.value:
                _flush_tool_results(pending_tool_results)
                pending_tool_results = []
                if current_assistant is None:
                    current_assistant = {"reasoning": [], "text": [], "tool_calls": []}
                if event.content:
                    current_assistant["text"].append(event.content)
                continue

            if event.event_type == SessionEventType.TOOL_CALL.value:
                _flush_tool_results(pending_tool_results)
                pending_tool_results = []
                if current_assistant is None:
                    current_assistant = {"reasoning": [], "text": [], "tool_calls": []}
                used_tools.add(str(event.tool or ""))
                current_assistant["tool_calls"].append({
                    "name": event.tool or "",
                    "arguments": event.args or {},
                })
                continue

            if event.event_type == SessionEventType.TOOL_RESULT.value:
                if current_assistant is not None:
                    _flush_assistant(current_assistant)
                    current_assistant = None
                pending_tool_results.append({
                    "tool_call_id": event.tool_call_id or "",
                    "name": event.tool or "",
                    "content": event.content or "",
                    "status": event.status or "ok",
                })
                if event.tool:
                    used_tools.add(event.tool)
                continue

        _flush_assistant(current_assistant)
        _flush_tool_results(pending_tool_results)

        tool_defs = [{"name": name, "description": f"Tool {name}", "parameters": {"type": "object"}} for name in sorted(t for t in used_tools if t)]
        system_value = (
            "You are a function calling AI model. Use reasoning in <think> tags. "
            "Emit tool invocations in <tool_call> blocks and consume results in <tool_response> blocks.\n"
            f"<tools>\n{json.dumps(tool_defs, ensure_ascii=False)}\n</tools>"
        )

        return {
            "session_id": session_id,
            "title": session.title,
            "source_file": str(self.store._events_file(session_id)),
            "trajectory": {
                "conversations": [{"from": "system", "value": system_value}, *conversations],
                "timestamp": session.updated_at,
                "model": os.getenv("HERMES_MODEL", ""),
                "completed": True,
                "metadata": {
                    "session_id": session_id,
                    "event_count": len(events),
                    "tools_used": sorted(t for t in used_tools if t),
                },
            },
        }

    def get_attempts(self, session_id: str) -> list[Attempt]:
        """Return all execution attempts."""
        return self.store.list_attempts(session_id)

    def get_attempt(self, session_id: str, attempt_id: str) -> Optional[Attempt]:
        """Return a single execution attempt."""
        return self.store.get_attempt(session_id, attempt_id)

    def cancel_current(self, session_id: str) -> bool:
        """Cancel the currently running agent for a session.

        Args:
            session_id: Session ID.

        Returns:
            Whether cancellation succeeded. True means an active agent existed and received a cancel signal.
        """
        agent = self._active_loops.get(session_id)
        if agent is None:
            return False
        self._update_session_state(session_id, status=SessionStatus.CANCELLED)
        session = self.store.get_session(session_id)
        if session and session.last_attempt_id:
            attempt = self.store.get_attempt(session_id, session.last_attempt_id)
            if attempt and attempt.status == AttemptStatus.RUNNING:
                attempt.mark_cancelled("cancelled by user")
                self.store.update_attempt(attempt)
        agent.interrupt("cancelled by user")
        return True

    @staticmethod
    def _is_cancelled_error(error: Optional[str]) -> bool:
        """Best-effort detection for user cancellation."""
        text = str(error or "").strip().lower()
        return "cancelled by user" in text or text == "cancelled" or "interrupted" in text

    async def _run_attempt(self, session: Session, attempt: Attempt) -> None:
        """Execute an Attempt in the background."""
        attempt.mark_running()
        self.store.update_attempt(attempt)
        self._update_session_state(
            session.session_id,
            status=SessionStatus.RUNNING,
            last_attempt_id=attempt.attempt_id,
        )
        self._record_event(
            session.session_id,
            SessionEventType.ATTEMPT_STARTED.value,
            attempt_id=attempt.attempt_id,
        )
        self.event_bus.emit(session.session_id, "attempt.started", {"attempt_id": attempt.attempt_id})

        try:
            messages = self.store.get_messages(session.session_id)
            result = await self._run_with_agent(attempt, messages=messages)
            if result.get("status") == "success":
                attempt.mark_completed(summary=result.get("content", ""))
                next_session_status = SessionStatus.COMPLETED
            elif result.get("status") == "cancelled":
                attempt.mark_cancelled(error=result.get("reason", "cancelled"))
                next_session_status = SessionStatus.CANCELLED
            else:
                attempt.mark_failed(error=result.get("reason", "unknown"))
                next_session_status = SessionStatus.FAILED
            attempt.run_dir = result.get("run_dir")
            attempt.metrics = result.get("metrics")

            self.store.update_attempt(attempt)
            self._update_session_state(
                session.session_id,
                status=next_session_status,
                last_attempt_id=attempt.attempt_id,
            )
            reply_metadata = {}
            if attempt.run_dir:
                reply_metadata["run_id"] = Path(attempt.run_dir).name
            reply_metadata["status"] = attempt.status.value
            if attempt.metrics:
                reply_metadata["metrics"] = attempt.metrics

            reply = Message(
                session_id=session.session_id, role="assistant",
                content=self._format_result_message(attempt),
                linked_attempt_id=attempt.attempt_id,
                metadata=reply_metadata,
            )
            self.store.append_message(reply)
            self._record_event(
                session.session_id,
                SessionEventType.ATTEMPT_COMPLETED.value if attempt.status == AttemptStatus.COMPLETED else SessionEventType.ATTEMPT_FAILED.value,
                attempt_id=attempt.attempt_id,
                status=attempt.status.value,
                metadata={
                    "summary": attempt.summary,
                    "error": attempt.error,
                    "run_dir": attempt.run_dir,
                    "metrics": attempt.metrics,
                },
            )
            self.event_bus.emit(
                session.session_id,
                "attempt.completed" if attempt.status == AttemptStatus.COMPLETED else "attempt.failed",
                {
                    "attempt_id": attempt.attempt_id,
                    "status": attempt.status.value,
                    "summary": attempt.summary,
                    "error": attempt.error,
                    "run_dir": attempt.run_dir,
                    "metrics": attempt.metrics,
                },
            )

        except Exception as exc:
            error_text = str(exc)
            if self._is_cancelled_error(error_text):
                attempt.mark_cancelled(error=error_text)
                next_session_status = SessionStatus.CANCELLED
            else:
                attempt.mark_failed(error=error_text)
                next_session_status = SessionStatus.FAILED
            self.store.update_attempt(attempt)
            self._update_session_state(
                session.session_id,
                status=next_session_status,
                last_attempt_id=attempt.attempt_id,
            )
            self._record_event(
                session.session_id,
                SessionEventType.ATTEMPT_FAILED.value,
                attempt_id=attempt.attempt_id,
                status=attempt.status.value,
                metadata={"error": error_text},
            )
            self.event_bus.emit(
                session.session_id,
                "attempt.failed",
                {"attempt_id": attempt.attempt_id, "status": attempt.status.value, "error": error_text},
            )

    async def _run_with_agent(self, attempt: Attempt, messages: list = None) -> Dict[str, Any]:
        """Execute an attempt using Hermes AIAgent directly.

        Args:
            attempt: Current execution attempt.
            messages: Session message history.

        Returns:
            Result dictionary containing status, run_dir, run_id, metrics, and related fields.
        """
        import os
        import sys
        prepare_hermes_project_context(chdir=True)
        _HERMES = Path(__file__).resolve().parents[3] / "hermes-agent"
        if str(_HERMES) not in sys.path:
            sys.path.insert(0, str(_HERMES))
        from run_agent import AIAgent
        from src.core.state import RunStateStore

        sid = attempt.session_id
        attempt_id = attempt.attempt_id
        latest_prepared_run_dir: str | None = None
        latest_backtest_run_dir: str | None = None
        latest_useful_tool_output: str | None = None

        state_store = RunStateStore()
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        run_dir = state_store.create_run_dir(self.runs_dir)
        state_store.save_request(run_dir, attempt.prompt, {"session_id": sid})

        if is_backtest_prompt(attempt.prompt):
            try:
                bootstrap_run_from_prompt(run_dir, attempt.prompt)
            except Exception:
                logger.warning("Failed to bootstrap backtest run_dir=%s", run_dir, exc_info=True)

        # Bridge Hermes callbacks -> Vibe-Trading SSE events
        def _on_tool_progress(
            event_type: str,
            tool_name: str = "",
            preview: str = "",
            args: Optional[dict] = None,
            **kwargs,
        ) -> None:
            nonlocal latest_prepared_run_dir, latest_backtest_run_dir, latest_useful_tool_output
            if event_type == "tool.started":
                if tool_name == "backtest":
                    started_run_dir = str((args or {}).get("run_dir") or "").strip()
                    if started_run_dir:
                        latest_backtest_run_dir = started_run_dir
                self._record_event(
                    sid,
                    SessionEventType.TOOL_CALL.value,
                    attempt_id=attempt_id,
                    tool=tool_name,
                    args=args or {},
                    status="running",
                )
                logger.info("[%s] tool.started  %s  args=%s", sid[:8], tool_name, str(args or {})[:300])
                self.event_bus.emit(sid, "tool_call", {
                    "attempt_id": attempt_id,
                    "tool": tool_name,
                    "args": args or {},
                })
                if tool_name == "run_swarm":
                    preset = str((args or {}).get("preset_name") or "swarm").strip()
                    variables = (args or {}).get("variables") or {}
                    vars_preview = ", ".join(
                        f"{k}={v}" for k, v in variables.items() if str(v).strip()
                    )
                    progress_msg = (
                        f"Running `{preset}`"
                        + (f" for {vars_preview}" if vars_preview else "")
                        + ". This usually takes a few minutes."
                    )
                    self._record_event(
                        sid,
                        SessionEventType.TOOL_PROGRESS.value,
                        attempt_id=attempt_id,
                        tool=tool_name,
                        content=progress_msg,
                    )
                    self.event_bus.emit(sid, "tool_progress", {
                        "attempt_id": attempt_id,
                        "tool": tool_name,
                        "preview": progress_msg,
                    })
            elif event_type == "tool.completed":
                is_error = kwargs.get("is_error", False)
                preview_str = str(preview or "")[:500]
                parsed_result: Dict[str, Any] | None = None
                try:
                    parsed_result = json.loads(str(preview or ""))
                except Exception:
                    parsed_result = None

                if not is_error and parsed_result:
                    if tool_name == "setup_backtest_run":
                        latest_prepared_run_dir = str(parsed_result.get("run_dir") or "") or latest_prepared_run_dir
                    elif tool_name == "backtest":
                        resolved = parsed_result.get("resolved_run_dir") or parsed_result.get("run_dir")
                        if parsed_result.get("status") == "ok" and resolved:
                            latest_backtest_run_dir = str(resolved)

                if not is_error:
                    useful_tool_output = self._extract_useful_tool_output(tool_name, parsed_result, str(preview or ""))
                    if useful_tool_output:
                        latest_useful_tool_output = useful_tool_output

                if is_error:
                    logger.error("[%s] tool.error    %s  result=%s", sid[:8], tool_name, preview_str)
                else:
                    logger.info("[%s] tool.completed %s  result=%s", sid[:8], tool_name, preview_str[:200])
                self._record_event(
                    sid,
                    SessionEventType.TOOL_RESULT.value,
                    attempt_id=attempt_id,
                    tool=tool_name,
                    content=preview_str,
                    status="error" if is_error else "ok",
                    metadata={"is_error": is_error},
                )
                self.event_bus.emit(sid, "tool_result", {
                    "attempt_id": attempt_id,
                    "tool": tool_name,
                    "is_error": is_error,
                    "status": "error" if is_error else "ok",
                    "preview": preview_str,
                })
            elif event_type == "subagent_progress":
                progress_text = str(preview or tool_name or "")[:500]
                logger.info("[%s] tool.progress  %s", sid[:8], progress_text[:200])
                self._record_event(
                    sid,
                    SessionEventType.TOOL_PROGRESS.value,
                    attempt_id=attempt_id,
                    tool=str(kwargs.get("parent_tool") or "delegate_task"),
                    content=progress_text,
                )
                self.event_bus.emit(sid, "tool_progress", {
                    "attempt_id": attempt_id,
                    "tool": str(kwargs.get("parent_tool") or "delegate_task"),
                    "preview": progress_text,
                })

        def _on_delta(chunk: str) -> None:
            if chunk is not None:
                self._record_event(
                    sid,
                    SessionEventType.TEXT_DELTA.value,
                    attempt_id=attempt_id,
                    role="assistant",
                    content=chunk,
                )
            self.event_bus.emit(sid, "text_delta", {
                "attempt_id": attempt_id,
                "content": chunk,
            })

        def _on_reasoning(text: str) -> None:
            if text:
                self._record_event(
                    sid,
                    SessionEventType.REASONING_DELTA.value,
                    attempt_id=attempt_id,
                    role="assistant",
                    reasoning=text,
                )
            self.event_bus.emit(sid, "reasoning_delta", {
                "attempt_id": attempt_id,
                "content": text,
            })

        def _on_tool_generation(tool_name: str) -> None:
            if tool_name == "execute_code":
                logger.error(
                    "[%s] permission_denied execute_code attempted by model; "
                    "toolset is disabled for Vibe-Trading session runtime",
                    sid[:8],
                )

        ensure_runtime_env()
        agent_kwargs = get_hermes_agent_kwargs()

        # Configure terminal/file tool root via env var and per-session task
        # override so every session starts in agent/ rather than the full repo
        # root. This prevents search_files from crawling hermes-agent/ and other
        # top-level sibling directories.
        #
        # TERMINAL_CWD is the global fallback; register_task_env_overrides pins
        # the exact session-scoped cwd in Hermes' tool layer so that file ops
        # and terminal commands resolve relative paths without any absolute path
        # being injected via the prompt.  Plugin discovery still works because
        # Hermes uses Path.cwd() (the Python process CWD), not TERMINAL_CWD, to
        # find .hermes/plugins/.
        repo_root = prepare_hermes_project_context(chdir=False)
        agent_root = repo_root / "agent"

        # TERMINAL_CWD may be set in .env as a relative path (e.g. a username
        # like 'chris'). Resolve it against agent_root so the tool layer always
        # receives an absolute path.
        _raw_cwd = os.getenv("TERMINAL_CWD", "")
        if _raw_cwd and not os.path.isabs(_raw_cwd):
            file_root = (agent_root / _raw_cwd).resolve()
        elif _raw_cwd:
            file_root = Path(_raw_cwd).resolve()
        else:
            file_root = agent_root
        # Ensure the directory exists so Hermes doesn't reject it.
        file_root.mkdir(parents=True, exist_ok=True)

        try:
            from tools.terminal_tool import register_task_env_overrides
            register_task_env_overrides(sid, {"cwd": str(file_root)})
        except Exception:
            pass  # Non-fatal: TERMINAL_CWD env-var fallback still applies

        agent = AIAgent(
            model=os.getenv("HERMES_MODEL", ""),
            max_iterations=50,
            quiet_mode=True,
            session_id=sid,
            enabled_toolsets=[
                "terminal",
                "file",
                "browser",
                "skills",
                "todo",
                "memory",
                "session_search",
                "delegation",
                "cronjob",
                "research",
                "compat",
                "vibe_trading_finance",
            ],
            disabled_toolsets=["code_execution"],
            tool_progress_callback=_on_tool_progress,
            tool_gen_callback=_on_tool_generation,
            reasoning_callback=_on_reasoning,
            stream_delta_callback=_on_delta,
            ephemeral_system_prompt=(
                f"Run directory: {run_dir}\n"
                f"Session: {sid}\n"
                f"{_BACKTEST_WORKFLOW_PROMPT}"
                f"{_DOCUMENT_WORKFLOW_PROMPT}"
                f"{_MARKET_DATA_WORKFLOW_PROMPT}"
            ),
            skip_context_files=True,
            **agent_kwargs,
        )
        self._active_loops[sid] = agent

        history = self._convert_messages_to_history(messages) if messages else []

        from src.hermes_tool_adapter.vibe_trading_compat import reset_artifact_dir, set_artifact_dir
        _ctx_token = set_artifact_dir(run_dir / "artifacts")
        try:
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(
                _AGENT_EXECUTOR,
                lambda: agent.run_conversation(
                    user_message=attempt.prompt,
                    conversation_history=history,
                ),
            )
            final_text = (raw.get("final_response") or "").strip()
            if not final_text and latest_useful_tool_output:
                final_text = latest_useful_tool_output.strip()
                logger.info(
                    "[%s] using tool-result fallback for empty final response",
                    sid[:8],
                )
            if final_text:
                try:
                    (run_dir / "report.md").write_text(final_text, encoding="utf-8")
                except Exception:
                    logger.warning("Failed to persist report.md for run_dir=%s", run_dir, exc_info=True)
            state_store.mark_success(run_dir)
            result: Dict[str, Any] = {
                "status": "success",
                "content": final_text,
                "run_dir": str(run_dir),
                "run_id": run_dir.name,
            }
        except Exception as exc:
            logger.error("[%s] agent exception in run_dir=%s: %s", sid[:8], run_dir, exc, exc_info=True)
            state_store.mark_failure(run_dir, str(exc))
            result = {
                "status": "cancelled" if self._is_cancelled_error(str(exc)) else "failed",
                "reason": str(exc),
                "content": "",
                "run_dir": str(run_dir),
                "run_id": run_dir.name,
            }
        finally:
            reset_artifact_dir(_ctx_token)
            self._active_loops.pop(sid, None)

        # Load metrics from the run output when available.
        actual_run_dir = latest_backtest_run_dir or latest_prepared_run_dir or result.get("run_dir")
        if actual_run_dir:
            result["run_dir"] = actual_run_dir
            result["run_id"] = Path(actual_run_dir).name
            # If the backtest tool created its own run dir, propagate state.json there too
            # so the frontend can resolve the status from the returned run_id.
            if actual_run_dir != str(run_dir):
                try:
                    state_store.mark_success(Path(actual_run_dir)) if result.get("status") == "success" else state_store.mark_failure(Path(actual_run_dir), str(result.get("reason", "")))
                except Exception:
                    pass
            metrics = self._load_metrics(Path(actual_run_dir))
            if metrics:
                result["metrics"] = metrics

        return result

    @staticmethod
    def _convert_messages_to_history(messages: list) -> list[Dict[str, Any]]:
        """Convert Session messages into OpenAI-format history.

        Keeps the readable ``[prev_run: {run_id}]`` marker instead of removing it
        completely, and trims by character budget instead of a hard six-message cap
        so the LLM can still see previous artifact paths and strategy content during
        iterative updates.

        Args:
            messages: Session message list without the current turn.

        Returns:
            OpenAI-format messages trimmed from the newest items within the token budget.
        """
        import re
        from pathlib import Path

        def _shorten_run_dir(match: re.Match) -> str:
            path_str = match.group(0).replace("Run directory:", "").strip()
            run_id = Path(path_str).name if path_str else ""
            return f"[prev_run: {run_id}]" if run_id else ""

        history = []
        for msg in messages[:-1]:
            role = msg.role if hasattr(msg, "role") else msg.get("role", "user")
            content = msg.content if hasattr(msg, "content") else msg.get("content", "")
            if not content.strip() or role not in ("user", "assistant"):
                continue
            content = re.sub(r"Run directory:\s*\S+", _shorten_run_dir, content).strip()
            if content:
                history.append({"role": role, "content": content})

        # Trim from the newest messages within a character budget of roughly 3000 tokens.
        MAX_HISTORY_CHARS = 12000
        total_chars = 0
        trimmed: list = []
        for msg in reversed(history):
            msg_len = len(msg.get("content", ""))
            if total_chars + msg_len > MAX_HISTORY_CHARS:
                break
            trimmed.append(msg)
            total_chars += msg_len
        return list(reversed(trimmed))

    @staticmethod
    def _load_metrics(run_dir: Path) -> Optional[Dict[str, Any]]:
        """Load metrics.csv from a run directory."""
        import csv
        metrics_path = run_dir / "artifacts" / "metrics.csv"
        if not metrics_path.exists():
            return None
        try:
            with open(metrics_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
                if rows:
                    return {k: float(v) for k, v in rows[0].items() if v}
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_useful_tool_output(
        tool_name: str,
        parsed_result: Optional[Dict[str, Any]],
        preview: str,
    ) -> str:
        """Extract readable fallback content from a successful tool result."""
        data = parsed_result if isinstance(parsed_result, dict) else {}

        if tool_name == "run_swarm":
            final_report = str(data.get("final_report") or "").strip()
            if final_report:
                return final_report

            task_sections: list[str] = []
            tasks = data.get("tasks") or []
            if isinstance(tasks, list):
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    summary = str(task.get("summary") or "").strip()
                    if not summary:
                        continue
                    agent_id = str(task.get("agent_id") or task.get("id") or "task").strip()
                    task_sections.append(f"### {agent_id}\n{summary}")
            if task_sections:
                return "\n\n".join(task_sections)

        for key in ("summary", "report", "message", "analysis"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        clean_preview = str(preview or "").strip()
        if clean_preview and not clean_preview.startswith(("{", "[")):
            return clean_preview[:4000]

        return ""

    @staticmethod
    def _format_result_message(attempt: Attempt) -> str:
        """Format the final execution result message."""
        if attempt.status == AttemptStatus.COMPLETED:
            return attempt.summary or "Strategy execution completed."
        return f"Execution failed: {attempt.error or 'unknown error'}"
