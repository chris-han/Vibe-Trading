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
