from pathlib import Path

from fastapi.testclient import TestClient

import hermes_dashboard_wrapper
from hermes_cli.web_server import _SESSION_TOKEN
from hermes_state import SessionDB
from tools.skills_guard import ScanResult
from tools.skills_hub import SkillBundle


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


def test_wrapper_scopes_skill_install_per_request(monkeypatch, tmp_path):
    import tools.skills_guard as skills_guard
    import tools.skills_hub as skills_hub

    home_a = tmp_path / "tenant-a" / ".hermes"
    home_b = tmp_path / "tenant-b" / ".hermes"

    class _FakeSource:
        def inspect(self, identifier):
            return None

        def fetch(self, identifier):
            if identifier != "community/demo-skill":
                return None
            return SkillBundle(
                name="demo-skill",
                source="github",
                identifier=identifier,
                trust_level="community",
                files={
                    "SKILL.md": (
                        "---\n"
                        "name: demo-skill\n"
                        "description: Demo skill\n"
                        "---\n\n"
                        "# Demo\n"
                    ),
                },
                metadata={},
            )

    monkeypatch.setattr(skills_hub, "GitHubAuth", lambda: None)
    monkeypatch.setattr(skills_hub, "create_source_router", lambda auth: [_FakeSource()])
    monkeypatch.setattr(
        skills_guard,
        "scan_skill",
        lambda path, source="community": ScanResult(
            skill_name="demo-skill",
            source=source,
            trust_level="community",
            verdict="safe",
            findings=[],
            scanned_at="2026-04-21T00:00:00Z",
            summary="clean",
        ),
    )
    monkeypatch.setattr(skills_guard, "should_allow_install", lambda result, force=False: (True, "ok"))

    client = TestClient(hermes_dashboard_wrapper.app)
    auth_header = {"Authorization": f"Bearer {_SESSION_TOKEN}"}

    response = client.post(
        "/api/skills/install",
        headers={**auth_header, "X-Hermes-Home": str(home_a)},
        json={"identifier": "community/demo-skill"},
    )

    assert response.status_code == 200, response.text
    assert (home_a / "skills" / "demo-skill" / "SKILL.md").exists()
    assert not (home_b / "skills" / "demo-skill" / "SKILL.md").exists()
