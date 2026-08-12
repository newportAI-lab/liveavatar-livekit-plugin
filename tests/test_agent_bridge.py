from types import SimpleNamespace

from fakes import FakeAgentSession

from livekit.plugins.facemarket.agent_bridge import AgentSessionBridge


def test_uninstall_preserves_application_callbacks():
    session = FakeAgentSession()
    application_events = []
    session.on("user_state_changed", lambda event: application_events.append(event))
    bridge = AgentSessionBridge(session, lambda event: None)

    bridge.install()
    bridge.uninstall()
    session.emit("user_state_changed", "application-event")

    assert application_events == ["application-event"]
    assert len(session.callbacks["user_state_changed"]) == 1


def test_user_turn_and_agent_response_share_request_id():
    session = FakeAgentSession()
    published = []
    bridge = AgentSessionBridge(session, published.append)
    bridge.install()

    session.emit("user_state_changed", SimpleNamespace(old_state="listening", new_state="speaking"))
    session.emit("user_input_transcribed", SimpleNamespace(transcript="hello", is_final=False))
    session.emit("user_input_transcribed", SimpleNamespace(transcript="hello", is_final=True))
    session.emit("user_state_changed", SimpleNamespace(old_state="speaking", new_state="listening"))
    session.emit(
        "agent_state_changed", SimpleNamespace(old_state="listening", new_state="speaking")
    )
    session.emit(
        "agent_state_changed", SimpleNamespace(old_state="speaking", new_state="listening")
    )

    assert [event.event for event in published] == [
        "input.voice.start",
        "input.asr.partial",
        "input.asr.final",
        "input.voice.finish",
        "response.audio.start",
        "response.audio.finish",
    ]
    request_ids = {event.request_id for event in published}
    assert len(request_ids) == 1
    assert all(event.response_id is None for event in published[:4])
    assert published[4].response_id == published[5].response_id
    assert published[4].response_id is not None
    assert published[1].seq == 0
    assert published[2].seq is None


def test_new_user_turn_gets_new_request_id_and_duplicate_state_is_ignored():
    session = FakeAgentSession()
    published = []
    bridge = AgentSessionBridge(session, published.append)
    bridge.install()

    session.emit("user_state_changed", SimpleNamespace(old_state="listening", new_state="speaking"))
    first_id = published[-1].request_id
    session.emit("user_state_changed", SimpleNamespace(old_state="speaking", new_state="speaking"))
    session.emit("user_state_changed", SimpleNamespace(old_state="speaking", new_state="listening"))
    session.emit("user_state_changed", SimpleNamespace(old_state="listening", new_state="speaking"))

    assert [event.event for event in published] == [
        "input.voice.start",
        "input.voice.finish",
        "input.voice.start",
    ]
    assert published[-1].request_id != first_id


def test_proactive_speech_creates_and_clears_request_id():
    session = FakeAgentSession()
    published = []
    bridge = AgentSessionBridge(session, published.append)
    bridge.install()

    session.emit("agent_state_changed", SimpleNamespace(old_state="idle", new_state="speaking"))
    first_id = published[-1].request_id
    session.emit("agent_state_changed", SimpleNamespace(old_state="speaking", new_state="idle"))
    session.emit("agent_state_changed", SimpleNamespace(old_state="idle", new_state="speaking"))
    second_id = published[-1].request_id
    second_response_id = published[-1].response_id
    session.emit("agent_state_changed", SimpleNamespace(old_state="speaking", new_state="idle"))

    assert [event.event for event in published] == [
        "response.audio.start",
        "response.audio.finish",
        "response.audio.start",
        "response.audio.finish",
    ]
    assert second_id != first_id
    assert published[0].response_id == published[1].response_id
    assert second_response_id == published[3].response_id
    assert second_response_id != published[0].response_id


def test_response_correlation_is_frozen_during_barge_in():
    session = FakeAgentSession()
    published = []
    bridge = AgentSessionBridge(session, published.append)
    bridge.install()

    session.emit("user_state_changed", SimpleNamespace(old_state="listening", new_state="speaking"))
    first_turn_id = published[-1].request_id
    session.emit("user_state_changed", SimpleNamespace(old_state="speaking", new_state="listening"))
    session.emit(
        "agent_state_changed", SimpleNamespace(old_state="listening", new_state="speaking")
    )
    first_response_id = published[-1].response_id
    session.emit("user_state_changed", SimpleNamespace(old_state="listening", new_state="speaking"))
    second_turn_id = published[-1].request_id
    session.emit(
        "agent_state_changed", SimpleNamespace(old_state="speaking", new_state="listening")
    )
    first_finish = published[-1]
    session.emit(
        "agent_state_changed", SimpleNamespace(old_state="listening", new_state="speaking")
    )
    second_start = published[-1]

    assert first_turn_id != second_turn_id
    assert first_finish.request_id == first_turn_id
    assert first_finish.response_id == first_response_id
    assert second_start.request_id == second_turn_id
    assert second_start.response_id != first_response_id


def test_completed_user_turn_is_consumed_after_response_finish():
    session = FakeAgentSession()
    published = []
    bridge = AgentSessionBridge(session, published.append)
    bridge.install()

    session.emit("user_state_changed", SimpleNamespace(old_state="listening", new_state="speaking"))
    user_turn_id = published[-1].request_id
    session.emit("user_state_changed", SimpleNamespace(old_state="speaking", new_state="listening"))
    session.emit(
        "agent_state_changed", SimpleNamespace(old_state="listening", new_state="speaking")
    )
    session.emit(
        "agent_state_changed", SimpleNamespace(old_state="speaking", new_state="listening")
    )
    session.emit(
        "agent_state_changed", SimpleNamespace(old_state="listening", new_state="speaking")
    )

    assert published[-1].request_id != user_turn_id


def test_prompt_is_single_use_and_reset_clears_it():
    session = FakeAgentSession()
    published = []
    bridge = AgentSessionBridge(session, published.append)
    bridge.install()

    bridge.arm_prompt()
    session.emit("agent_state_changed", SimpleNamespace(old_state="idle", new_state="speaking"))
    session.emit("agent_state_changed", SimpleNamespace(old_state="speaking", new_state="idle"))
    session.emit("agent_state_changed", SimpleNamespace(old_state="idle", new_state="speaking"))
    session.emit("agent_state_changed", SimpleNamespace(old_state="speaking", new_state="idle"))
    bridge.arm_prompt()
    bridge.reset()
    session.emit("agent_state_changed", SimpleNamespace(old_state="idle", new_state="speaking"))

    assert [event.event for event in published] == [
        "response.audio.promptStart",
        "response.audio.promptFinish",
        "response.audio.start",
        "response.audio.finish",
        "response.audio.start",
    ]


def test_failed_prompt_start_does_not_leave_prompt_mode_armed():
    session = FakeAgentSession()
    published = []
    should_fail = True

    def fail_publish(event):
        nonlocal should_fail
        if should_fail:
            should_fail = False
            raise RuntimeError("publish failed")
        published.append(event)

    bridge = AgentSessionBridge(session, fail_publish)
    bridge.install()
    bridge.arm_prompt()

    try:
        session.emit("agent_state_changed", SimpleNamespace(old_state="idle", new_state="speaking"))
    except RuntimeError:
        pass
    session.emit("agent_state_changed", SimpleNamespace(old_state="speaking", new_state="idle"))
    session.emit("agent_state_changed", SimpleNamespace(old_state="idle", new_state="speaking"))

    assert [event.event for event in published] == ["response.audio.finish", "response.audio.start"]
