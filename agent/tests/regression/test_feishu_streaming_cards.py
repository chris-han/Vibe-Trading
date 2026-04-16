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


def test_feishu_chart_patch_timeout_preserves_streamed_card_without_fallback_reply(monkeypatch):
    streamed_updates = []
    streaming_mode_updates = []
    fallback_replies = []

    class FakeEvent:
        def __init__(self, event_type, data):
            self.event_type = event_type
            self.data = data

    class FakeEventBus:
        async def subscribe(self, session_id, last_event_id=None):
            yield FakeEvent(
                "attempt.completed",
                {
                    "attempt_id": "attempt-1",
                    "summary": (
                        "Summary\n\n```vchart\n"
                        '{"type":"bar","data":[{"id":"bar","values":[{"x":"A","y":1}]}],"xField":"x","yField":"y"}'
                        "\n```"
                    ),
                },
            )

    class FakeMessage:
        role = "assistant"
        linked_attempt_id = "attempt-1"
        content = (
            "Summary\n\n```vchart\n"
            '{"type":"bar","data":[{"id":"bar","values":[{"x":"A","y":1}]}],"xField":"x","yField":"y"}'
            "\n```"
        )

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

    async def fake_patch_card_body(card_ctx, title, elements, *, template="blue"):
        raise RuntimeError("Feishu HTTP 504: Gateway timeout")

    async def fake_send_reply(chat_id, text):
        fallback_replies.append(text)

    monkeypatch.setattr(api_server, "_feishu_create_streaming_card_message", fake_create_streaming_card_message)
    monkeypatch.setattr(api_server, "_feishu_stream_card_text", fake_stream_card_text)
    monkeypatch.setattr(api_server, "_feishu_set_card_streaming_mode", fake_set_card_streaming_mode)
    monkeypatch.setattr(api_server, "_feishu_patch_card_body", fake_patch_card_body)
    monkeypatch.setattr(api_server, "_feishu_send_reply", fake_send_reply)
    monkeypatch.setattr(api_server, "_FEISHU_STREAM_UPDATE_INTERVAL_SECONDS", 0.0)

    asyncio.run(api_server._feishu_await_and_reply(FakeService(), "session-1", "chat-1", "attempt-1"))

    assert streamed_updates
    assert "Summary" in streamed_updates[-1]
    assert "```vchart" not in streamed_updates[-1]
    assert streaming_mode_updates == [{"enabled": False, "summary": "Complete"}]
    assert fallback_replies == []


def test_feishu_await_and_reply_sends_additional_cards_when_chart_count_exceeds_limit(monkeypatch):
    streamed_updates = []
    streaming_mode_updates = []
    patched_batches = []
    sent_batches = []
    fallback_replies = []

    chart_blocks = []
    for index in range(6):
        chart_blocks.append(
            "```vchart\n"
            + json.dumps(
                {
                    "type": "line",
                    "title": {"text": f"Chart {index + 1}"},
                    "data": {"values": [{"x": "A", "y": index + 1}]},
                    "xField": "x",
                    "yField": "y",
                }
            )
            + "\n```"
        )
    final_content = "\n\n".join(chart_blocks)

    class FakeEvent:
        def __init__(self, event_type, data):
            self.event_type = event_type
            self.data = data

    class FakeEventBus:
        async def subscribe(self, session_id, last_event_id=None):
            yield FakeEvent("attempt.completed", {"attempt_id": "attempt-1", "summary": final_content})

    class FakeMessage:
        role = "assistant"
        linked_attempt_id = "attempt-1"
        content = final_content

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

    async def fake_patch_card_body(card_ctx, title, elements, *, template="blue"):
        patched_batches.append(elements)

    async def fake_send_card_message(chat_id, title, elements, *, template="blue"):
        sent_batches.append(elements)
        return {"card_id": "card_extra", "message_id": "om_extra"}

    async def fake_send_reply(chat_id, text):
        fallback_replies.append(text)

    monkeypatch.setattr(api_server, "_feishu_create_streaming_card_message", fake_create_streaming_card_message)
    monkeypatch.setattr(api_server, "_feishu_stream_card_text", fake_stream_card_text)
    monkeypatch.setattr(api_server, "_feishu_set_card_streaming_mode", fake_set_card_streaming_mode)
    monkeypatch.setattr(api_server, "_feishu_patch_card_body", fake_patch_card_body)
    monkeypatch.setattr(api_server, "_feishu_send_card_message", fake_send_card_message)
    monkeypatch.setattr(api_server, "_feishu_send_reply", fake_send_reply)
    monkeypatch.setattr(api_server, "_FEISHU_STREAM_UPDATE_INTERVAL_SECONDS", 0.0)

    asyncio.run(api_server._feishu_await_and_reply(FakeService(), "session-1", "chat-1", "attempt-1"))

    assert streaming_mode_updates == [{"enabled": False, "summary": "Complete"}]
    assert fallback_replies == []
    assert len(patched_batches) == 1
    assert sum(1 for item in patched_batches[0] if item.get("tag") == "chart") == 1
    assert len(sent_batches) == 5
    assert all(sum(1 for item in batch if item.get("tag") == "chart") == 1 for batch in sent_batches)


def test_feishu_await_and_reply_isolates_independent_chart_sections_into_separate_cards(monkeypatch):
    streamed_updates = []
    streaming_mode_updates = []
    patched_batches = []
    sent_batches = []
    fallback_replies = []

    chart_blocks = []
    for index in range(3):
        chart_blocks.append(
            f"## Chart {index + 1}\n\n说明 {index + 1}\n\n"
            + "```vchart\n"
            + json.dumps(
                {
                    "type": "line",
                    "title": {"text": f"Chart {index + 1}"},
                    "data": {"values": [{"x": "A", "y": index + 1}]},
                    "xField": "x",
                    "yField": "y",
                }
            )
            + "\n```"
        )
    final_content = "\n\n".join(chart_blocks)

    class FakeEvent:
        def __init__(self, event_type, data):
            self.event_type = event_type
            self.data = data

    class FakeEventBus:
        async def subscribe(self, session_id, last_event_id=None):
            yield FakeEvent("attempt.completed", {"attempt_id": "attempt-1", "summary": final_content})

    class FakeMessage:
        role = "assistant"
        linked_attempt_id = "attempt-1"
        content = final_content

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

    async def fake_patch_card_body(card_ctx, title, elements, *, template="blue"):
        patched_batches.append(elements)

    async def fake_send_card_message(chat_id, title, elements, *, template="blue"):
        sent_batches.append(elements)
        return {"card_id": f"card_{len(sent_batches)}", "message_id": f"om_{len(sent_batches)}"}

    async def fake_send_reply(chat_id, text):
        fallback_replies.append(text)

    monkeypatch.setattr(api_server, "_feishu_create_streaming_card_message", fake_create_streaming_card_message)
    monkeypatch.setattr(api_server, "_feishu_stream_card_text", fake_stream_card_text)
    monkeypatch.setattr(api_server, "_feishu_set_card_streaming_mode", fake_set_card_streaming_mode)
    monkeypatch.setattr(api_server, "_feishu_patch_card_body", fake_patch_card_body)
    monkeypatch.setattr(api_server, "_feishu_send_card_message", fake_send_card_message)
    monkeypatch.setattr(api_server, "_feishu_send_reply", fake_send_reply)
    monkeypatch.setattr(api_server, "_FEISHU_STREAM_UPDATE_INTERVAL_SECONDS", 0.0)

    asyncio.run(api_server._feishu_await_and_reply(FakeService(), "session-1", "chat-1", "attempt-1"))

    assert streamed_updates
    assert streaming_mode_updates == [{"enabled": False, "summary": "Complete"}]
    assert fallback_replies == []
    assert len(patched_batches) == 1
    assert len(sent_batches) == 2
    assert all(sum(1 for item in batch if item.get("tag") == "chart") == 1 for batch in [patched_batches[0], *sent_batches])
    assert any(item.get("tag") == "markdown" and "Chart 1" in item.get("content", "") for item in patched_batches[0])
    assert any(item.get("tag") == "markdown" and "Chart 2" in item.get("content", "") for item in sent_batches[0])
    assert any(item.get("tag") == "markdown" and "Chart 3" in item.get("content", "") for item in sent_batches[1])
