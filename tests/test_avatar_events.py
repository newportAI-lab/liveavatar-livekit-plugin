import asyncio
from types import SimpleNamespace

import pytest
from fakes import FakeAgentSession, FakeApiClient, FakeRoom
from test_avatar_lifecycle import make_avatar

from livekit.plugins.facemarket.protocol import decode_event


@pytest.mark.asyncio
async def test_inbound_events_metadata_ready_once_and_idle_prompt():
    room, agent = FakeRoom(), FakeAgentSession()
    avatar = make_avatar(FakeApiClient())
    received = []
    avatar.on("session_ready")(received.append)
    avatar.on("custom_event")(received.append)
    await avatar.start(agent, room=room)
    packet = SimpleNamespace(
        data=b'{"event":"scene.ready","data":{}}',
        participant=SimpleNamespace(identity="renderer"),
        topic="t",
    )
    room.emit("data_received", packet)
    room.emit("data_received", packet)
    room.emit(
        "data_received",
        SimpleNamespace(
            data=b'{"event":"unknown"}', participant=SimpleNamespace(identity="renderer"), topic="t"
        ),
    )
    room.emit(
        "data_received",
        SimpleNamespace(
            data=b'{"event":"system.idleTrigger","data":{}}',
            participant=SimpleNamespace(identity="renderer"),
            topic="t",
        ),
    )
    agent.emit("agent_state_changed", SimpleNamespace(old_state="idle", new_state="speaking"))
    await asyncio.sleep(0)
    assert [event.event for event in received] == ["scene.ready", "unknown"]
    assert received[0].participant_identity == "renderer"
    assert (
        decode_event(room.local_participant.published[-1][0]).event == "response.audio.promptStart"
    )


@pytest.mark.asyncio
async def test_interrupt_is_reliable_and_publish_failure_is_local_error():
    room = FakeRoom()
    avatar = make_avatar(FakeApiClient())
    errors = []
    avatar.on("error")(errors.append)
    await avatar.start(FakeAgentSession(), room=room)
    await avatar.interrupt()
    await asyncio.sleep(0)
    assert decode_event(room.local_participant.published[-1][0]).event == "response.audio.interrupt"
    assert room.local_participant.published[-1][1] is True
    room.local_participant.fail_publish = True
    await avatar.interrupt()
    await asyncio.sleep(0)
    assert len(errors) == 1
