"""SQLite persistence layer for Feishu meeting negotiation state.

Design goals
------------
- Keep SQL standard so migration to PostgreSQL is a driver swap + placeholder change.
- Use ISO-8601 TEXT for timestamps (PG: TIMESTAMPTZ).
- Use INTEGER for booleans (0/1) — compatible with both SQLite and PG.
- Store flexible metadata in JSON TEXT columns (PG: JSONB).
- WAL mode for SQLite concurrency safety.

PG migration checklist (future)
-------------------------------
1. Swap sqlite3 for psycopg (or asyncpg).
2. Change "?" placeholders to "%s".
3. Change TEXT timestamp columns to TIMESTAMPTZ.
4. Change JSON TEXT columns to JSONB.
5. Replace PRAGMA statements with PG equivalents.
6. Use SERIAL or GENERATED ALWAYS AS IDENTITY instead of AUTOINCREMENT.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path.home() / ".semantier" / "feishu-bot-meeting-coordinator" / "meetings.db"


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS negotiations (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT,
    location        TEXT,
    requester_open_id   TEXT NOT NULL,
    requester_display_name TEXT,
    timezone        TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    duration_minutes INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft',
    current_round   INTEGER NOT NULL DEFAULT 1,
    max_rounds      INTEGER NOT NULL DEFAULT 3,
    poll_interval_minutes INTEGER NOT NULL DEFAULT 10,
    deadline_at     TEXT,
    calendar_id     TEXT,
    event_id        TEXT,
    chat_id         TEXT,
    session_id      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    finalized_at    TEXT,
    failure_reason  TEXT,
    meta_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS negotiation_rounds (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    negotiation_id      TEXT NOT NULL,
    round_number        INTEGER NOT NULL,
    proposed_start_time TEXT NOT NULL,
    proposed_end_time   TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'proposed',
    created_at          TEXT NOT NULL,
    event_id            TEXT,
    FOREIGN KEY (negotiation_id) REFERENCES negotiations(id) ON DELETE CASCADE,
    UNIQUE(negotiation_id, round_number)
);

CREATE TABLE IF NOT EXISTS attendee_responses (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    negotiation_id      TEXT NOT NULL,
    round_id            INTEGER,
    attendee_open_id    TEXT NOT NULL,
    attendee_name       TEXT,
    rsvp_status         TEXT NOT NULL DEFAULT 'pending',
    responded_at        TEXT,
    note                TEXT,
    feishu_rsvp_status  TEXT,
    FOREIGN KEY (negotiation_id) REFERENCES negotiations(id) ON DELETE CASCADE,
    FOREIGN KEY (round_id) REFERENCES negotiation_rounds(id) ON DELETE CASCADE,
    UNIQUE(negotiation_id, round_id, attendee_open_id)
);

CREATE TABLE IF NOT EXISTS poll_logs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    negotiation_id          TEXT NOT NULL,
    round_id                INTEGER,
    polled_at               TEXT NOT NULL,
    action_taken            TEXT NOT NULL DEFAULT 'checked',
    details                 TEXT,
    attendee_snapshot_json  TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (negotiation_id) REFERENCES negotiations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_negotiations_status ON negotiations(status);
CREATE INDEX IF NOT EXISTS idx_negotiations_deadline ON negotiations(deadline_at);
CREATE INDEX IF NOT EXISTS idx_rounds_negotiation ON negotiation_rounds(negotiation_id);
CREATE INDEX IF NOT EXISTS idx_responses_negotiation ON attendee_responses(negotiation_id);
CREATE INDEX IF NOT EXISTS idx_poll_logs_negotiation ON poll_logs(negotiation_id);
"""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Negotiation:
    id: str
    title: str
    description: str | None
    location: str | None
    requester_open_id: str
    requester_display_name: str | None
    timezone: str
    duration_minutes: int
    status: str
    current_round: int
    max_rounds: int
    poll_interval_minutes: int
    deadline_at: str | None
    calendar_id: str | None
    event_id: str | None
    chat_id: str | None
    session_id: str | None
    created_at: str
    updated_at: str
    finalized_at: str | None
    failure_reason: str | None
    meta: dict[str, Any]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Negotiation:
        return cls(
            id=str(row["id"]),
            title=str(row["title"]),
            description=row["description"],
            location=row["location"],
            requester_open_id=str(row["requester_open_id"]),
            requester_display_name=row["requester_display_name"],
            timezone=str(row["timezone"]),
            duration_minutes=int(row["duration_minutes"]),
            status=str(row["status"]),
            current_round=int(row["current_round"]),
            max_rounds=int(row["max_rounds"]),
            poll_interval_minutes=int(row["poll_interval_minutes"]),
            deadline_at=row["deadline_at"],
            calendar_id=row["calendar_id"],
            event_id=row["event_id"],
            chat_id=row["chat_id"],
            session_id=row["session_id"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            finalized_at=row["finalized_at"],
            failure_reason=row["failure_reason"],
            meta=json.loads(str(row["meta_json"] or "{}")),
        )


@dataclass
class NegotiationRound:
    id: int
    negotiation_id: str
    round_number: int
    proposed_start_time: str
    proposed_end_time: str
    status: str
    created_at: str
    event_id: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> NegotiationRound:
        return cls(
            id=int(row["id"]),
            negotiation_id=str(row["negotiation_id"]),
            round_number=int(row["round_number"]),
            proposed_start_time=str(row["proposed_start_time"]),
            proposed_end_time=str(row["proposed_end_time"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            event_id=row["event_id"],
        )


@dataclass
class AttendeeResponse:
    id: int
    negotiation_id: str
    round_id: int | None
    attendee_open_id: str
    attendee_name: str | None
    rsvp_status: str
    responded_at: str | None
    note: str | None
    feishu_rsvp_status: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AttendeeResponse:
        return cls(
            id=int(row["id"]),
            negotiation_id=str(row["negotiation_id"]),
            round_id=row["round_id"],
            attendee_open_id=str(row["attendee_open_id"]),
            attendee_name=row["attendee_name"],
            rsvp_status=str(row["rsvp_status"]),
            responded_at=row["responded_at"],
            note=row["note"],
            feishu_rsvp_status=row["feishu_rsvp_status"],
        )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class MeetingStore:
    """SQLite-backed persistence for meeting negotiation lifecycle."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ---- connection helpers ------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ---- negotiations ------------------------------------------------------

    def create_negotiation(
        self,
        title: str,
        requester_open_id: str,
        duration_minutes: int,
        *,
        description: str | None = None,
        location: str | None = None,
        requester_display_name: str | None = None,
        timezone: str = "Asia/Shanghai",
        max_rounds: int = 3,
        poll_interval_minutes: int = 10,
        deadline_at: str | None = None,
        chat_id: str | None = None,
        session_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str:
        """Create a new negotiation record. Returns the negotiation id."""
        negotiation_id = uuid.uuid4().hex
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO negotiations (
                    id, title, description, location,
                    requester_open_id, requester_display_name, timezone,
                    duration_minutes, status, current_round, max_rounds,
                    poll_interval_minutes, deadline_at, chat_id, session_id,
                    created_at, updated_at, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    negotiation_id,
                    title,
                    description,
                    location,
                    requester_open_id,
                    requester_display_name,
                    timezone,
                    duration_minutes,
                    "draft",
                    1,
                    max_rounds,
                    poll_interval_minutes,
                    deadline_at,
                    chat_id,
                    session_id,
                    now,
                    now,
                    json.dumps(meta or {}, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            conn.commit()
        return negotiation_id

    def get_negotiation(self, negotiation_id: str) -> Negotiation | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM negotiations WHERE id = ?",
                (negotiation_id,),
            ).fetchone()
        if row is None:
            return None
        return Negotiation.from_row(row)

    def update_negotiation(
        self,
        negotiation_id: str,
        *,
        status: str | None = None,
        current_round: int | None = None,
        calendar_id: str | None = None,
        event_id: str | None = None,
        finalized_at: str | None = None,
        failure_reason: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        """Update mutable fields. Returns True if row existed."""
        fields: list[str] = ["updated_at = ?"]
        params: list[Any] = [self._now()]

        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if current_round is not None:
            fields.append("current_round = ?")
            params.append(current_round)
        if calendar_id is not None:
            fields.append("calendar_id = ?")
            params.append(calendar_id)
        if event_id is not None:
            fields.append("event_id = ?")
            params.append(event_id)
        if finalized_at is not None:
            fields.append("finalized_at = ?")
            params.append(finalized_at)
        if failure_reason is not None:
            fields.append("failure_reason = ?")
            params.append(failure_reason)
        if meta is not None:
            fields.append("meta_json = ?")
            params.append(json.dumps(meta, ensure_ascii=False, separators=(",", ":")))

        params.append(negotiation_id)
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE negotiations SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            conn.commit()
        return cursor.rowcount > 0

    def list_active_negotiations(self) -> list[Negotiation]:
        """Return negotiations that are still in progress."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM negotiations
                WHERE status IN ('draft', 'awaiting_rsvp', 'rescheduling', 'ready_to_finalize')
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [Negotiation.from_row(r) for r in rows]

    def delete_negotiation(self, negotiation_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM negotiations WHERE id = ?",
                (negotiation_id,),
            )
            conn.commit()
        return cursor.rowcount > 0

    # ---- rounds ------------------------------------------------------------

    def add_round(
        self,
        negotiation_id: str,
        round_number: int,
        proposed_start_time: str,
        proposed_end_time: str,
        *,
        event_id: str | None = None,
    ) -> int:
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO negotiation_rounds (
                    negotiation_id, round_number, proposed_start_time,
                    proposed_end_time, status, created_at, event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    negotiation_id,
                    round_number,
                    proposed_start_time,
                    proposed_end_time,
                    "proposed",
                    now,
                    event_id,
                ),
            )
            conn.commit()
        return cursor.lastrowid or 0

    def get_rounds(self, negotiation_id: str) -> list[NegotiationRound]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM negotiation_rounds
                WHERE negotiation_id = ?
                ORDER BY round_number ASC
                """,
                (negotiation_id,),
            ).fetchall()
        return [NegotiationRound.from_row(r) for r in rows]

    def get_current_round(self, negotiation_id: str) -> NegotiationRound | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM negotiation_rounds
                WHERE negotiation_id = ?
                ORDER BY round_number DESC
                LIMIT 1
                """,
                (negotiation_id,),
            ).fetchone()
        if row is None:
            return None
        return NegotiationRound.from_row(row)

    def update_round_status(
        self, round_id: int, status: str, event_id: str | None = None
    ) -> bool:
        fields = ["status = ?"]
        params: list[Any] = [status]
        if event_id is not None:
            fields.append("event_id = ?")
            params.append(event_id)
        params.append(round_id)
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE negotiation_rounds SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            conn.commit()
        return cursor.rowcount > 0

    # ---- attendee responses ------------------------------------------------

    def upsert_attendee_response(
        self,
        negotiation_id: str,
        attendee_open_id: str,
        *,
        round_id: int | None = None,
        attendee_name: str | None = None,
        rsvp_status: str = "pending",
        responded_at: str | None = None,
        note: str | None = None,
        feishu_rsvp_status: str | None = None,
    ) -> bool:
        now = responded_at or self._now()
        with self._connect() as conn:
            # Try update first
            cursor = conn.execute(
                """
                UPDATE attendee_responses
                SET rsvp_status = ?, responded_at = ?, note = ?,
                    feishu_rsvp_status = ?, attendee_name = ?
                WHERE negotiation_id = ? AND attendee_open_id = ?
                AND (round_id IS ? OR (round_id IS NULL AND ? IS NULL))
                """,
                (
                    rsvp_status,
                    now,
                    note,
                    feishu_rsvp_status,
                    attendee_name,
                    negotiation_id,
                    attendee_open_id,
                    round_id,
                    round_id,
                ),
            )
            if cursor.rowcount == 0:
                conn.execute(
                    """
                    INSERT INTO attendee_responses (
                        negotiation_id, round_id, attendee_open_id, attendee_name,
                        rsvp_status, responded_at, note, feishu_rsvp_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        negotiation_id,
                        round_id,
                        attendee_open_id,
                        attendee_name,
                        rsvp_status,
                        now,
                        note,
                        feishu_rsvp_status,
                    ),
                )
            conn.commit()
        return True

    def get_attendee_responses(
        self, negotiation_id: str, round_id: int | None = None
    ) -> list[AttendeeResponse]:
        with self._connect() as conn:
            if round_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM attendee_responses
                    WHERE negotiation_id = ? AND round_id = ?
                    ORDER BY attendee_open_id ASC
                    """,
                    (negotiation_id, round_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM attendee_responses
                    WHERE negotiation_id = ?
                    ORDER BY attendee_open_id ASC, round_id ASC
                    """,
                    (negotiation_id,),
                ).fetchall()
        return [AttendeeResponse.from_row(r) for r in rows]

    def get_pending_attendees(
        self, negotiation_id: str, round_id: int | None = None
    ) -> list[AttendeeResponse]:
        with self._connect() as conn:
            if round_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM attendee_responses
                    WHERE negotiation_id = ? AND round_id = ? AND rsvp_status = 'pending'
                    ORDER BY attendee_open_id ASC
                    """,
                    (negotiation_id, round_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM attendee_responses
                    WHERE negotiation_id = ? AND rsvp_status = 'pending'
                    ORDER BY attendee_open_id ASC
                    """,
                    (negotiation_id,),
                ).fetchall()
        return [AttendeeResponse.from_row(r) for r in rows]

    # ---- poll logs ---------------------------------------------------------

    def log_poll(
        self,
        negotiation_id: str,
        action_taken: str,
        *,
        round_id: int | None = None,
        details: str | None = None,
        attendee_snapshot: dict[str, Any] | None = None,
    ) -> int:
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO poll_logs (
                    negotiation_id, round_id, polled_at, action_taken,
                    details, attendee_snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    negotiation_id,
                    round_id,
                    now,
                    action_taken,
                    details,
                    json.dumps(attendee_snapshot or {}, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            conn.commit()
        return cursor.lastrowid or 0

    def get_poll_logs(self, negotiation_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM poll_logs
                WHERE negotiation_id = ?
                ORDER BY polled_at DESC
                LIMIT ?
                """,
                (negotiation_id, limit),
            ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "negotiation_id": str(r["negotiation_id"]),
                "round_id": r["round_id"],
                "polled_at": str(r["polled_at"]),
                "action_taken": str(r["action_taken"]),
                "details": r["details"],
                "attendee_snapshot": json.loads(str(r["attendee_snapshot_json"] or "{}")),
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Convenience helpers for cron / CLI use
# ---------------------------------------------------------------------------

def get_store(db_path: str | None = None) -> MeetingStore:
    """Return a MeetingStore instance (creates DB if missing)."""
    return MeetingStore(db_path=db_path)


def init_db(db_path: str | None = None) -> str:
    """Initialize the database and return the path."""
    store = get_store(db_path)
    return str(store.db_path)
