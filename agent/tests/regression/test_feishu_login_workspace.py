import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

import api_server


def _patch_isolated_auth_runtime(tmp_path, monkeypatch):
    workspaces_dir = tmp_path / "workspaces"
    control_dir = tmp_path / ".auth"
    session_map_file = tmp_path / ".feishu_sessions.json"
    monkeypatch.setattr(api_server, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(api_server, "AUTH_CONTROL_DIR", control_dir)
    monkeypatch.setattr(api_server, "_FEISHU_SESSION_MAP_FILE", session_map_file)
    # Patch these too as they might be imported or used from globals
    monkeypatch.setattr(api_server, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(api_server, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(api_server, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setenv("FEISHU_OAUTH_ENABLED", "true")
    monkeypatch.setenv("FEISHU_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("FEISHU_OAUTH_APP_ID", "cli_test_app")
    monkeypatch.setenv("FEISHU_OAUTH_REDIRECT_URI", "http://testserver/auth/feishu/callback")
    monkeypatch.setenv("ENABLE_SESSION_RUNTIME", "true")
    monkeypatch.setattr(api_server, "_session_service_by_workspace", {}, raising=False)
    monkeypatch.setattr(api_server, "_session_service", None, raising=False)
    return workspaces_dir


class _FakeFeishuSession:
    def __init__(self, session_id):
        self.session_id = session_id


class _FakeFeishuService:
    def __init__(self, slug):
        self.slug = slug
        self.sessions = {}
        self.sent = []

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def create_session(self, title, config):
        session_id = f"{self.slug}-session-{len(self.sessions) + 1}"
        session = _FakeFeishuSession(session_id)
        self.sessions[session_id] = {"session": session, "title": title, "config": config}
        return session

    async def send_message(self, session_id, content):
        self.sent.append({"session_id": session_id, "content": content})
        return {"attempt_id": None}


def test_feishu_callback_bootstraps_workspace_and_sets_session_cookie(tmp_path, monkeypatch):
    workspaces_dir = _patch_isolated_auth_runtime(tmp_path, monkeypatch)

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
            "name": "Alice Zhang",
            "en_name": "Alice Zhang",
            "avatar_url": "https://example.com/alice.png",
            "email": "alice@example.com",
        },
    )

    client = TestClient(api_server.app)
    response = client.get("/auth/feishu/callback?code=abc123&state=state-1", follow_redirects=False)

    assert response.status_code in (302, 307), response.text
    assert "vt_session" in response.cookies


def test_system_paths_reports_active_hermes_home(tmp_path, monkeypatch):
    hermes_home = tmp_path / "backend-hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    client = TestClient(api_server.app)
    response = client.get("/system/paths")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["hermesHome"] == str(hermes_home.resolve())
    assert Path(payload["dataRoot"]).exists()


def test_system_paths_reports_public_workspace_for_anonymous_user(tmp_path, monkeypatch):
    workspaces_dir = _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    client = TestClient(api_server.app)
    response = client.get("/system/paths")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["authenticated"] is False
    assert payload["currentWorkspaceId"] == "public"
    assert payload["currentWorkspaceSlug"] == "public"
    assert payload["currentWorkspaceRoot"] == str((workspaces_dir / "public").resolve())
    assert Path(payload["currentWorkspaceRoot"]).is_dir()


def test_system_paths_reports_authenticated_workspace_root(tmp_path, monkeypatch):
    workspaces_dir = _patch_isolated_auth_runtime(tmp_path, monkeypatch)

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
            "name": "Alice Zhang",
            "en_name": "Alice Zhang",
            "avatar_url": "https://example.com/alice.png",
            "email": "alice@example.com",
        },
    )

    client = TestClient(api_server.app)
    callback = client.get("/auth/feishu/callback?code=abc123&state=state-1", follow_redirects=False)

    assert callback.status_code in (302, 307), callback.text

    response = client.get("/system/paths")

    assert response.status_code == 200, response.text
    payload = response.json()
    user = client.get("/auth/me").json()["user"]

    assert payload["authenticated"] is True
    assert payload["currentWorkspaceId"] == user["user_id"]
    assert payload["currentWorkspaceSlug"] == user["workspace_slug"]
    assert payload["currentWorkspaceRoot"] == str((workspaces_dir / user["user_id"]).resolve())
    assert Path(payload["currentWorkspaceRoot"]).is_dir()


def test_feishu_login_auto_enables_when_oauth_config_is_present(monkeypatch):
    monkeypatch.delenv("FEISHU_OAUTH_ENABLED", raising=False)
    monkeypatch.setenv("FEISHU_OAUTH_APP_ID", "cli_test_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "oauth-secret")
    monkeypatch.setenv("FEISHU_OAUTH_REDIRECT_URI", "http://testserver/auth/feishu/callback")
    monkeypatch.setenv("FEISHU_SESSION_SECRET", "test-secret")

    client = TestClient(api_server.app)
    response = client.get("/auth/feishu/login", follow_redirects=False)

    assert response.status_code in (302, 307), response.text
    assert "open-apis/authen/v1/authorize" in response.headers["location"]


def test_feishu_login_respects_explicit_disable_even_when_config_exists(monkeypatch):
    monkeypatch.setenv("FEISHU_OAUTH_ENABLED", "false")
    monkeypatch.setenv("FEISHU_OAUTH_APP_ID", "cli_test_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "oauth-secret")
    monkeypatch.setenv("FEISHU_OAUTH_REDIRECT_URI", "http://testserver/auth/feishu/callback")
    monkeypatch.setenv("FEISHU_SESSION_SECRET", "test-secret")

    client = TestClient(api_server.app)
    response = client.get("/auth/feishu/login", follow_redirects=False)

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Feishu OAuth is not enabled"


def test_auth_me_reports_feishu_oauth_capability(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    guest = TestClient(api_server.app)
    guest_me = guest.get("/auth/me")

    assert guest_me.status_code == 200, guest_me.text
    assert guest_me.json()["feishu_oauth_enabled"] is True

    monkeypatch.setenv("FEISHU_OAUTH_ENABLED", "false")
    disabled = TestClient(api_server.app)
    disabled_me = disabled.get("/auth/me")

    assert disabled_me.status_code == 200, disabled_me.text
    assert disabled_me.json()["feishu_oauth_enabled"] is False


def test_sessions_are_isolated_per_authenticated_workspace(tmp_path, monkeypatch):
    workspaces_dir = _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    profiles = {
        "alice-token": {
            "open_id": "ou_alice",
            "union_id": "on_alice",
            "name": "Alice Zhang",
            "email": "alice@example.com",
        },
        "bob-token": {
            "open_id": "ou_bob",
            "union_id": "on_bob",
            "name": "Bob Lee",
            "email": "bob@example.com",
        },
    }

    monkeypatch.setattr(
        api_server,
        "_feishu_exchange_oauth_code",
        lambda code, redirect_uri=None: {"access_token": f"{code}-token"},
    )
    monkeypatch.setattr(api_server, "_feishu_fetch_user_profile", lambda access_token: profiles[access_token])

    alice = TestClient(api_server.app)
    bob = TestClient(api_server.app)

    assert alice.get("/auth/feishu/callback?code=alice", follow_redirects=False).status_code in (302, 307)
    assert bob.get("/auth/feishu/callback?code=bob", follow_redirects=False).status_code in (302, 307)

    alice_create = alice.post("/sessions", json={"title": "Alice Session"})
    bob_create = bob.post("/sessions", json={"title": "Bob Session"})

    assert alice_create.status_code == 201, alice_create.text
    assert bob_create.status_code == 201, bob_create.text

    alice_sessions = alice.get("/sessions").json()
    bob_sessions = bob.get("/sessions").json()
    alice_user_id = alice.get("/auth/me").json()["user"]["user_id"]
    bob_user_id = bob.get("/auth/me").json()["user"]["user_id"]

    assert [s["title"] for s in alice_sessions] == ["Alice Session"]
    assert [s["title"] for s in bob_sessions] == ["Bob Session"]

    assert (workspaces_dir / alice_user_id / "sessions").exists()
    assert (workspaces_dir / bob_user_id / "sessions").exists()


def test_workspace_session_ids_cannot_be_used_across_workspaces(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    profiles = {
        "alice-token": {
            "open_id": "ou_alice",
            "union_id": "on_alice",
            "name": "Alice Zhang",
            "email": "alice@example.com",
        },
        "bob-token": {
            "open_id": "ou_bob",
            "union_id": "on_bob",
            "name": "Bob Lee",
            "email": "bob@example.com",
        },
    }

    monkeypatch.setattr(
        api_server,
        "_feishu_exchange_oauth_code",
        lambda code, redirect_uri=None: {"access_token": f"{code}-token"},
    )
    monkeypatch.setattr(api_server, "_feishu_fetch_user_profile", lambda access_token: profiles[access_token])

    alice = TestClient(api_server.app)
    bob = TestClient(api_server.app)

    alice.get("/auth/feishu/callback?code=alice", follow_redirects=False)
    bob.get("/auth/feishu/callback?code=bob", follow_redirects=False)

    session_id = alice.post("/sessions", json={"title": "Alice Session"}).json()["session_id"]

    upload = bob.post(
        "/upload",
        data={"session_id": session_id},
        files={"file": ("note.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")},
    )

    assert upload.status_code == 404, upload.text
    assert "not found" in upload.json()["detail"].lower()


def test_runs_are_isolated_per_authenticated_workspace(tmp_path, monkeypatch):
    workspaces_dir = _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    profiles = {
        "alice-token": {
            "open_id": "ou_alice",
            "union_id": "on_alice",
            "name": "Alice Zhang",
            "email": "alice@example.com",
        },
        "bob-token": {
            "open_id": "ou_bob",
            "union_id": "on_bob",
            "name": "Bob Lee",
            "email": "bob@example.com",
        },
    }

    monkeypatch.setattr(
        api_server,
        "_feishu_exchange_oauth_code",
        lambda code, redirect_uri=None: {"access_token": f"{code}-token"},
    )
    monkeypatch.setattr(api_server, "_feishu_fetch_user_profile", lambda access_token: profiles[access_token])

    alice = TestClient(api_server.app)
    bob = TestClient(api_server.app)
    alice.get("/auth/feishu/callback?code=alice", follow_redirects=False)
    bob.get("/auth/feishu/callback?code=bob", follow_redirects=False)

    alice_user_id = alice.get("/auth/me").json()["user"]["user_id"]
    bob_user_id = bob.get("/auth/me").json()["user"]["user_id"]

    alice_run = workspaces_dir / alice_user_id / "runs" / "20260415_120000_aa1111"
    bob_run = workspaces_dir / bob_user_id / "runs" / "20260415_120000_bb2222"
    for run_dir, prompt in ((alice_run, "Alice strategy"), (bob_run, "Bob strategy")):
        (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        (run_dir.parent.parent / "uploads").mkdir(parents=True, exist_ok=True)
        (run_dir / "state.json").write_text('{"status":"success"}', encoding="utf-8")
        (run_dir / "req.json").write_text(f'{{"prompt":"{prompt}"}}', encoding="utf-8")

    alice_runs = alice.get("/runs")
    bob_runs = bob.get("/runs")

    assert alice_runs.status_code == 200, alice_runs.text
    assert bob_runs.status_code == 200, bob_runs.text
    assert [r["run_id"] for r in alice_runs.json()] == ["20260415_120000_aa1111"]
    assert [r["run_id"] for r in bob_runs.json()] == ["20260415_120000_bb2222"]

    alice_get_bob = alice.get("/runs/20260415_120000_bb2222")
    assert alice_get_bob.status_code == 404, alice_get_bob.text


def test_swarm_runtime_is_resolved_per_authenticated_workspace(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    profiles = {
        "alice-token": {
            "open_id": "ou_alice",
            "union_id": "on_alice",
            "name": "Alice Zhang",
            "email": "alice@example.com",
        },
        "bob-token": {
            "open_id": "ou_bob",
            "union_id": "on_bob",
            "name": "Bob Lee",
            "email": "bob@example.com",
        },
    }

    monkeypatch.setattr(
        api_server,
        "_feishu_exchange_oauth_code",
        lambda code, redirect_uri=None: {"access_token": f"{code}-token"},
    )
    monkeypatch.setattr(api_server, "_feishu_fetch_user_profile", lambda access_token: profiles[access_token])

    runtimes = {}

    class FakeRun:
        def __init__(self, run_id, preset_name):
            self.id = run_id
            self.preset_name = preset_name
            self.status = type("Status", (), {"value": "pending"})()
            self.created_at = "2026-04-15T00:00:00+00:00"
            self.tasks = []

    class FakeStore:
        def __init__(self, slug):
            self.slug = slug
            self.runs = []

        def list_runs(self, limit=50):
            return list(self.runs)[:limit]

        def load_run(self, run_id):
            for run in self.runs:
                if run.id == run_id:
                    return run
            return None

        def read_events(self, run_id, after_index=0):
            return []

        def run_dir(self, run_id):
            return tmp_path / self.slug / run_id

    class FakeRuntime:
        def __init__(self, slug):
            self.slug = slug
            self._store = FakeStore(slug)

        def start_run(self, preset_name, user_vars):
            run = FakeRun(f"{self.slug}-run", preset_name)
            self._store.runs.insert(0, run)
            return run

        def cancel_run(self, run_id):
            return any(run.id == run_id for run in self._store.runs)

    def fake_get_swarm_runtime(workspace=None):
        assert workspace is not None
        return runtimes.setdefault(workspace.workspace_slug, FakeRuntime(workspace.workspace_slug))

    monkeypatch.setattr(api_server, "_get_swarm_runtime", fake_get_swarm_runtime)

    alice = TestClient(api_server.app)
    bob = TestClient(api_server.app)
    alice.get("/auth/feishu/callback?code=alice", follow_redirects=False)
    bob.get("/auth/feishu/callback?code=bob", follow_redirects=False)

    alice_create = alice.post("/swarm/runs", json={"preset_name": "pairs_research_lab", "user_vars": {}})
    bob_create = bob.post("/swarm/runs", json={"preset_name": "pairs_research_lab", "user_vars": {}})

    assert alice_create.status_code == 200, alice_create.text
    assert bob_create.status_code == 200, bob_create.text
    assert alice_create.json()["id"] == "alice_zhang-run"
    assert bob_create.json()["id"] == "bob_lee-run"

    assert [r["id"] for r in alice.get("/swarm/runs").json()] == ["alice_zhang-run"]
    assert [r["id"] for r in bob.get("/swarm/runs").json()] == ["bob_lee-run"]


def test_feishu_webhook_routes_messages_into_logged_in_user_workspace(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    store = api_server._get_auth_store()
    alice = store.upsert_feishu_user(
        open_id="ou_alice",
        union_id="on_alice",
        name="Alice Zhang",
        email="alice@example.com",
        avatar_url=None,
    )
    bob = store.upsert_feishu_user(
        open_id="ou_bob",
        union_id="on_bob",
        name="Bob Lee",
        email="bob@example.com",
        avatar_url=None,
    )

    services = {}

    def fake_get_session_service(workspace=None):
        slug = workspace.workspace_slug if workspace is not None else "public"
        return services.setdefault(slug, _FakeFeishuService(slug))

    monkeypatch.setattr(api_server, "_get_session_service", fake_get_session_service)

    client = TestClient(api_server.app)

    def post_message(open_id, text):
        return client.post(
            "/feishu/webhook",
            json={
                "header": {"event_type": "im.message.receive_v1"},
                "event": {
                    "sender": {"sender_type": "user", "sender_id": {"open_id": open_id}},
                    "message": {
                        "chat_id": "oc_shared_chat",
                        "message_id": f"msg-{open_id}",
                        "message_type": "text",
                        "content": {"text": text},
                    },
                },
            },
        )

    alice_response = post_message("ou_alice", "hello from alice")
    bob_response = post_message("ou_bob", "hello from bob")

    assert alice_response.status_code == 200, alice_response.text
    assert bob_response.status_code == 200, bob_response.text
    assert services["alice_zhang"].sent == [{"session_id": "alice_zhang-session-1", "content": "hello from alice"}]
    assert services["bob_lee"].sent == [{"session_id": "bob_lee-session-1", "content": "hello from bob"}]

    session_map = api_server._load_feishu_session_map()
    assert session_map == {
        f"{alice.user_id}:oc_shared_chat": "alice_zhang-session-1",
        f"{bob.user_id}:oc_shared_chat": "bob_lee-session-1",
    }


def test_feishu_gateway_requires_linked_login_before_routing(tmp_path, monkeypatch):
    _patch_isolated_auth_runtime(tmp_path, monkeypatch)

    replies = []

    async def fake_send_reply(chat_id, text):
        replies.append({"chat_id": chat_id, "text": text})

    monkeypatch.setattr(api_server, "_feishu_send_reply", fake_send_reply)

    class FailService:
        def get_session(self, session_id):
            raise AssertionError("gateway should not inspect sessions for unlinked users")

        def create_session(self, title, config):
            raise AssertionError("gateway should not create sessions for unlinked users")

        async def send_message(self, session_id, content):
            raise AssertionError("gateway should not dispatch messages for unlinked users")

    asyncio.run(
        api_server._feishu_route_message(
            FailService(),
            "oc_unlinked_chat",
            "who am i",
            sender_open_id="ou_unknown",
        )
    )

    assert replies == [{
        "chat_id": "oc_unlinked_chat",
        "text": "Your Feishu account is not linked yet. Sign in first: http://testserver/auth/feishu/login",
    }]
    assert api_server._load_feishu_session_map() == {}
