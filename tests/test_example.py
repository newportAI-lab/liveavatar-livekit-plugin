from pathlib import Path
from typing import ClassVar

import pytest

from examples import basic_agent


def test_example_compiles():
    source = Path("examples/basic_agent.py").read_text()
    compile(source, "examples/basic_agent.py", "exec")
    assert "from livekit.plugins import facemarket" in source
    assert "session_id=previous_session_id" in source
    assert "facemarket.SCENE_READY" in source
    assert "facemarket.SESSION_READY" not in source


class FakeContext:
    def __init__(self):
        self.room = object()
        self.shutdown_callbacks = []

    async def connect(self):
        pass

    def add_shutdown_callback(self, callback):
        self.shutdown_callbacks.append(callback)


class FakeAvatar:
    instances: ClassVar[list["FakeAvatar"]] = []

    def __init__(self, **kwargs):
        self.session_id = "session-1"
        self.stopped = False
        self.instances.append(self)

    def on(self, _event):
        return lambda callback: callback

    async def start(self, session, *, room, session_id):
        pass

    async def stop(self):
        self.stopped = True


class FakeAgentSession:
    async def start(self, agent, *, room):
        pass


@pytest.mark.asyncio
async def test_example_stops_avatar_from_job_shutdown_callback(monkeypatch):
    monkeypatch.setenv("FACEMARKET_AVATAR_ID", "avatar-1")
    monkeypatch.delenv("FACEMARKET_PRESERVE_SESSION", raising=False)
    monkeypatch.setattr(basic_agent.facemarket, "AvatarSession", FakeAvatar)
    monkeypatch.setattr(basic_agent, "AgentSession", FakeAgentSession)
    monkeypatch.setattr(basic_agent.agents, "Agent", lambda **kwargs: object())
    ctx = FakeContext()

    await basic_agent.entrypoint(ctx)

    avatar = FakeAvatar.instances[-1]
    assert avatar.stopped is False
    assert len(ctx.shutdown_callbacks) == 1
    await ctx.shutdown_callbacks[0]()
    assert avatar.stopped is True


@pytest.mark.asyncio
async def test_example_can_preserve_remote_session_for_later_reconnect(monkeypatch):
    monkeypatch.setenv("FACEMARKET_AVATAR_ID", "avatar-1")
    monkeypatch.setenv("FACEMARKET_PRESERVE_SESSION", "true")
    monkeypatch.setattr(basic_agent.facemarket, "AvatarSession", FakeAvatar)
    monkeypatch.setattr(basic_agent, "AgentSession", FakeAgentSession)
    monkeypatch.setattr(basic_agent.agents, "Agent", lambda **kwargs: object())
    ctx = FakeContext()

    await basic_agent.entrypoint(ctx)

    assert ctx.shutdown_callbacks == []
    assert FakeAvatar.instances[-1].stopped is False
