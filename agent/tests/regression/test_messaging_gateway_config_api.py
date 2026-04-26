from __future__ import annotations

import asyncio
from fastapi.testclient import TestClient
import json
import subprocess

import api_server


def _patch_isolated_auth_runtime(tmp_path, monkeypatch):
    workspaces_dir = tmp_path / "workspaces"
    control_dir = tmp_path / ".auth"
    monkeypatch.setattr(api_server, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(api_server, "AUTH_CONTROL_DIR", control_dir)
    monkeypatch.setattr(api_server, "_auth_store", None, raising=False)
    monkeypatch.setattr(api_server, "_auth_store_path", None, raising=False)
    monkeypatch.setenv("FEISHU_OAUTH_ENABLED", "true")
    monkeypatch.setenv("FEISHU_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("FEISHU_OAUTH_APP_ID", "cli_test_app")
    monkeypatch.setenv("FEISHU_OAUTH_REDIRECT_URI", "http://testserver/auth/feishu/callback")
    monkeypatch.setenv(
        "MESSAGING_CONFIG_ENCRYPTION_KEY",
        "m83nHgnx4H6fjf3ScsOHA2hO8_m3i3UV7hN5j2q8V8o=",
    )


def _login(client: TestClient, monkeypatch):
    monkeypatch.setattr(
        api_server,
        "_feishu_exchange_oauth_code",
        lambda code, redirect_uri=None: {"access_token": f"token-{code}"},
    )
    monkeypatch.setattr(
        api_server,
        "_feishu_fetch_user_profile",
        lambda access_token: {
            "open_id": "ou_alice",
            "union_id": "on_alice",
            "name": "Alice",
            "email": "alice@example.com",
        },
    )
    response = client.get("/auth/feishu/callback?code=abc123&state=test", follow_redirects=False)
    assert response.status_code in (302, 307)


def test_messaging_platforms_requires_auth(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)
    client = TestClient(api_server.app)

    response = client.get("/messaging/platforms")

    assert response.status_code == 401


def test_messaging_platform_crud_flow(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)
    client = TestClient(api_server.app)
    _login(client, monkeypatch)

    monkeypatch.setattr(
        api_server,
        "_validate_messaging_config",
        lambda platform, config: {
            "platform": platform,
            "valid": True,
            "summary": "ok",
            "details": {"platform": platform},
        },
    )

    save_response = client.put(
        "/messaging/feishu",
        json={
            "config": {
                "app_id": "cli_123",
                "app_secret": "super-secret",
                "domain": "feishu",
                "connection_mode": "websocket",
            }
        },
    )
    assert save_response.status_code == 200, save_response.text
    saved_payload = save_response.json()
    assert saved_payload["configured"] is True
    assert saved_payload["platform"] == "feishu"
    assert saved_payload["config"]["app_secret"] != "super-secret"

    list_response = client.get("/messaging/platforms")
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    feishu = next(item for item in list_payload["platforms"] if item["platform"] == "feishu")
    assert feishu["configured"] is True
    assert feishu["config"]["app_secret"] != "super-secret"

    validate_response = client.post(
        "/messaging/feishu/validate",
        json={"config": {"app_id": "cli_123", "app_secret": "super-secret"}},
    )
    assert validate_response.status_code == 200, validate_response.text
    validate_payload = validate_response.json()
    assert validate_payload["valid"] is True
    assert validate_payload["masked_config"]["app_secret"] != "super-secret"

    delete_response = client.delete("/messaging/feishu")
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["deleted"] is True


def test_delete_weixin_clears_gateway_runtime_state(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)
    client = TestClient(api_server.app)
    _login(client, monkeypatch)

    monkeypatch.setattr(
        api_server,
        "_validate_messaging_config",
        lambda platform, config: {
            "platform": platform,
            "valid": True,
            "summary": "ok",
            "details": {},
        },
    )

    removed_platforms: list[str] = []
    cleared_account_flags: list[bool] = []
    restart_calls: list[bool] = []

    monkeypatch.setattr(api_server, "_apply_messaging_config_to_gateway_yaml", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        api_server,
        "_remove_messaging_config_from_gateway_yaml",
        lambda hermes_home, platform: (removed_platforms.append(platform) or True),
    )
    monkeypatch.setattr(
        api_server,
        "_clear_weixin_account_cache",
        lambda hermes_home, **kwargs: (cleared_account_flags.append(bool(kwargs.get("remove_all"))) or True),
    )
    monkeypatch.setattr(
        api_server,
        "_ensure_workspace_gateway_running",
        lambda hermes_home, **kwargs: (restart_calls.append(bool(kwargs.get("force_restart"))) or True),
    )

    save_response = client.put(
        "/messaging/weixin",
        json={
            "config": {
                "account_id": "wx_account_delete",
                "token": "wx_token_delete",
                "base_url": "https://ilinkai.weixin.qq.com",
            }
        },
    )
    assert save_response.status_code == 200, save_response.text

    removed_platforms.clear()
    cleared_account_flags.clear()
    restart_calls.clear()

    delete_response = client.delete("/messaging/weixin")
    assert delete_response.status_code == 200, delete_response.text
    payload = delete_response.json()
    assert payload["deleted"] is True
    assert payload["gateway_applied"] is True
    assert payload["gateway_restarted"] is True
    assert payload["had_existing_config"] is True

    assert removed_platforms == ["weixin"]
    assert cleared_account_flags == [True]
    assert restart_calls == [True]


def test_weixin_qrcode_flow(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)
    client = TestClient(api_server.app)
    _login(client, monkeypatch)
    applied_configs: list[dict] = []
    started_gateway_homes: list[str] = []

    def _stub_apply(hermes_home, platform, config):
        assert platform == "weixin"
        applied_configs.append(dict(config))
        return True

    monkeypatch.setattr(api_server, "_apply_messaging_config_to_gateway_yaml", _stub_apply)
    monkeypatch.setattr(
        api_server,
        "_start_workspace_hermes_gateway",
        lambda hermes_home, **kwargs: (
            started_gateway_homes.append(str(hermes_home))
            or {"ok": True, "message": "started"}
        ),
    )

    class _StubResponse:
        def __init__(self, payload: dict):
            self.status_code = 200
            self.text = json.dumps(payload)
            self._payload = payload

        def json(self):
            return self._payload

    def _stub_get(url, params=None, headers=None, timeout=10):
        if url.endswith("/ilink/bot/get_bot_qrcode"):
            assert params == {"bot_type": "3"}
            return _StubResponse(
                {
                    "qrcode": "qr_abc",
                    "qrcode_img_content": "https://qr.example.com/abc",
                }
            )
        if url.endswith("/ilink/bot/get_qrcode_status"):
            assert params == {"qrcode": "qr_abc"}
            return _StubResponse(
                {
                    "status": "confirmed",
                    "ilink_bot_id": "wx_account_2",
                    "bot_token": "wx_token_2",
                    "baseurl": "https://ilinkai.weixin.qq.com",
                    "ilink_user_id": "wx_user_2",
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(api_server.requests, "get", _stub_get)

    qr_response = client.post("/messaging/weixin/qrcode", json={})
    assert qr_response.status_code == 200, qr_response.text
    qr_payload = qr_response.json()
    assert qr_payload["qrcode"] == "qr_abc"
    assert qr_payload["qrcode_url"] == "https://qr.example.com/abc"

    status_response = client.get(
        "/messaging/weixin/qrcode/status",
        params={"qrcode": "qr_abc", "base_url": "https://ilinkai.weixin.qq.com"},
    )
    assert status_response.status_code == 200, status_response.text
    status_payload = status_response.json()
    assert status_payload["status"] == "confirmed"
    assert status_payload["credentials"]["account_id"] == "wx_account_2"
    assert status_payload["credentials"]["token"] == "wx_token_2"

    list_response = client.get("/messaging/platforms")
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    weixin = next(item for item in list_payload["platforms"] if item["platform"] == "weixin")
    assert weixin["configured"] is True
    assert weixin["config"]["account_id"] == "wx_account_2"
    assert weixin["config"]["base_url"] == "https://ilinkai.weixin.qq.com"
    assert weixin["config"]["token"] != "wx_token_2"
    assert applied_configs and applied_configs[0]["token"] == "wx_token_2"

    workspace_dirs = [item for item in (tmp_path / "workspaces").iterdir() if item.is_dir()]
    assert len(workspace_dirs) == 1
    account_file = workspace_dirs[0] / ".hermes" / "weixin" / "accounts" / "wx_account_2.json"
    assert account_file.exists()
    account_payload = json.loads(account_file.read_text(encoding="utf-8"))
    assert account_payload["token"] == "wx_token_2"
    assert account_payload["base_url"] == "https://ilinkai.weixin.qq.com"
    assert account_payload["user_id"] == "wx_user_2"
    assert started_gateway_homes


def test_weixin_save_creates_account_cache_file(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)
    client = TestClient(api_server.app)
    _login(client, monkeypatch)

    monkeypatch.setattr(
        api_server,
        "_validate_messaging_config",
        lambda platform, config: {
            "platform": platform,
            "valid": True,
            "summary": "ok",
            "details": {},
        },
    )
    started_gateway_homes: list[str] = []
    monkeypatch.setattr(
        api_server,
        "_start_workspace_hermes_gateway",
        lambda hermes_home, **kwargs: (
            started_gateway_homes.append(str(hermes_home))
            or {"ok": True, "message": "started"}
        ),
    )

    response = client.put(
        "/messaging/weixin",
        json={
            "config": {
                "account_id": "wx_account_direct",
                "token": "wx_token_direct",
                "base_url": "https://ilinkai.weixin.qq.com",
                "dm_policy": "pairing",
            }
        },
    )
    assert response.status_code == 200, response.text

    workspace_dirs = [item for item in (tmp_path / "workspaces").iterdir() if item.is_dir()]
    assert len(workspace_dirs) == 1
    account_file = workspace_dirs[0] / ".hermes" / "weixin" / "accounts" / "wx_account_direct.json"
    assert account_file.exists()
    payload = json.loads(account_file.read_text(encoding="utf-8"))
    assert payload["token"] == "wx_token_direct"
    assert payload["base_url"] == "https://ilinkai.weixin.qq.com"
    assert started_gateway_homes


def test_weixin_qrcode_status_timeout_is_transient_wait(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)
    client = TestClient(api_server.app)
    _login(client, monkeypatch)

    def _stub_get(url, params=None, headers=None, timeout=10):
        if url.endswith("/ilink/bot/get_qrcode_status"):
            raise api_server.requests.Timeout("read timed out")
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(api_server.requests, "get", _stub_get)

    status_response = client.get(
        "/messaging/weixin/qrcode/status",
        params={"qrcode": "qr_timeout", "base_url": "https://ilinkai.weixin.qq.com"},
    )

    assert status_response.status_code == 200, status_response.text
    payload = status_response.json()
    assert payload["status"] == "wait"
    assert payload["credentials"] is None
    assert payload["raw"].get("transient_error") == "timeout"


def test_backfill_weixin_gateway_sessions_to_backend_store(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    workspace = api_server.ensure_workspace(
        api_server.WORKSPACES_DIR,
        "ou_alice",
        api_server._TEMPLATE_HERMES_HOME,
        workspace_slug="ou_alice",
    )

    gateway_sessions_dir = workspace.hermes_home / "sessions"
    gateway_sessions_dir.mkdir(parents=True, exist_ok=True)

    sessions_index = {
        "agent:main:weixin:dm:wx_chat_001": {
            "session_id": "wx_session_001",
            "created_at": "2026-04-23T08:00:00",
            "updated_at": "2026-04-23T08:10:00",
            "platform": "weixin",
            "display_name": "Weixin Chat 001",
            "origin": {
                "platform": "weixin",
                "chat_id": "wx_chat_001",
                "chat_name": "Weixin Chat 001",
                "chat_type": "dm",
                "user_id": "wx_user_001",
                "user_name": "Alice Weixin",
            },
        },
        "agent:main:telegram:dm:tg_chat_001": {
            "session_id": "other_session_001",
            "created_at": "2026-04-23T08:00:00",
            "updated_at": "2026-04-23T08:10:00",
            "platform": "telegram",
        },
    }

    (gateway_sessions_dir / "sessions.json").write_text(
        json.dumps(sessions_index),
        encoding="utf-8",
    )
    (gateway_sessions_dir / "wx_session_001.jsonl").write_text(
        json.dumps({"role": "user", "content": "hello"}) + "\n",
        encoding="utf-8",
    )

    from src.session.store import SessionStore

    store = SessionStore(base_dir=workspace.sessions_dir)
    created = api_server._backfill_weixin_gateway_sessions_to_store(workspace, store)
    assert created == 1

    session = store.get_session("wx_session_001")
    assert session is not None
    assert (session.config or {}).get("channel") == "weixin"
    assert (session.config or {}).get("gateway_session_key") == "agent:main:weixin:dm:wx_chat_001"
    assert store.get_session("other_session_001") is None
    auth_store = api_server._get_auth_store()
    assert (
        auth_store.get_weixin_chat_session(
            owner_user_id="ou_alice",
            session_key="agent:main:weixin:dm:wx_chat_001",
        )
        == "wx_session_001"
    )
    artifact_paths = [entry["path"] for entry in store.list_artifacts("wx_session_001")]
    assert str(gateway_sessions_dir / "wx_session_001.jsonl") in artifact_paths


def test_backfill_skips_weixin_sessions_marked_deleted(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    workspace = api_server.ensure_workspace(
        api_server.WORKSPACES_DIR,
        "ou_alice_deleted",
        api_server._TEMPLATE_HERMES_HOME,
        workspace_slug="ou_alice_deleted",
    )

    gateway_sessions_dir = workspace.hermes_home / "sessions"
    gateway_sessions_dir.mkdir(parents=True, exist_ok=True)

    session_key = "agent:main:weixin:dm:wx_chat_deleted"
    session_id = "wx_session_deleted"

    sessions_index = {
        session_key: {
            "session_id": session_id,
            "created_at": "2026-04-23T08:00:00",
            "updated_at": "2026-04-23T08:10:00",
            "platform": "weixin",
            "display_name": "Deleted Weixin Chat",
            "origin": {
                "platform": "weixin",
                "chat_id": "wx_chat_deleted",
                "chat_name": "Deleted Weixin Chat",
                "chat_type": "dm",
                "user_id": "wx_user_deleted",
            },
        }
    }

    (gateway_sessions_dir / "sessions.json").write_text(
        json.dumps(sessions_index),
        encoding="utf-8",
    )
    (gateway_sessions_dir / f"session_{session_id}.json").write_text(
        json.dumps({"session_id": session_id, "platform": "weixin"}),
        encoding="utf-8",
    )

    from src.session.store import SessionStore

    store = SessionStore(base_dir=workspace.sessions_dir)
    created = api_server._backfill_weixin_gateway_sessions_to_store(workspace, store)
    assert created == 1
    assert store.get_session(session_id) is not None

    api_server._mark_weixin_gateway_sessions_deleted(
        workspace,
        [{"session_id": session_id, "session_key": session_key}],
    )

    # Simulate a user deletion in WebUI: local session removed, then list triggers backfill.
    assert store.delete_session(session_id) is True
    assert store.get_session(session_id) is None

    recreated = api_server._backfill_weixin_gateway_sessions_to_store(workspace, store)
    assert recreated == 0
    assert store.get_session(session_id) is None

    deleted_markers_path = gateway_sessions_dir / "deleted_sessions.json"
    assert deleted_markers_path.exists()
    deleted_payload = json.loads(deleted_markers_path.read_text(encoding="utf-8"))
    assert session_id in deleted_payload.get("session_ids", [])
    assert session_key in deleted_payload.get("session_keys", [])

    updated_index = json.loads((gateway_sessions_dir / "sessions.json").read_text(encoding="utf-8"))
    assert session_key not in updated_index
    assert not (gateway_sessions_dir / f"session_{session_id}.json").exists()


def test_sync_gateway_messages_into_backend_session_store(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    workspace = api_server.ensure_workspace(
        api_server.WORKSPACES_DIR,
        "ou_alice_sync",
        api_server._TEMPLATE_HERMES_HOME,
        workspace_slug="ou_alice_sync",
    )

    from src.session.models import Session
    from src.session.store import SessionStore

    store = SessionStore(base_dir=workspace.sessions_dir)
    session = Session(
        session_id="wx_session_sync_001",
        title="Weixin:sync",
        config={
            "channel": "weixin",
            "source": "gateway",
            "gateway_session_key": "agent:main:weixin:dm:wx_sync_001",
        },
    )
    store.create_session(session)

    import sqlite3

    state_db = workspace.hermes_home / "state.db"
    state_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state_db)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT,
                content TEXT,
                timestamp REAL
            )
            """
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            ("wx_session_sync_001", "user", "hi", 1776917520.0),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            ("wx_session_sync_001", "assistant", "hello", 1776917521.0),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            ("wx_session_sync_001", "session_meta", "ignored", 1776917522.0),
        )
        conn.commit()
    finally:
        conn.close()

    created_first = api_server._sync_gateway_session_messages_to_store(
        workspace,
        store,
        "wx_session_sync_001",
        limit=100,
    )
    assert created_first == 2

    projected = store.get_messages("wx_session_sync_001", limit=50)
    assert [m.role for m in projected] == ["user", "assistant"]
    assert [m.content for m in projected] == ["hi", "hello"]

    # Re-sync should be idempotent due to persisted cursor in session config.
    created_second = api_server._sync_gateway_session_messages_to_store(
        workspace,
        store,
        "wx_session_sync_001",
        limit=100,
    )
    assert created_second == 0
    projected_after = store.get_messages("wx_session_sync_001", limit=50)
    assert len(projected_after) == 2

    saved_session = store.get_session("wx_session_sync_001")
    assert saved_session is not None
    assert int((saved_session.config or {}).get("gateway_last_state_message_id", 0)) >= 2


def test_send_message_projects_gateway_session_messages_back_to_state_db(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    workspace = api_server.ensure_workspace(
        api_server.WORKSPACES_DIR,
        "ou_alice_reverse_sync",
        api_server._TEMPLATE_HERMES_HOME,
        workspace_slug="ou_alice_reverse_sync",
    )

    from src.session.events import EventBus
    from src.session.models import Session
    from src.session.service import SessionService
    from src.session.store import SessionStore

    store = SessionStore(base_dir=workspace.sessions_dir)
    session = Session(
        session_id="wx_session_reverse_sync_001",
        title="Weixin:reverse-sync",
        config={
            "channel": "weixin",
            "source": "gateway",
            "gateway_session_key": "agent:main:weixin:dm:wx_reverse_sync_001",
        },
    )
    store.create_session(session)

    async def _stub_run_with_agent(self, attempt, messages):
        return {"status": "success", "content": "Synced reply from WebUI."}

    monkeypatch.setattr(SessionService, "_run_with_agent", _stub_run_with_agent)

    svc = SessionService(
        store=store,
        event_bus=EventBus(),
        runs_dir=workspace.runs_dir,
        swarm_dir=workspace.swarm_dir,
        hermes_home=workspace.hermes_home,
        message_projection_hook=lambda sess, msg: api_server._append_message_to_gateway_state_db(
            workspace,
            sess,
            msg,
        ),
    )

    async def _exercise() -> None:
        result = await svc.send_message("wx_session_reverse_sync_001", "continue from webui")
        assert result["message_id"]
        assert result["attempt_id"]
        for _ in range(20):
            projected = store.get_messages("wx_session_reverse_sync_001", limit=20)
            if len(projected) >= 2:
                return
            await asyncio.sleep(0)
        raise AssertionError("assistant reply was not persisted")

    asyncio.run(_exercise())

    import sqlite3

    con = sqlite3.connect(workspace.hermes_home / "state.db")
    try:
        rows = con.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
            ("wx_session_reverse_sync_001",),
        ).fetchall()
    finally:
        con.close()

    assert [row[0] for row in rows] == ["user", "assistant"]
    assert rows[0][1] == "continue from webui"
    assert rows[1][1] == "Synced reply from WebUI."


def test_weixin_qrcode_flow_accepts_alternate_user_id_key(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)
    client = TestClient(api_server.app)
    _login(client, monkeypatch)

    monkeypatch.setattr(api_server, "_apply_messaging_config_to_gateway_yaml", lambda *args, **kwargs: True)
    monkeypatch.setattr(api_server, "_start_workspace_hermes_gateway", lambda *args, **kwargs: {"ok": True})

    class _StubResponse:
        def __init__(self, payload: dict):
            self.status_code = 200
            self.text = json.dumps(payload)
            self._payload = payload

        def json(self):
            return self._payload

    def _stub_get(url, params=None, headers=None, timeout=10):
        if url.endswith("/ilink/bot/get_qrcode_status"):
            return _StubResponse(
                {
                    "status": "confirmed",
                    "ilink_bot_id": "wx_account_alt",
                    "bot_token": "wx_token_alt",
                    "baseurl": "https://ilinkai.weixin.qq.com",
                    "user_id": "wx_user_alt",
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(api_server.requests, "get", _stub_get)

    status_response = client.get(
        "/messaging/weixin/qrcode/status",
        params={"qrcode": "qr_alt", "base_url": "https://ilinkai.weixin.qq.com"},
    )
    assert status_response.status_code == 200, status_response.text
    payload = status_response.json()
    assert payload["credentials"]["user_id"] == "wx_user_alt"

    workspace_dirs = [item for item in (tmp_path / "workspaces").iterdir() if item.is_dir()]
    assert len(workspace_dirs) == 1
    account_file = workspace_dirs[0] / ".hermes" / "weixin" / "accounts" / "wx_account_alt.json"
    assert account_file.exists()
    account_payload = json.loads(account_file.read_text(encoding="utf-8"))
    assert account_payload["user_id"] == "wx_user_alt"


def test_weixin_pairing_pending_and_approve_api(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)
    client = TestClient(api_server.app)
    _login(client, monkeypatch)

    class _StubPairingStore:
        def __init__(self):
            self.approved_codes: list[str] = []

        def list_pending(self, platform: str):
            assert platform == "weixin"
            return [
                {
                    "platform": "weixin",
                    "code": "ABCD2345",
                    "user_id": "wx_user_1",
                    "user_name": "Alice",
                    "age_minutes": 3,
                }
            ]

        def approve_code(self, platform: str, code: str):
            assert platform == "weixin"
            normalized = code.strip().upper()
            if normalized != "ABCD2345":
                return None
            self.approved_codes.append(normalized)
            return {"user_id": "wx_user_1", "user_name": "Alice"}

    stub_store = _StubPairingStore()
    monkeypatch.setattr(api_server, "_with_workspace_pairing_store", lambda workspace: stub_store)

    pending_response = client.get("/messaging/weixin/pairing/pending")
    assert pending_response.status_code == 200, pending_response.text
    pending_payload = pending_response.json()
    assert pending_payload["platform"] == "weixin"
    assert len(pending_payload["pending"]) == 1
    assert pending_payload["pending"][0]["code"] == "ABCD2345"

    approve_response = client.post(
        "/messaging/weixin/pairing/approve",
        json={"code": "ABCD2345"},
    )
    assert approve_response.status_code == 200, approve_response.text
    approve_payload = approve_response.json()
    assert approve_payload["ok"] is True
    assert approve_payload["platform"] == "weixin"
    assert approve_payload["user_id"] == "wx_user_1"

    bad_response = client.post(
        "/messaging/weixin/pairing/approve",
        json={"code": "BADCODE"},
    )
    assert bad_response.status_code == 400, bad_response.text


def test_start_hermes_gateway_api(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)
    client = TestClient(api_server.app)
    _login(client, monkeypatch)

    monkeypatch.setattr(
        api_server,
        "_start_workspace_hermes_gateway",
        lambda hermes_home, **kwargs: {"ok": True, "pid": 12345, "message": "started"},
    )

    response = client.post("/api/start-hermes")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["pid"] == 12345
    assert payload["message"] == "started"


def test_start_workspace_gateway_uses_backend_python(tmp_path, monkeypatch):
    hermes_home = tmp_path / "workspace" / ".hermes"
    hermes_home.mkdir(parents=True)

    backend_agent_dir = tmp_path / "agent"
    backend_python = backend_agent_dir / ".venv" / "bin" / "python"
    backend_python.parent.mkdir(parents=True)
    backend_python.write_text("", encoding="utf-8")

    hermes_agent_dir = tmp_path / "hermes-agent"
    (hermes_agent_dir / "gateway").mkdir(parents=True)
    (hermes_agent_dir / "gateway" / "run.py").write_text("", encoding="utf-8")
    hermes_python = hermes_agent_dir / ".venv" / "bin" / "python"
    hermes_python.parent.mkdir(parents=True)
    hermes_python.write_text("", encoding="utf-8")

    popen_calls: list[dict] = []

    class _StubProcess:
        pid = 43210

    def _stub_popen(argv, cwd=None, env=None, **kwargs):
        popen_calls.append({"argv": argv, "cwd": cwd, "env": env, "kwargs": kwargs})
        return _StubProcess()

    monkeypatch.setattr(api_server, "_AGENT_DIR", backend_agent_dir)
    monkeypatch.setattr(api_server, "_resolve_hermes_agent_dir", lambda: hermes_agent_dir)
    monkeypatch.setattr(api_server, "_ensure_gateway_health_webhook", lambda hermes_home: None)
    monkeypatch.setattr(api_server, "_sync_workspace_provider_api_key", lambda hermes_home, env: None)
    monkeypatch.setattr(api_server, "_is_gateway_healthy", lambda: False)
    monkeypatch.setattr(api_server, "_HERMES_GATEWAY_START_ATTEMPTS", 1)
    monkeypatch.setattr(api_server.time, "sleep", lambda _: None)
    monkeypatch.setattr(api_server._sys, "executable", str(backend_python))
    monkeypatch.setattr(subprocess, "Popen", _stub_popen)

    result = api_server._start_workspace_hermes_gateway(hermes_home)

    assert result["ok"] is True
    assert popen_calls
    call = popen_calls[0]
    assert call["argv"][0] == str(backend_python)
    assert call["cwd"] == str(hermes_agent_dir)
    assert call["env"]["HERMES_PYTHON"] == str(backend_python)
    assert call["env"]["VIRTUAL_ENV"] == str(backend_agent_dir / ".venv")
