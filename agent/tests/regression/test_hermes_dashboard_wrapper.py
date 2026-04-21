from pathlib import Path

from fastapi.testclient import TestClient

import hermes_dashboard_wrapper
from hermes_cli.web_server import _SESSION_TOKEN
from hermes_state import SessionDB


def _create_titled_session(home: Path, session_id: str, title: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    db = SessionDB(db_path=home / "state.db")
    try:
        db.create_session(session_id=session_id, source="web")
        assert db.set_session_title(session_id, title)
    finally:
        db.close()


def test_wrapper_scopes_dashboard_sessions_per_request(tmp_path):
    home_a = tmp_path / "tenant-a" / ".hermes"
    home_b = tmp_path / "tenant-b" / ".hermes"
    _create_titled_session(home_a, "sess-a", "Tenant A session")
    _create_titled_session(home_b, "sess-b", "Tenant B session")

    client = TestClient(hermes_dashboard_wrapper.app)
    auth_header = {"Authorization": f"Bearer {_SESSION_TOKEN}"}

    response_a = client.get(
        "/api/sessions",
        headers={**auth_header, "X-Hermes-Home": str(home_a)},
    )
    assert response_a.status_code == 200, response_a.text
    assert [row["id"] for row in response_a.json()["sessions"]] == ["sess-a"]

    response_b = client.get(
        "/api/sessions",
        headers={**auth_header, "X-Hermes-Home": str(home_b)},
    )
    assert response_b.status_code == 200, response_b.text
    assert [row["id"] for row in response_b.json()["sessions"]] == ["sess-b"]


def test_wrapper_rejects_relative_hermes_home_header():
    client = TestClient(hermes_dashboard_wrapper.app)
    response = client.get(
        "/api/sessions",
        headers={
            "Authorization": f"Bearer {_SESSION_TOKEN}",
            "X-Hermes-Home": "relative/path",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "X-Hermes-Home must be an absolute path"
