import asyncio

import pytest

from src.session.events import EventBus


@pytest.mark.asyncio
async def test_subscribe_replay_existing_replays_buffered_events():
    bus = EventBus()
    bus.set_loop(asyncio.get_running_loop())
    bus.emit("session-1", "text_delta", {"content": "hello"})

    stream = bus.subscribe("session-1", replay_existing=True)
    event = await anext(stream)
    await stream.aclose()

    assert event.event_type == "text_delta"
    assert event.data == {"content": "hello"}


@pytest.mark.asyncio
async def test_subscribe_without_replay_existing_skips_buffered_events():
    bus = EventBus()
    bus.set_loop(asyncio.get_running_loop())
    bus.emit("session-1", "text_delta", {"content": "hello"})

    stream = bus.subscribe("session-1")
    task = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await stream.aclose()
