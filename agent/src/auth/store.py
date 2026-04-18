"""Small control-plane store for Feishu-authenticated users and workspaces."""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class AuthUser:
    user_id: str
    feishu_open_id: str
    feishu_union_id: str | None
    name: str
    email: str | None
    avatar_url: str | None
    workspace_slug: str
    created_at: str
    updated_at: str


def _slugify(value: str) -> str:
    normalized = (value or "").strip().lower()
    normalized = _SLUG_RE.sub("_", normalized).strip("_")
    return normalized or "user"


class AuthStore:
    """SQLite-backed auth/user mapping store."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    user_id TEXT PRIMARY KEY,
                    feishu_open_id TEXT NOT NULL UNIQUE,
                    feishu_union_id TEXT,
                    name TEXT NOT NULL,
                    email TEXT,
                    avatar_url TEXT,
                    workspace_slug TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _next_workspace_slug(self, conn: sqlite3.Connection, base_slug: str) -> str:
        slug = base_slug
        suffix = 2
        while conn.execute(
            "SELECT 1 FROM auth_users WHERE workspace_slug = ?",
            (slug,),
        ).fetchone():
            slug = f"{base_slug}_{suffix}"
            suffix += 1
        return slug

    def upsert_feishu_user(
        self,
        *,
        open_id: str,
        union_id: str | None,
        name: str,
        email: str | None,
        avatar_url: str | None,
    ) -> AuthUser:
        now = datetime.now(timezone.utc).isoformat()
        display_name = (name or email or open_id or "user").strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_users WHERE feishu_open_id = ?",
                (open_id,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE auth_users
                    SET feishu_union_id = ?, name = ?, email = ?, avatar_url = ?, updated_at = ?
                    WHERE feishu_open_id = ?
                    """,
                    (union_id, display_name, email, avatar_url, now, open_id),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM auth_users WHERE feishu_open_id = ?",
                    (open_id,),
                ).fetchone()
                assert row is not None
                return self._row_to_user(row)

            base_slug = _slugify(display_name)
            workspace_slug = self._next_workspace_slug(conn, base_slug)
            user_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO auth_users (
                    user_id, feishu_open_id, feishu_union_id, name, email, avatar_url,
                    workspace_slug, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    open_id,
                    union_id,
                    display_name,
                    email,
                    avatar_url,
                    workspace_slug,
                    now,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM auth_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            assert row is not None
            return self._row_to_user(row)

    def get_user_by_id(self, user_id: str) -> AuthUser | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_feishu_open_id(self, open_id: str) -> AuthUser | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_users WHERE feishu_open_id = ?",
                (open_id,),
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_feishu_union_id(self, union_id: str) -> AuthUser | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_users WHERE feishu_union_id = ?",
                (union_id,),
            ).fetchone()
        return self._row_to_user(row) if row else None

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> AuthUser:
        return AuthUser(
            user_id=str(row["user_id"]),
            feishu_open_id=str(row["feishu_open_id"]),
            feishu_union_id=row["feishu_union_id"],
            name=str(row["name"]),
            email=row["email"],
            avatar_url=row["avatar_url"],
            workspace_slug=str(row["workspace_slug"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
