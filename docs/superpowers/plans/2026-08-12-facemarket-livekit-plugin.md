# Facemarket LiveKit Python Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a publishable `livekit-plugins-facemarket` package that starts or reconnects a Facemarket renderer in a developer-owned LiveKit room and automatically bridges LiveKit Agents conversation events to the Facemarket Data Channel protocol.

**Architecture:** `AvatarSession` is the public orchestrator. Focused internal modules own the Facemarket HTTP API, renderer token creation, protocol validation, callback dispatch, and the LiveKit Agents 1.6 event adapter; all external boundaries are injectable for credential-free tests.

**Tech Stack:** Python 3.10+, Hatchling, `livekit-agents>=1.6.6,<2`, `livekit-api>=1.1.1,<2`, `httpx>=0.25,<1`, pytest, pytest-asyncio, Ruff, Black.

## Global Constraints

- Distribution name is `livekit-plugins-facemarket`; import path is `livekit.plugins.facemarket`.
- Support Python `>=3.10,<3.15`, matching LiveKit Agents 1.6.6 metadata.
- Facemarket defaults to `https://facemarket.ai/vih/dispatcher`; secrets remain backend-only.
- `start()` completes at successful `/v1/session/start`; it never waits for renderer media or `scene.ready`.
- Only explicit `stop()` calls `/v1/session/stop`; RTC disconnects never terminate the platform session.
- A caller reconnects only by explicitly passing `session_id` to a new `AvatarSession`.
- Use reliable Data Channel publication without assigning protocol meaning to topic.
- Do not modify Dispatcher, Renderer, STT, LLM, TTS, frontend, or hosted LiveKit code.
- Every behavior change follows red-green-refactor and every task ends in a focused commit.

## File map

- `pyproject.toml`: package metadata, dependency floors, build and test tooling.
- `livekit/plugins/facemarket/errors.py`: public exception hierarchy.
- `livekit/plugins/facemarket/protocol.py`: event constants, envelopes, validation, encoding.
- `livekit/plugins/facemarket/api.py`: asynchronous Facemarket session API.
- `livekit/plugins/facemarket/token.py`: renderer JWT construction.
- `livekit/plugins/facemarket/events.py`: isolated async callback registry.
- `livekit/plugins/facemarket/agent_bridge.py`: LiveKit Agents 1.6 event adaptation and request correlation.
- `livekit/plugins/facemarket/avatar.py`: lifecycle orchestration, room hooks, tracked publishing.
- `livekit/plugins/facemarket/__init__.py`: supported public exports.
- `tests/fakes.py`: narrow fake Room, participant, AgentSession, and packet boundaries.
- `examples/basic_agent.py`: minimal integration and explicit reconnect example.
- `README.md`, `README.zh.md`: user documentation.

---

### Task 1: Package skeleton and public errors

**Files:**
- Create: `pyproject.toml`
- Create: `livekit/plugins/facemarket/__init__.py`
- Create: `livekit/plugins/facemarket/errors.py`
- Create: `livekit/plugins/facemarket/version.py`
- Create: `livekit/plugins/facemarket/py.typed`
- Create: `tests/test_package.py`

**Interfaces:**
- Produces: `__version__: str`; `FacemarketError`, `ConfigurationError`, `SessionAlreadyStartedError`, `SessionStoppedError`, `APIError(code: int, message: str)`, `SessionStartError`, and `DataChannelProtocolError`.

- [ ] **Step 1: Write failing package tests**

```python
from livekit.plugins import facemarket

def test_public_package_identity():
    assert facemarket.__version__ == "0.1.0"
    error = facemarket.APIError(1001, "avatar not found")
    assert error.code == 1001
    assert error.message == "avatar not found"
    assert "1001" in str(error)
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_package.py -q`  
Expected: FAIL because `livekit.plugins.facemarket` does not exist.

- [ ] **Step 3: Add minimal package metadata and errors**

Configure Hatchling for `livekit/plugins/facemarket`, the exact dependency constraints in the header, pytest `asyncio_mode = "auto"`, and Ruff/Black line length 100. Implement the exception hierarchy and export it from `__init__.py`.

- [ ] **Step 4: Verify green and build metadata**

Run: `python -m pytest tests/test_package.py -q`  
Expected: PASS.

Run: `python -m pip install -e '.[dev]'` then `python -m build`  
Expected: editable install succeeds and wheel name begins `livekit_plugins_facemarket-0.1.0`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml livekit tests/test_package.py
git commit -m "build: scaffold facemarket plugin package"
```

### Task 2: Data Channel protocol

**Files:**
- Create: `livekit/plugins/facemarket/protocol.py`
- Create: `tests/test_protocol.py`
- Modify: `livekit/plugins/facemarket/__init__.py`

**Interfaces:**
- Produces: frozen `DataChannelEvent(event, data, request_id, response_id, seq, timestamp, participant_identity, topic)`; `decode_event(data: bytes, *, participant_identity: str | None = None, topic: str | None = None) -> DataChannelEvent`; `encode_event(event: DataChannelEvent) -> bytes`.
- Produces constants: `SCENE_READY`, `SCENE_RESOURCE_TRANSITION`, `SESSION_STATE`, `SESSION_CLOSING`, `IDLE_TRIGGER`, `ERROR`, `CUSTOM_EVENT`, `PROTOCOL_ERROR`, `SESSION_READY`.

- [ ] **Step 1: Write failing encode/decode and validation tests**

```python
def test_round_trip_preserves_envelope_metadata():
    original = DataChannelEvent(
        event="input.asr.partial", data={"text": "hel"},
        request_id="req-1", seq=0, timestamp=123,
    )
    assert decode_event(encode_event(original)) == original

@pytest.mark.parametrize("payload", [
    b"not-json", b"[]", b'{"event": 1}',
    b'{"event":"session.state","data":{}}',
    b'{"event":"error","data":{"message":1}}',
])
def test_invalid_packet_raises_protocol_error(payload):
    with pytest.raises(DataChannelProtocolError):
        decode_event(payload)
```

Add positive tests for every known event, resource-transition required IDs, integer-but-not-bool `seq/timestamp`, unknown valid events, participant identity, and topic preservation.

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_protocol.py -q`  
Expected: FAIL on missing protocol module.

- [ ] **Step 3: Implement minimal immutable protocol layer**

Encode only non-`None` optional fields. Decode UTF-8 JSON, validate the common envelope and known-event payloads exactly as specified, and retain unknown valid events unchanged so `AvatarSession` can map them to `custom_event`.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_protocol.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add livekit/plugins/facemarket/protocol.py livekit/plugins/facemarket/__init__.py tests/test_protocol.py
git commit -m "feat: add facemarket data channel protocol"
```

### Task 3: Facemarket session API

**Files:**
- Create: `livekit/plugins/facemarket/api.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Produces: `SessionInfo(session_id: str)`.
- Produces: `ApiClient(api_key: str, base_url: str, sandbox: bool = False, client: httpx.AsyncClient | None = None)` with `start_session(*, avatar_id, agent_identity, sfu_url, renderer_token, session_id=None) -> SessionInfo`, `stop_session(session_id) -> None`, and `aclose() -> None`.

- [ ] **Step 1: Write failing request/response tests**

```python
@pytest.mark.asyncio
async def test_new_start_omits_session_id(api_and_http):
    api, http = api_and_http
    http.post.return_value = response({"code": 0, "data": {"sessionId": "new-id"}})
    info = await api.start_session(
        avatar_id="avatar-1", agent_identity="agent-1",
        sfu_url="wss://lk", renderer_token="jwt",
    )
    assert info.session_id == "new-id"
    assert http.post.call_args.kwargs["json"] == {
        "avatarId": "avatar-1", "mode": "rtcAgent",
        "agentIdentity": "agent-1", "sfuUrl": "wss://lk", "rendererToken": "jwt",
    }
```

Add tests for explicit `sessionId`, authoritative response ID, `/v1/session/stop`, bearer/content headers, sandbox header, nonzero code, absent response ID, native HTTP status/timeout errors, injected-client ownership, and idempotent `aclose()`.

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_api.py -q`  
Expected: FAIL on missing API client.

- [ ] **Step 3: Implement the minimal API client**

Use a 30-second `httpx.Timeout`. Close only internally created clients. Strip trailing `/` from `base_url`. Preserve native HTTP exceptions after `raise_for_status()`.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_api.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add livekit/plugins/facemarket/api.py tests/test_api.py
git commit -m "feat: add facemarket session api client"
```

### Task 4: Renderer token factory

**Files:**
- Create: `livekit/plugins/facemarket/token.py`
- Create: `tests/test_token.py`

**Interfaces:**
- Produces: `RendererToken(token: str, identity: str)`.
- Produces: `create_renderer_token(*, api_key: str, api_secret: str, room_name: str, agent_identity: str, ttl: datetime.timedelta, identity_factory: Callable[[], str] | None = None) -> RendererToken`.

- [ ] **Step 1: Write failing verified-claims test**

```python
def test_renderer_claims():
    result = create_renderer_token(
        api_key="key", api_secret="secret", room_name="room-1",
        agent_identity="agent-1", ttl=timedelta(hours=4, minutes=30),
        identity_factory=lambda: "renderer-fixed",
    )
    claims = TokenVerifier("key", "secret").verify(result.token)
    assert result.identity == "renderer-fixed"
    assert claims.identity == "renderer-fixed"
    assert claims.kind == "agent"
    assert claims.attributes == {"lk.publish_on_behalf": "agent-1"}
    assert claims.video.room == "room-1"
    assert claims.video.room_join and claims.video.can_publish
    assert claims.video.can_subscribe and claims.video.can_publish_data
```

Also decode JWT timestamps and assert expiration is within five seconds of the configured TTL. Test blank credential, room, and identity inputs raise `ConfigurationError`.

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_token.py -q`  
Expected: FAIL on missing token factory.

- [ ] **Step 3: Implement with current LiveKit API**

Build `AccessToken(...).with_identity(...).with_ttl(...).with_kind("agent").with_attributes(...).with_grants(VideoGrants(room_join=True, room=..., can_publish=True, can_subscribe=True, can_publish_data=True)).to_jwt()`.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_token.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add livekit/plugins/facemarket/token.py tests/test_token.py
git commit -m "feat: generate renderer livekit tokens"
```

### Task 5: Callback registry and LiveKit Agents 1.6 bridge

**Files:**
- Create: `livekit/plugins/facemarket/events.py`
- Create: `livekit/plugins/facemarket/agent_bridge.py`
- Create: `tests/fakes.py`
- Create: `tests/test_events.py`
- Create: `tests/test_agent_bridge.py`

**Interfaces:**
- Produces: `EventDispatcher.on(name)`, `add(name, callback)`, `remove(name, callback)`, and async `dispatch(name, *args)` with callback isolation.
- Produces: `AgentSessionBridge(session, publish: Callable[[DataChannelEvent], None])`, `install()`, `uninstall()`, `arm_prompt()`, and `reset()`.

- [ ] **Step 1: Write failing callback isolation tests**

Register one callback that raises and a second that appends its input; assert `dispatch()` logs the first failure and still invokes the second. Assert `uninstall()` removes exactly the bridge callbacks and preserves callbacks owned by the application.

- [ ] **Step 2: Write failing LiveKit 1.6 contract tests**

Use current documented events, not removed aliases:

```python
session.emit("user_state_changed", SimpleNamespace(old_state="listening", new_state="speaking"))
session.emit("user_input_transcribed", SimpleNamespace(transcript="hello", is_final=False))
session.emit("user_state_changed", SimpleNamespace(old_state="speaking", new_state="listening"))
session.emit("agent_state_changed", SimpleNamespace(old_state="listening", new_state="speaking"))
session.emit("agent_state_changed", SimpleNamespace(old_state="speaking", new_state="listening"))
```

Assert events map to voice start, ASR partial with `seq=0`, voice finish, response start, and response finish. Add final transcript, one UUID per turn, a new UUID on the next user turn, proactive speech ID creation/cleanup, prompt start/finish, prompt single-use, and reset tests.

- [ ] **Step 3: Verify red**

Run: `python -m pytest tests/test_events.py tests/test_agent_bridge.py -q`  
Expected: FAIL on missing modules.

- [ ] **Step 4: Implement minimal bridge**

Treat only `new_state == "speaking"` transitions as start and `old_state == "speaking" and new_state != "speaking"` as finish. Ignore duplicate state notifications. Call the synchronous `publish` boundary with `DataChannelEvent`; `AvatarSession` owns task scheduling. Increment partial `seq` from zero and do not increment it for final transcripts.

- [ ] **Step 5: Verify against installed SDK contracts**

Run: `python -c "from livekit.agents import AgentSession, UserStateChangedEvent, AgentStateChangedEvent, UserInputTranscribedEvent; print(AgentSession, UserStateChangedEvent, AgentStateChangedEvent, UserInputTranscribedEvent)"`  
Expected: all four imports succeed under the declared dependency floor.

Run: `python -m pytest tests/test_events.py tests/test_agent_bridge.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add livekit/plugins/facemarket/events.py livekit/plugins/facemarket/agent_bridge.py tests/fakes.py tests/test_events.py tests/test_agent_bridge.py
git commit -m "feat: bridge livekit agent session events"
```

### Task 6: AvatarSession lifecycle and room protocol

**Files:**
- Create: `livekit/plugins/facemarket/avatar.py`
- Create: `tests/test_avatar_lifecycle.py`
- Create: `tests/test_avatar_events.py`
- Create: `tests/test_integration.py`
- Modify: `livekit/plugins/facemarket/__init__.py`
- Modify: `tests/fakes.py`

**Interfaces:**
- Produces: `AvatarSession(avatar_id, api_key=None, base_url=None, livekit_api_key=None, livekit_api_secret=None, sandbox=False, renderer_token_ttl=timedelta(hours=4, minutes=30), *, api_client=None, token_factory=create_renderer_token)`.
- Produces: `session_id: str | None`, `on(event)`, async `start(agent_session, *, room, session_id=None) -> None`, async `stop() -> None`, async `interrupt() -> None`, and async context methods.

- [ ] **Step 1: Write failing lifecycle tests**

Cover configuration precedence, connected-room validation, request fields, explicit reconnect, authoritative response ID, immediate return, compatible idempotent start, incompatible repeated start, failed-start listener cleanup/retry, new renderer identity on retry, concurrent stop, stop retry after API failure, terminal no-restart, and context-manager stop.

Use a fake room exposing the real boundary names: `name`, `url`, `connection_state`, `local_participant.identity`, `on`, `off`, and async `local_participant.publish_data(payload, reliable=True)`.

- [ ] **Step 2: Write failing inbound and publication tests**

Feed fake `rtc.DataPacket`-shaped objects to the installed `data_received` callback. Assert known events, unknown-to-`custom_event`, protocol errors, full metadata, `scene.ready` one-shot readiness, idle prompt arming, reliable publication, `interrupt()` envelope, publish-failure local error, callback isolation, task cancellation on failed start/stop, and prompt reset on room `disconnected`.

- [ ] **Step 3: Verify red**

Run: `python -m pytest tests/test_avatar_lifecycle.py tests/test_avatar_events.py tests/test_integration.py -q`  
Expected: FAIL because `AvatarSession` is not implemented.

- [ ] **Step 4: Implement lifecycle state machine**

Use explicit internal states `NEW`, `STARTING`, `ACTIVE`, `STOPPING`, `STOPPED`. Guard transitions with an `asyncio.Lock`; share a stored stop task for concurrent callers. Capture the successful `(agent_session, room, requested_session_id)` tuple for compatible repeated-start checks. On start failure, uninstall both bridges, cancel and await tracked tasks, close only owned HTTP resources, reset to `NEW`, and re-raise.

- [ ] **Step 5: Implement room and task handling**

Install `data_received` and `disconnected` callbacks before the API call and remove them during failed-start cleanup or terminal stop. Convert packets with `decode_event`; map `scene.ready` to one-shot `session_ready`, known events to their names, unknown events to `custom_event`, and invalid packets to `protocol_error`. Track every `publish_data` task, consume exceptions, and dispatch a local error event without recursive re-publication.

- [ ] **Step 6: Verify green and full integration path**

Run: `python -m pytest tests/test_avatar_lifecycle.py tests/test_avatar_events.py tests/test_integration.py -q`  
Expected: PASS.

Run: `python -m pytest -q`  
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add livekit/plugins/facemarket/avatar.py livekit/plugins/facemarket/__init__.py tests
git commit -m "feat: add facemarket avatar session"
```

### Task 7: Example and bilingual documentation

**Files:**
- Create: `examples/basic_agent.py`
- Modify: `README.md`
- Create: `README.zh.md`
- Create: `tests/test_example.py`

**Interfaces:**
- Consumes: the public API exported by `livekit.plugins.facemarket`.
- Produces: runnable usage documentation for new sessions, explicit reconnect, callbacks, sandbox, and explicit stop.

- [ ] **Step 1: Write failing example smoke test**

```python
def test_example_compiles():
    source = Path("examples/basic_agent.py").read_text()
    compile(source, "examples/basic_agent.py", "exec")
    assert "from livekit.plugins import facemarket" in source
    assert "session_id=previous_session_id" in source
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_example.py -q`  
Expected: FAIL because the example is absent.

- [ ] **Step 3: Add the minimal example**

Show `ctx.connect()`, `AgentSession`, `AvatarSession`, callbacks, `avatar.start(session, room=ctx.room, session_id=previous_session_id)`, persistence of `avatar.session_id`, then `session.start(...)`. Use environment variables for all secrets and explain that `previous_session_id` is `None` for a new session.

- [ ] **Step 4: Write both README files**

Document installation, Python/LiveKit compatibility, constructor options, environment variables, credential security, start completion semantics, explicit reconnect and stop, all callbacks, `DataChannelEvent`, sandbox header, architecture boundaries, and test commands. Keep English and Chinese API examples structurally identical.

- [ ] **Step 5: Verify green**

Run: `python -m pytest tests/test_example.py -q`  
Expected: PASS.

Run: `python -m compileall -q livekit examples`  
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add examples/basic_agent.py README.md README.zh.md tests/test_example.py
git commit -m "docs: add facemarket plugin usage guides"
```

### Task 8: Release-quality verification

**Files:**
- Modify only files implicated by verification failures.

**Interfaces:**
- Produces: a clean, buildable, typed package whose tests pass without credentials.

- [ ] **Step 1: Run format and static checks**

Run: `python -m ruff check .`  
Expected: exit 0.

Run: `python -m black --check livekit tests examples`  
Expected: exit 0.

- [ ] **Step 2: Run the complete test suite**

Run: `python -m pytest -q`  
Expected: all tests PASS with no unhandled-task warnings.

- [ ] **Step 3: Build and inspect artifacts**

Run: `python -m build`  
Expected: sdist and wheel build successfully.

Run: `python -m twine check dist/*`  
Expected: all distributions PASS.

Run: `python -c "from livekit.plugins import facemarket; print(facemarket.__version__)"`  
Expected: prints `0.1.0`.

- [ ] **Step 4: Review the final diff against scope**

Run: `git diff --check HEAD~7..HEAD` and `git status --short`  
Expected: no whitespace errors and no accidental files; do not modify Dispatcher, Renderer, or the reference SDK.

- [ ] **Step 5: Commit verification-only fixes if needed**

```bash
git add pyproject.toml livekit tests examples README.md README.zh.md
git commit -m "chore: finalize facemarket plugin"
```

Skip this commit when verification required no changes.
