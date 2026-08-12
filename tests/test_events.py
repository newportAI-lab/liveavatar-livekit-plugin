import logging

import pytest

from livekit.plugins.facemarket.events import EventDispatcher


@pytest.mark.asyncio
async def test_dispatch_isolates_failing_callbacks(caplog):
    dispatcher = EventDispatcher()
    received = []

    def fail(value):
        raise RuntimeError("boom")

    def succeed(value):
        received.append(value)

    dispatcher.add("ready", fail)
    dispatcher.add("ready", succeed)

    with caplog.at_level(logging.ERROR):
        await dispatcher.dispatch("ready", "event")

    assert received == ["event"]
    assert "callback failed" in caplog.text


@pytest.mark.asyncio
async def test_on_decorator_and_remove():
    dispatcher = EventDispatcher()
    received = []

    @dispatcher.on("ready")
    async def callback(value):
        received.append(value)

    await dispatcher.dispatch("ready", "first")
    dispatcher.remove("ready", callback)
    await dispatcher.dispatch("ready", "second")

    assert received == ["first"]
