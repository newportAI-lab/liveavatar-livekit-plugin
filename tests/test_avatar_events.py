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
async def test_interrupt_is_reliable_correlated_control_and_publish_failure_is_local_error():
    room = FakeRoom()
    avatar = make_avatar(FakeApiClient())
    errors = []
    avatar.on("error")(errors.append)
    await avatar.start(FakeAgentSession(), room=room)
    await avatar.interrupt("request-9")
    await asyncio.sleep(0)
    interrupt = decode_event(room.local_participant.published[-1][0])
    assert interrupt.event == "control.interrupt"
    assert interrupt.request_id == "request-9"
    assert room.local_participant.published[-1][1] is True
    room.local_participant.fail_publish = True
    await avatar.interrupt()
    await asyncio.sleep(0)
    assert len(errors) == 1


@pytest.mark.asyncio
async def test_async_prompt_start_failure_rolls_back_without_prompt_finish_or_recursive_publish():
    room, agent = FakeRoom(), FakeAgentSession()
    avatar = make_avatar(FakeApiClient())
    errors = []
    avatar.on("error")(errors.append)
    await avatar.start(agent, room=room)
    room.emit(
        "data_received",
        SimpleNamespace(data=b'{"event":"system.idleTrigger"}', participant=None, topic=None),
    )
    room.local_participant.fail_publish = True

    agent.emit("agent_state_changed", SimpleNamespace(old_state="idle", new_state="speaking"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    room.local_participant.fail_publish = False
    agent.emit("agent_state_changed", SimpleNamespace(old_state="speaking", new_state="idle"))
    await asyncio.sleep(0)

    published_events = [
        decode_event(payload).event for payload, _ in room.local_participant.published
    ]
    assert "response.audio.promptFinish" not in published_events
    assert published_events == ["response.audio.finish"]
    assert len(errors) == 1


@pytest.mark.asyncio
async def test_stop_cancellation_of_pending_prompt_start_does_not_publish_a_finish():
    room, agent = FakeRoom(), FakeAgentSession()
    prompt_started = asyncio.Event()

    async def blocking_publish(payload, reliable=True):
        if decode_event(payload).event == "response.audio.promptStart":
            prompt_started.set()
            await asyncio.Future()
        room.local_participant.published.append((payload, reliable))

    room.local_participant.publish_data = blocking_publish
    avatar = make_avatar(FakeApiClient())
    await avatar.start(agent, room=room)
    room.emit(
        "data_received",
        SimpleNamespace(data=b'{"event":"system.idleTrigger"}', participant=None, topic=None),
    )
    agent.emit("agent_state_changed", SimpleNamespace(old_state="idle", new_state="speaking"))
    await prompt_started.wait()
    agent.emit("agent_state_changed", SimpleNamespace(old_state="speaking", new_state="idle"))

    await avatar.stop()
    await asyncio.sleep(0)

    assert room.local_participant.published == []
