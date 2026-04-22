from __future__ import annotations

import os
import sqlite3

from cryptography.fernet import Fernet

from src.auth.store import AuthStore


def test_messaging_config_is_encrypted_at_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("MESSAGING_CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    db_path = tmp_path / "auth.db"
    store = AuthStore(db_path)
    user = store.upsert_feishu_user(
        open_id="ou_test",
        union_id="on_test",
        name="Test User",
        email="test@example.com",
        avatar_url=None,
    )

    saved = store.upsert_messaging_config(
        user_id=user.user_id,
        platform="feishu",
        config={
            "app_id": "cli_123",
            "app_secret": "secret_abc123",
            "domain": "feishu",
            "connection_mode": "websocket",
        },
        validated_at="2026-04-22T00:00:00Z",
    )

    assert saved.platform == "feishu"
    assert saved.config["app_secret"] == "secret_abc123"

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT encrypted_config FROM messaging_gateway_configs WHERE user_id = ? AND platform = ?",
            (user.user_id, "feishu"),
        ).fetchone()

    assert row is not None
    encrypted = str(row[0])
    assert "secret_abc123" not in encrypted
    assert encrypted != ""


def test_messaging_config_crud_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MESSAGING_CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

    store = AuthStore(tmp_path / "auth.db")
    user = store.upsert_feishu_user(
        open_id="ou_test_2",
        union_id="on_test_2",
        name="Test User 2",
        email="test2@example.com",
        avatar_url=None,
    )

    store.upsert_messaging_config(
        user_id=user.user_id,
        platform="weixin",
        config={
            "account_id": "wx_account_1",
            "token": "wx_token_1",
            "base_url": "https://ilinkai.weixin.qq.com",
        },
        validated_at="2026-04-22T00:00:00Z",
    )

    fetched = store.get_messaging_config(user_id=user.user_id, platform="weixin")
    assert fetched is not None
    assert fetched.config["account_id"] == "wx_account_1"

    listed = store.list_messaging_configs(user_id=user.user_id)
    assert len(listed) == 1
    assert listed[0].platform == "weixin"

    assert store.delete_messaging_config(user_id=user.user_id, platform="weixin") is True
    assert store.get_messaging_config(user_id=user.user_id, platform="weixin") is None
