from __future__ import annotations

import json

from src.session.events import EventBus
from src.session.models import Attempt, SessionEvent, SessionEventType
from src.session.service import SessionService
from src.session.store import SessionStore


def test_delete_session_removes_session_uploads_runs_and_swarm_runs(tmp_path):
    sessions_dir = tmp_path / "sessions"
    runs_dir = tmp_path / "runs"
    swarm_dir = tmp_path / ".swarm"

    store = SessionStore(base_dir=sessions_dir)
    service = SessionService(store=store, event_bus=EventBus(), runs_dir=runs_dir, swarm_dir=swarm_dir)

    session = service.create_session("Fed Minutes", {"channel": "web"})

    upload_file = sessions_dir / session.session_id / "uploads" / "minutes.pdf"
    upload_file.parent.mkdir(parents=True, exist_ok=True)
    upload_file.write_bytes(b"%PDF-1.4\n")

    run_dir = runs_dir / "backtest-run-123"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.md").write_text("report\n", encoding="utf-8")
    store.create_attempt(Attempt(session_id=session.session_id, prompt="run", run_dir=str(run_dir)))

    orphan_run_dir = runs_dir / "orphan-session-run"
    orphan_run_dir.mkdir(parents=True, exist_ok=True)
    (orphan_run_dir / "req.json").write_text(
        json.dumps({"prompt": "run", "context": {"session_id": session.session_id}}),
        encoding="utf-8",
    )

    external_artifacts_dir = tmp_path / "external-artifacts"
    external_artifacts_dir.mkdir(parents=True, exist_ok=True)
    external_file = external_artifacts_dir / f"session_{session.session_id}.json"
    external_file.write_text('{"platform":"weixin"}\n', encoding="utf-8")
    external_jsonl = external_artifacts_dir / f"{session.session_id}.jsonl"
    external_jsonl.write_text('{"role":"user","content":"hi"}\n', encoding="utf-8")
    store.register_artifact(session.session_id, str(external_file), kind="gateway_session_meta")
    store.register_artifact(session.session_id, str(external_jsonl), kind="gateway_transcript")

    swarm_run_dir = swarm_dir / "runs" / "swarm-abc123"
    swarm_run_dir.mkdir(parents=True, exist_ok=True)
    (swarm_run_dir / "run.json").write_text('{"status":"completed"}\n', encoding="utf-8")
    store.append_event(
        SessionEvent(
            session_id=session.session_id,
            event_type=SessionEventType.TOOL_RESULT.value,
            tool="run_swarm",
            status="ok",
            metadata={"swarm_run_id": "swarm-abc123"},
        )
    )

    assert service.delete_session(session.session_id) is True

    assert not (sessions_dir / session.session_id).exists()
    assert not upload_file.exists()
    assert not run_dir.exists()
    assert not orphan_run_dir.exists()
    assert not external_file.exists()
    assert not external_jsonl.exists()
    assert not swarm_run_dir.exists()


def test_batch_delete_sessions_removes_artifacts_for_deleted_sessions_only(tmp_path):
    sessions_dir = tmp_path / "sessions"
    runs_dir = tmp_path / "runs"
    swarm_dir = tmp_path / ".swarm"

    store = SessionStore(base_dir=sessions_dir)
    service = SessionService(store=store, event_bus=EventBus(), runs_dir=runs_dir, swarm_dir=swarm_dir)

    deleted_session = service.create_session("Delete Me", {"channel": "web"})
    kept_session = service.create_session("Keep Me", {"channel": "web"})

    deleted_upload = sessions_dir / deleted_session.session_id / "uploads" / "delete.pdf"
    deleted_upload.parent.mkdir(parents=True, exist_ok=True)
    deleted_upload.write_bytes(b"%PDF-1.4\n")

    kept_upload = sessions_dir / kept_session.session_id / "uploads" / "keep.pdf"
    kept_upload.parent.mkdir(parents=True, exist_ok=True)
    kept_upload.write_bytes(b"%PDF-1.4\n")

    deleted_run_dir = runs_dir / "delete-run"
    deleted_run_dir.mkdir(parents=True, exist_ok=True)
    store.create_attempt(Attempt(session_id=deleted_session.session_id, prompt="run", run_dir=str(deleted_run_dir)))

    deleted_orphan_run_dir = runs_dir / "delete-orphan-run"
    deleted_orphan_run_dir.mkdir(parents=True, exist_ok=True)
    (deleted_orphan_run_dir / "req.json").write_text(
        json.dumps({"prompt": "run", "context": {"session_id": deleted_session.session_id}}),
        encoding="utf-8",
    )

    kept_orphan_run_dir = runs_dir / "keep-orphan-run"
    kept_orphan_run_dir.mkdir(parents=True, exist_ok=True)
    (kept_orphan_run_dir / "req.json").write_text(
        json.dumps({"prompt": "run", "context": {"session_id": kept_session.session_id}}),
        encoding="utf-8",
    )

    external_artifacts_dir = tmp_path / "external-artifacts"
    external_artifacts_dir.mkdir(parents=True, exist_ok=True)
    deleted_external_file = external_artifacts_dir / f"session_{deleted_session.session_id}.json"
    deleted_external_file.write_text('{"platform":"weixin"}\n', encoding="utf-8")
    kept_external_file = external_artifacts_dir / f"session_{kept_session.session_id}.json"
    kept_external_file.write_text('{"platform":"weixin"}\n', encoding="utf-8")
    store.register_artifact(deleted_session.session_id, str(deleted_external_file), kind="gateway_session_meta")
    store.register_artifact(kept_session.session_id, str(kept_external_file), kind="gateway_session_meta")

    deleted_swarm_dir = swarm_dir / "runs" / "swarm-delete"
    deleted_swarm_dir.mkdir(parents=True, exist_ok=True)
    store.append_event(
        SessionEvent(
            session_id=deleted_session.session_id,
            event_type=SessionEventType.TOOL_RESULT.value,
            tool="run_swarm",
            status="ok",
            metadata={"swarm_run_id": "swarm-delete"},
        )
    )

    result = service.delete_sessions([deleted_session.session_id, "missing-session"])

    assert result == {"deleted": [deleted_session.session_id], "missing": ["missing-session"]}
    assert not (sessions_dir / deleted_session.session_id).exists()
    assert deleted_upload.exists() is False
    assert not deleted_run_dir.exists()
    assert not deleted_orphan_run_dir.exists()
    assert not deleted_external_file.exists()
    assert not deleted_swarm_dir.exists()
    assert (sessions_dir / kept_session.session_id).exists()
    assert kept_upload.exists()
    assert kept_orphan_run_dir.exists()
    assert kept_external_file.exists()