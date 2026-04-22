from __future__ import annotations

from fastapi.testclient import TestClient

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
