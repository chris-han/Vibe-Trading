from pathlib import Path

from fastapi.testclient import TestClient

import api_server


def _pdf_payload() -> bytes:
    # Minimal PDF-like payload; endpoint only validates extension/size.
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def _patch_auth(monkeypatch):
    monkeypatch.setattr(api_server, "_API_KEY", None)
    monkeypatch.setattr(api_server, "_feishu_oauth_enabled", lambda: False)


def test_upload_accepts_session_id_from_query_param(tmp_path, monkeypatch):
    _patch_auth(monkeypatch)
    sessions_dir = tmp_path / "sessions"
    runs_dir = tmp_path / "runs"
    uploads_dir = tmp_path / "uploads"

    session_id = "sess_query_1"
    (sessions_dir / session_id).mkdir(parents=True)

    monkeypatch.setattr(api_server, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(api_server, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(api_server, "UPLOADS_DIR", uploads_dir)

    client = TestClient(api_server.app)
    response = client.post(
        f"/upload?session_id={session_id}",
        files={"file": ("earnings.pdf", _pdf_payload(), "application/pdf")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["filename"] == "earnings.pdf"

    saved = Path(body["file_path"])
    assert saved.exists()
    assert saved.parent == sessions_dir / session_id / "uploads"


def test_upload_accepts_session_id_from_header(tmp_path, monkeypatch):
    _patch_auth(monkeypatch)
    sessions_dir = tmp_path / "sessions"
    runs_dir = tmp_path / "runs"
    uploads_dir = tmp_path / "uploads"

    session_id = "sess_header_1"
    (sessions_dir / session_id).mkdir(parents=True)

    monkeypatch.setattr(api_server, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(api_server, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(api_server, "UPLOADS_DIR", uploads_dir)

    client = TestClient(api_server.app)
    response = client.post(
        "/upload",
        headers={"x-session-id": session_id},
        files={"file": ("earnings.pdf", _pdf_payload(), "application/pdf")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    saved = Path(body["file_path"])
    assert saved.exists()
    assert saved.parent == sessions_dir / session_id / "uploads"


def test_upload_missing_scope_returns_actionable_error(monkeypatch):
    _patch_auth(monkeypatch)
    client = TestClient(api_server.app)
    response = client.post(
        "/upload",
        files={"file": ("earnings.pdf", _pdf_payload(), "application/pdf")},
    )

    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert "session_id or run_id is required" in detail
    assert "query param" in detail
