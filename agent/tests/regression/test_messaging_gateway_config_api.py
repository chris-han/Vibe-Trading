from __future__ import annotations

from fastapi.testclient import TestClient
import json

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
