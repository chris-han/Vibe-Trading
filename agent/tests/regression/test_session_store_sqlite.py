from __future__ import annotations

from pathlib import Path

from src.session.models import Attempt, Message, Session
from src.session.store_sqlite import SQLiteSessionStore


def test_sqlite_session_store_roundtrip_and_message_projection(tmp_path):
    base_dir = tmp_path / "sessions"
    db_path = tmp_path / ".hermes" / "state.db"
    store = SQLiteSessionStore(base_dir=base_dir, db_path=db_path)

    session = Session(session_id="session_a", title="Alpha", config={"channel": "web"})
    store.create_session(session)

    loaded = store.get_session("session_a")
    assert loaded is not None
    assert loaded.title == "Alpha"

    store.append_message(
        Message(
            session_id="session_a",
            role="user",
            content="hello",
            linked_attempt_id="attempt_a",
        )
    )
    messages = store.get_messages("session_a")
    assert len(messages) == 1
    assert messages[0].content == "hello"
    assert messages[0].linked_attempt_id == "attempt_a"


def test_sqlite_session_store_attempts_and_artifact_indexing(tmp_path):
    base_dir = tmp_path / "sessions"
    db_path = tmp_path / ".hermes" / "state.db"
    store = SQLiteSessionStore(base_dir=base_dir, db_path=db_path)

    session = Session(session_id="session_b", title="Beta", config={"channel": "web"})
    store.create_session(session)

    run_dir = tmp_path / "runs" / "run_001"
    swarm_run_dir = tmp_path / ".swarm" / "runs" / "swarm_001"
    run_dir.mkdir(parents=True, exist_ok=True)
    swarm_run_dir.mkdir(parents=True, exist_ok=True)

    attempt = Attempt(session_id="session_b", attempt_id="attempt_b", prompt="go", run_dir=str(run_dir))
    store.create_attempt(attempt)
    store.register_artifact("session_b", str(swarm_run_dir), kind="swarm_run_dir")

    attempts = store.list_attempts("session_b")
    assert len(attempts) == 1
    assert attempts[0].run_dir == str(run_dir)

    artifacts = store.list_artifacts("session_b")
    paths = {entry["path"] for entry in artifacts}
    assert str(run_dir) in paths
    assert str(swarm_run_dir) in paths


def test_sqlite_session_store_delete_removes_session_dir_and_records(tmp_path):
    base_dir = tmp_path / "sessions"
    db_path = tmp_path / ".hermes" / "state.db"
    store = SQLiteSessionStore(base_dir=base_dir, db_path=db_path)

    session = Session(session_id="session_c", title="Gamma", config={"channel": "web"})
    store.create_session(session)
    session_upload_dir = base_dir / "session_c" / "uploads"
    session_upload_dir.mkdir(parents=True, exist_ok=True)
    (session_upload_dir / "note.txt").write_text("ok", encoding="utf-8")

    assert store.delete_session("session_c") is True
    assert store.get_session("session_c") is None
    assert not (base_dir / "session_c").exists()
