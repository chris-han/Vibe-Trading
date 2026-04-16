import asyncio
import json

import api_server
from src.adapters.factory import get_feishu_visualization_adapter


_FEISHU_ADAPTER = get_feishu_visualization_adapter()


def test_build_streaming_card_v2_uses_card_json_v2_schema():
    payload = json.loads(_FEISHU_ADAPTER.build_streaming_card_payload("Vibe-Trading", "hello"))

    assert payload["schema"] == "2.0"
    assert payload["config"]["streaming_mode"] is True
    assert payload["config"]["update_multi"] is True
    assert payload["body"]["elements"][0]["tag"] == "markdown"
    assert payload["body"]["elements"][0]["element_id"] == _FEISHU_ADAPTER.stream_element_id


def test_feishu_await_and_reply_streams_card_and_disables_mode(monkeypatch):
    streamed_updates = []
    streaming_mode_updates = []
    fallback_replies = []

    class FakeEvent:
        def __init__(self, event_type, data):
            self.event_type = event_type
            self.data = data

    class FakeEventBus:
        async def subscribe(self, session_id, last_event_id=None):
            yield FakeEvent("text_delta", {"attempt_id": "attempt-1", "content": "Hello"})
            yield FakeEvent("text_delta", {"attempt_id": "attempt-1", "content": " world"})
            yield FakeEvent("attempt.completed", {"attempt_id": "attempt-1", "summary": "Hello world"})

    class FakeMessage:
        role = "assistant"
        linked_attempt_id = "attempt-1"
        content = "Hello world"

    class FakeService:
        event_bus = FakeEventBus()

        def get_messages(self, session_id, limit=20):
            return [FakeMessage()]

        def get_events(self, session_id, limit=2000):
            return []

    async def fake_create_streaming_card_message(chat_id, title, initial_body):
        return {
            "card_id": "card_123",
            "message_id": "om_123",
            "element_id": _FEISHU_ADAPTER.stream_element_id,
            "sequence": 1,
        }

    async def fake_stream_card_text(card_ctx, content):
        streamed_updates.append(content)
        card_ctx["sequence"] = int(card_ctx.get("sequence") or 1) + 1

    async def fake_set_card_streaming_mode(card_ctx, *, enabled, summary=None):
        streaming_mode_updates.append({"enabled": enabled, "summary": summary})
        card_ctx["sequence"] = int(card_ctx.get("sequence") or 1) + 1

    async def fake_send_reply(chat_id, text):
        fallback_replies.append(text)

    monkeypatch.setattr(api_server, "_feishu_create_streaming_card_message", fake_create_streaming_card_message)
    monkeypatch.setattr(api_server, "_feishu_stream_card_text", fake_stream_card_text)
    monkeypatch.setattr(api_server, "_feishu_set_card_streaming_mode", fake_set_card_streaming_mode)
    monkeypatch.setattr(api_server, "_feishu_send_reply", fake_send_reply)
    monkeypatch.setattr(api_server, "_FEISHU_STREAM_UPDATE_INTERVAL_SECONDS", 0.0)

    asyncio.run(api_server._feishu_await_and_reply(FakeService(), "session-1", "chat-1", "attempt-1"))

    assert streamed_updates
    assert streamed_updates[-1] == "Hello world"
    assert streaming_mode_updates == [{"enabled": False, "summary": "Complete"}]
    assert fallback_replies == []