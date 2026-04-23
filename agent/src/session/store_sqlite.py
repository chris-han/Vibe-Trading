"""SQLite-backed persistence for Session, Attempt, and SessionEvent records.

This backend mirrors the SessionStore interface while storing canonical records
in SQLite. It keeps lightweight session directories on disk so existing upload
and artifact paths continue to work during migration.
"""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.session.models import Attempt, Message, Session, SessionEvent, SessionEventType


class SQLiteSessionStore:
    """SQLite-backed persistent storage with SessionStore-compatible APIs."""

    def __init__(self, base_dir: Path, db_path: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webui_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_attempt_id TEXT,
                    config_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webui_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    parent_attempt_id TEXT,
                    status TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    run_dir TEXT,
                    summary TEXT,
                    react_trace_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    error TEXT,
                    metrics_json TEXT,
                    FOREIGN KEY(session_id) REFERENCES webui_sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webui_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    attempt_id TEXT,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    role TEXT,
                    content TEXT,
                    reasoning TEXT,
                    tool TEXT,
                    tool_call_id TEXT,
                    args_json TEXT,
                    status TEXT,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES webui_sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webui_artifacts (
                    session_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, path),
                    FOREIGN KEY(session_id) REFERENCES webui_sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_webui_sessions_updated_at ON webui_sessions(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_webui_attempts_session_created ON webui_attempts(session_id, created_at ASC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_webui_events_session_ts ON webui_events(session_id, timestamp ASC)")
            conn.commit()

    def _session_dir(self, session_id: str) -> Path:
        return self.base_dir / session_id

    def _session_channel(self, session_id: str) -> Optional[str]:
        session = self.get_session(session_id)
        if not session:
            return None
        channel = session.config.get("channel") if isinstance(session.config, dict) else None
        return str(channel) if channel else None

    # ---- Session CRUD ----

    def create_session(self, session: Session) -> Session:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM webui_sessions WHERE session_id = ?",
                (session.session_id,),
            ).fetchone()
            if existing is not None:
                raise ValueError(f"Session {session.session_id} already exists")
            conn.execute(
                """
                INSERT INTO webui_sessions (
                    session_id,
                    title,
                    status,
                    created_at,
                    updated_at,
                    last_attempt_id,
                    config_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.title,
                    session.status.value,
                    session.created_at,
                    session.updated_at,
                    session.last_attempt_id,
                    json.dumps(session.config or {}, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            conn.commit()

        # Preserve filesystem compatibility for uploads and nested run dirs.
        session_dir = self._session_dir(session.session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "attempts").mkdir(parents=True, exist_ok=True)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    session_id,
                    title,
                    status,
                    created_at,
                    updated_at,
                    last_attempt_id,
                    config_json
                FROM webui_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return Session.from_dict(
            {
                "session_id": str(row["session_id"]),
                "title": str(row["title"] or ""),
                "status": str(row["status"] or "active"),
                "created_at": str(row["created_at"] or ""),
                "updated_at": str(row["updated_at"] or ""),
                "last_attempt_id": row["last_attempt_id"],
                "config": json.loads(str(row["config_json"] or "{}")),
            }
        )

    def update_session(self, session: Session) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE webui_sessions
                SET
                    title = ?,
                    status = ?,
                    created_at = ?,
                    updated_at = ?,
                    last_attempt_id = ?,
                    config_json = ?
                WHERE session_id = ?
                """,
                (
                    session.title,
                    session.status.value,
                    session.created_at,
                    session.updated_at,
                    session.last_attempt_id,
                    json.dumps(session.config or {}, ensure_ascii=False, separators=(",", ":")),
                    session.session_id,
                ),
            )
            conn.commit()

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM webui_sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()

        session_dir = self._session_dir(session_id)
        if session_dir.exists():
            import shutil

            shutil.rmtree(session_dir, ignore_errors=True)
        return cursor.rowcount > 0

    def register_artifact(self, session_id: str, path: str, kind: str = "generic") -> None:
        normalized = str(Path(path or "")).strip()
        if not normalized:
            return
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO webui_artifacts (session_id, path, kind, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, path) DO UPDATE SET
                    kind = excluded.kind
                """,
                (session_id, normalized, str(kind or "generic"), now),
            )
            conn.commit()

    def list_artifacts(self, session_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT path, kind
                FROM webui_artifacts
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [{"path": str(r["path"] or ""), "kind": str(r["kind"] or "generic")} for r in rows if str(r["path"] or "").strip()]

    def list_sessions(self, limit: int = 50) -> List[Session]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    session_id,
                    title,
                    status,
                    created_at,
                    updated_at,
                    last_attempt_id,
                    config_json
                FROM webui_sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        sessions: List[Session] = []
        for row in rows:
            sessions.append(
                Session.from_dict(
                    {
                        "session_id": str(row["session_id"]),
                        "title": str(row["title"] or ""),
                        "status": str(row["status"] or "active"),
                        "created_at": str(row["created_at"] or ""),
                        "updated_at": str(row["updated_at"] or ""),
                        "last_attempt_id": row["last_attempt_id"],
                        "config": json.loads(str(row["config_json"] or "{}")),
                    }
                )
            )
        return sessions

    # ---- Canonical Event Log ----

    def append_event(self, event: SessionEvent) -> None:
        channel = self._session_channel(event.session_id)
        if channel:
            event.metadata = {**(event.metadata or {}), "channel": channel}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO webui_events (
                    event_id,
                    session_id,
                    attempt_id,
                    event_type,
                    timestamp,
                    role,
                    content,
                    reasoning,
                    tool,
                    tool_call_id,
                    args_json,
                    status,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.session_id,
                    event.attempt_id,
                    event.event_type,
                    event.timestamp,
                    event.role,
                    event.content,
                    event.reasoning,
                    event.tool,
                    event.tool_call_id,
                    json.dumps(event.args or {}, ensure_ascii=False, separators=(",", ":")) if event.args else None,
                    event.status,
                    json.dumps(event.metadata or {}, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            conn.commit()

    def get_events(self, session_id: str, limit: int = 1000) -> List[SessionEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    event_id,
                    session_id,
                    attempt_id,
                    event_type,
                    timestamp,
                    role,
                    content,
                    reasoning,
                    tool,
                    tool_call_id,
                    args_json,
                    status,
                    metadata_json
                FROM webui_events
                WHERE session_id = ?
                ORDER BY timestamp ASC, id ASC
                LIMIT ?
                """,
                (session_id, max(1, int(limit))),
            ).fetchall()
        return [
            SessionEvent.from_dict(
                {
                    "event_id": str(r["event_id"]),
                    "session_id": str(r["session_id"]),
                    "attempt_id": r["attempt_id"],
                    "event_type": str(r["event_type"]),
                    "timestamp": str(r["timestamp"]),
                    "role": r["role"],
                    "content": r["content"],
                    "reasoning": r["reasoning"],
                    "tool": r["tool"],
                    "tool_call_id": r["tool_call_id"],
                    "args": json.loads(str(r["args_json"] or "{}")) if r["args_json"] else None,
                    "status": r["status"],
                    "metadata": json.loads(str(r["metadata_json"] or "{}")),
                }
            )
            for r in rows
        ]

    # ---- Message Projection ----

    def append_message(self, message: Message) -> None:
        channel = self._session_channel(message.session_id)
        if channel and "channel" not in message.metadata:
            message.metadata = {**message.metadata, "channel": channel}
        self.append_event(
            SessionEvent(
                session_id=message.session_id,
                attempt_id=message.linked_attempt_id,
                event_type=SessionEventType.MESSAGE_CREATED.value,
                timestamp=message.created_at,
                role=message.role,
                content=message.content,
                metadata={
                    "message_id": message.message_id,
                    "linked_attempt_id": message.linked_attempt_id,
                    "metadata": message.metadata,
                },
            )
        )

    def get_messages(self, session_id: str, limit: int = 100) -> List[Message]:
        events = self.get_events(session_id, limit=5000)
        messages: deque[Message] = deque(maxlen=limit)
        for event in events:
            if event.event_type != SessionEventType.MESSAGE_CREATED.value:
                continue
            meta = dict(event.metadata.get("metadata") or {}) if isinstance(event.metadata, dict) else {}
            linked_attempt_id = None
            if isinstance(event.metadata, dict):
                linked_attempt_id = event.metadata.get("linked_attempt_id") or event.attempt_id
            messages.append(
                Message(
                    message_id=str((event.metadata or {}).get("message_id") or event.event_id),
                    session_id=event.session_id,
                    role=event.role or "user",
                    content=event.content or "",
                    created_at=event.timestamp,
                    linked_attempt_id=linked_attempt_id,
                    metadata=meta,
                )
            )
        return list(messages)

    # ---- Attempt CRUD ----

    def create_attempt(self, attempt: Attempt) -> Attempt:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO webui_attempts (
                    attempt_id,
                    session_id,
                    parent_attempt_id,
                    status,
                    prompt,
                    run_dir,
                    summary,
                    react_trace_json,
                    created_at,
                    completed_at,
                    error,
                    metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.attempt_id,
                    attempt.session_id,
                    attempt.parent_attempt_id,
                    attempt.status.value,
                    attempt.prompt,
                    attempt.run_dir,
                    attempt.summary,
                    json.dumps(attempt.react_trace or [], ensure_ascii=False, separators=(",", ":")),
                    attempt.created_at,
                    attempt.completed_at,
                    attempt.error,
                    json.dumps(attempt.metrics, ensure_ascii=False, separators=(",", ":")) if attempt.metrics is not None else None,
                ),
            )
            conn.commit()

        # Preserve existing attempt directory structure for compatibility.
        attempt_dir = self._session_dir(attempt.session_id) / "attempts" / attempt.attempt_id
        attempt_dir.mkdir(parents=True, exist_ok=True)

        if attempt.run_dir:
            self.register_artifact(attempt.session_id, str(attempt.run_dir), kind="run_dir")
        return attempt

    def get_attempt(self, session_id: str, attempt_id: str) -> Optional[Attempt]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    attempt_id,
                    session_id,
                    parent_attempt_id,
                    status,
                    prompt,
                    run_dir,
                    summary,
                    react_trace_json,
                    created_at,
                    completed_at,
                    error,
                    metrics_json
                FROM webui_attempts
                WHERE session_id = ? AND attempt_id = ?
                """,
                (session_id, attempt_id),
            ).fetchone()
        if row is None:
            return None
        return Attempt.from_dict(
            {
                "attempt_id": str(row["attempt_id"]),
                "session_id": str(row["session_id"]),
                "parent_attempt_id": row["parent_attempt_id"],
                "status": str(row["status"]),
                "prompt": str(row["prompt"] or ""),
                "run_dir": row["run_dir"],
                "summary": row["summary"],
                "react_trace": json.loads(str(row["react_trace_json"] or "[]")),
                "created_at": str(row["created_at"] or ""),
                "completed_at": row["completed_at"],
                "error": row["error"],
                "metrics": json.loads(str(row["metrics_json"])) if row["metrics_json"] else None,
            }
        )

    def update_attempt(self, attempt: Attempt) -> None:
        self.create_attempt(attempt)

    def list_attempts(self, session_id: str) -> List[Attempt]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    attempt_id,
                    session_id,
                    parent_attempt_id,
                    status,
                    prompt,
                    run_dir,
                    summary,
                    react_trace_json,
                    created_at,
                    completed_at,
                    error,
                    metrics_json
                FROM webui_attempts
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        attempts: List[Attempt] = []
        for row in rows:
            attempts.append(
                Attempt.from_dict(
                    {
                        "attempt_id": str(row["attempt_id"]),
                        "session_id": str(row["session_id"]),
                        "parent_attempt_id": row["parent_attempt_id"],
                        "status": str(row["status"]),
                        "prompt": str(row["prompt"] or ""),
                        "run_dir": row["run_dir"],
                        "summary": row["summary"],
                        "react_trace": json.loads(str(row["react_trace_json"] or "[]")),
                        "created_at": str(row["created_at"] or ""),
                        "completed_at": row["completed_at"],
                        "error": row["error"],
                        "metrics": json.loads(str(row["metrics_json"])) if row["metrics_json"] else None,
                    }
                )
            )
        return attempts
