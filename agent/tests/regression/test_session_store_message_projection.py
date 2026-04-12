from __future__ import annotations

import sys
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parents[2]
root_str = str(AGENT_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)


def test_get_messages_not_truncated_by_delta_events(tmp_path):
    from src.session.models import Message, SessionEvent, SessionEventType
    from src.session.store import SessionStore

    store = SessionStore(base_dir=tmp_path)
    session_id = "cea924f25057"
    attempt_id = "attempt_1"

    store.append_message(
        Message(
            message_id="user_1",
            session_id=session_id,
            role="user",
            content="美股宏观分析",
            linked_attempt_id=attempt_id,
            created_at="2026-04-12T17:52:20.000000",
        )
    )

    for index in range(1105):
        store.append_event(
            SessionEvent(
                session_id=session_id,
                attempt_id=attempt_id,
                event_type=SessionEventType.TEXT_DELTA.value,
                role="assistant",
                content=f"delta-{index}",
                timestamp=f"2026-04-12T17:53:{index % 60:02d}.000000",
            )
        )

    store.append_message(
        Message(
            message_id="assistant_1",
            session_id=session_id,
            role="assistant",
            content="最终回答",
            linked_attempt_id=attempt_id,
            created_at="2026-04-12T17:54:59.000000",
            metadata={"status": "completed", "run_id": "run_1"},
        )
    )

    messages = store.get_messages(session_id, limit=100)

    assert len(messages) == 2
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "美股宏观分析"
    assert messages[1].content == "最终回答"
