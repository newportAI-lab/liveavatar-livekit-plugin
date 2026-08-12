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

    assert [event.event for event in published] == [
        "response.audio.start",
        "response.audio.finish",
        "response.audio.start",
    ]
    assert published[-1].request_id != first_id


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
