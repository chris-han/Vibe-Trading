"""Small control-plane store for Feishu-authenticated users and workspaces."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
import hashlib
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


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


@dataclass
class MessagingGatewayConfig:
    user_id: str
    platform: str
    config: dict[str, Any]
    created_at: str
    updated_at: str
    validated_at: str | None
    last_error: str | None


def _slugify(value: str) -> str:
    normalized = (value or "").strip().lower()
    normalized = _SLUG_RE.sub("_", normalized).strip("_")
    return normalized or "user"


def _resolve_messaging_encryption_key() -> bytes:
    configured = (os.getenv("MESSAGING_CONFIG_ENCRYPTION_KEY") or "").strip()
    if configured:
        try:
            Fernet(configured.encode("utf-8"))
            return configured.encode("utf-8")
        except Exception:
            # Allow plain passphrase input by deriving a Fernet-compatible key.
            return urlsafe_b64encode(hashlib.sha256(configured.encode("utf-8")).digest())

    # Backward-compatible fallback for existing deployments.
    fallback = (os.getenv("FEISHU_SESSION_SECRET") or "").strip()
    if fallback:
        return urlsafe_b64encode(hashlib.sha256(fallback.encode("utf-8")).digest())

    raise RuntimeError(
        "Messaging encryption key is not configured. Set MESSAGING_CONFIG_ENCRYPTION_KEY (recommended) "
        "or FEISHU_SESSION_SECRET."
    )


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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messaging_gateway_configs (
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    encrypted_config TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    validated_at TEXT,
                    last_error TEXT,
                    PRIMARY KEY (user_id, platform),
                    FOREIGN KEY(user_id) REFERENCES auth_users(user_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feishu_chat_sessions (
                    session_key TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _normalize_platform(platform: str) -> str:
        normalized = (platform or "").strip().lower()
        if normalized not in {"feishu", "weixin"}:
            raise ValueError(f"Unsupported messaging platform: {platform}")
        return normalized

    @staticmethod
    def _encrypt_config(config: dict[str, Any]) -> str:
        payload = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
        return Fernet(_resolve_messaging_encryption_key()).encrypt(payload.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _decrypt_config(ciphertext: str) -> dict[str, Any]:
        try:
            plain = Fernet(_resolve_messaging_encryption_key()).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("Failed to decrypt messaging config. Check encryption key configuration.") from exc
        parsed = json.loads(plain)
        if not isinstance(parsed, dict):
            raise RuntimeError("Messaging config payload must decode to an object.")
        return parsed

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

    def upsert_messaging_config(
        self,
        *,
        user_id: str,
        platform: str,
        config: dict[str, Any],
        validated_at: str | None = None,
        last_error: str | None = None,
    ) -> MessagingGatewayConfig:
        normalized_platform = self._normalize_platform(platform)
        now = datetime.now(timezone.utc).isoformat()
        encrypted = self._encrypt_config(config)

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM messaging_gateway_configs WHERE user_id = ? AND platform = ?",
                (user_id, normalized_platform),
            ).fetchone()
            created_at = str(existing["created_at"]) if existing else now

            conn.execute(
                """
                INSERT INTO messaging_gateway_configs (
                    user_id, platform, encrypted_config, created_at, updated_at, validated_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, platform) DO UPDATE SET
                    encrypted_config = excluded.encrypted_config,
                    updated_at = excluded.updated_at,
                    validated_at = excluded.validated_at,
                    last_error = excluded.last_error
                """,
                (
                    user_id,
                    normalized_platform,
                    encrypted,
                    created_at,
                    now,
                    validated_at,
                    last_error,
                ),
            )
            conn.commit()

            row = conn.execute(
                """
                SELECT user_id, platform, encrypted_config, created_at, updated_at, validated_at, last_error
                FROM messaging_gateway_configs
                WHERE user_id = ? AND platform = ?
                """,
                (user_id, normalized_platform),
            ).fetchone()

        assert row is not None
        return self._row_to_messaging_config(row)

    def get_messaging_config(self, *, user_id: str, platform: str) -> MessagingGatewayConfig | None:
        normalized_platform = self._normalize_platform(platform)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id, platform, encrypted_config, created_at, updated_at, validated_at, last_error
                FROM messaging_gateway_configs
                WHERE user_id = ? AND platform = ?
                """,
                (user_id, normalized_platform),
            ).fetchone()
        return self._row_to_messaging_config(row) if row else None

    def list_messaging_configs(self, *, user_id: str) -> list[MessagingGatewayConfig]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, platform, encrypted_config, created_at, updated_at, validated_at, last_error
                FROM messaging_gateway_configs
                WHERE user_id = ?
                ORDER BY platform ASC
                """,
                (user_id,),
            ).fetchall()
        return [self._row_to_messaging_config(row) for row in rows]

    def delete_messaging_config(self, *, user_id: str, platform: str) -> bool:
        normalized_platform = self._normalize_platform(platform)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM messaging_gateway_configs WHERE user_id = ? AND platform = ?",
                (user_id, normalized_platform),
            )
            conn.commit()
        return cursor.rowcount > 0

    def get_feishu_chat_session(self, *, session_key: str) -> str | None:
        key = str(session_key or "").strip()
        if not key:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id FROM feishu_chat_sessions WHERE session_key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        session_id = str(row["session_id"] or "").strip()
        return session_id or None

    def upsert_feishu_chat_session(self, *, session_key: str, session_id: str) -> None:
        key = str(session_key or "").strip()
        sid = str(session_id or "").strip()
        if not key or not sid:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feishu_chat_sessions (session_key, session_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET
                    session_id = excluded.session_id,
                    updated_at = excluded.updated_at
                """,
                (key, sid, now),
            )
            conn.commit()

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

    @classmethod
    def _row_to_messaging_config(cls, row: sqlite3.Row) -> MessagingGatewayConfig:
        return MessagingGatewayConfig(
            user_id=str(row["user_id"]),
            platform=str(row["platform"]),
            config=cls._decrypt_config(str(row["encrypted_config"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            validated_at=str(row["validated_at"]) if row["validated_at"] else None,
            last_error=str(row["last_error"]) if row["last_error"] else None,
        )
