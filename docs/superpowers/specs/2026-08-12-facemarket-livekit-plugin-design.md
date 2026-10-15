# Facemarket LiveKit Python Plugin Design

**Date:** 2026-08-12  
**Status:** Approved for implementation planning

## 1. Goal and scope

Build a publishable Python avatar plugin that connects a developer-owned LiveKit room and LiveKit Agents `AgentSession` to the Facemarket renderer platform.

The package is a rendering adapter and session-signaling bridge. The developer owns the LiveKit room and the STT, LLM, and TTS pipeline. Facemarket provides the renderer and platform session management.

The MVP includes:

- The `livekit-plugins-facemarket` Python distribution.
- The `livekit.plugins.facemarket` import package.
- A public `facemarket.AvatarSession` API.
- Facemarket session start, explicit reconnect, and stop requests.
- Renderer LiveKit token generation for a developer-owned room.
- Automatic `AgentSession` to Data Channel event forwarding.
- Validated inbound Data Channel event dispatch.
- Unit tests, mock integration tests, a minimal example, and English and Chinese README files.

The MVP does not include:

- Changes to the Java Dispatcher or Rust/C++ Renderer.
- Ownership or creation of the developer's LiveKit room.
- STT, LLM, TTS, or frontend implementations.
- PyPI publication.
- A real Facemarket/LiveKit end-to-end test in this repository.

## 2. Selected approach

Use an independent thin plugin with small internal components. Reuse the protocol behavior of the local `liveavatar-platform-rtc-python` repository as a reference, but do not depend on that package at runtime.

This is preferred over a single-file implementation because lifecycle, HTTP, token, protocol, and SDK compatibility concerns can be tested independently. It is preferred over sharing the platform RTC SDK because the two packages have different room ownership and token flows.

## 3. Package structure

```text
livekit-plugins-facemarket/
├── pyproject.toml
├── livekit/plugins/facemarket/
│   ├── __init__.py
│   ├── api.py
│   ├── avatar.py
│   ├── errors.py
│   ├── protocol.py
│   ├── token.py
│   ├── version.py
│   └── py.typed
├── examples/
├── tests/
├── README.md
└── README.zh.md
```

Responsibilities:

- `avatar.py`: public `AvatarSession`, lifecycle state, room hooks, AgentSession bridge, callbacks, and task tracking.
- `api.py`: authenticated asynchronous calls to the Facemarket session API.
- `protocol.py`: event constants, `DataChannelEvent`, JSON encoding, decoding, and validation.
- `token.py`: renderer identity creation and LiveKit JWT generation.
- `errors.py`: stable public exception types.
- `__init__.py`: supported public API and event constants only.

`AvatarSession` is the only primary entry point. Internal components use narrow interfaces so they can be replaced with fakes in tests.

## 4. Public API

The primary usage is:

```python
from livekit.plugins import facemarket

avatar = facemarket.AvatarSession(
    avatar_id="avatar_001",
    api_key="facemarket-api-key",
    livekit_url="wss://developer-livekit.example.com",
    livekit_api_key="developer-livekit-api-key",
    livekit_api_secret="developer-livekit-api-secret",
)

await avatar.start(agent_session, room=ctx.room)
persist(avatar.session_id)
```

Explicit reconnection uses a previously persisted platform session ID:

```python
await avatar.start(
    agent_session,
    room=ctx.room,
    session_id=previous_session_id,
)
```

The plugin never silently restores a session across instances. The caller owns persistence and explicitly supplies `session_id` when reconnecting.

Callbacks use decorator registration:

```python
@avatar.on("scene.ready")
async def on_scene_ready(event: facemarket.DataChannelEvent) -> None:
    ...
```

All inbound protocol callbacks receive the complete `DataChannelEvent` so applications retain correlation IDs, timestamps, participant identity, and topic metadata.

## 5. Configuration

Constructor arguments take precedence over environment variables.

- Facemarket API key: constructor `api_key`, otherwise `FACEMARKET_API_KEY`.
- Facemarket base URL: constructor `base_url`, otherwise `FACEMARKET_BASE_URL`, otherwise `https://facemarket.ai/vih/dispatcher`.
- LiveKit server URL: constructor `livekit_url`, otherwise `LIVEKIT_URL`.
- LiveKit API key: constructor `livekit_api_key`, otherwise `LIVEKIT_API_KEY`.
- LiveKit API secret: constructor `livekit_api_secret`, otherwise `LIVEKIT_API_SECRET`.
- Sandbox: constructor boolean; when true the API client adds `X-Env-Sandbox: true`.
- Renderer token TTL: configurable constructor duration with a default of 4 hours 30 minutes.

The plugin treats only `None` as absent configuration, so explicit blank constructor values do not fall back to environment values. It validates non-blank required configuration, a positive renderer token TTL, `room.isconnected()`, the room name, and the local participant identity before making a platform request. Secrets are backend-only and are never sent over a LiveKit Data Channel or exposed to frontend clients.

## 6. Session API

The client uses:

- `POST {base_url}/v1/session/start`
- `POST {base_url}/v1/session/stop`
- `Authorization: Bearer <FACEMARKET_API_KEY>`
- `Content-Type: application/json`
- `X-Env-Sandbox: true` only in sandbox mode

### 6.1 Start request

```json
{
  "avatarId": "avatar_001",
  "mode": "rtcAgent",
  "agentIdentity": "agent_xxx",
  "sfuUrl": "wss://developer-livekit.example.com",
  "rendererToken": "<jwt>",
  "sessionId": "optional_previous_session_id"
}
```

`sessionId` is omitted entirely for a new session. It is included only when the caller passes `session_id` to `start()`.

The platform response uses its common envelope:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "sessionId": "session_123"
  }
}
```

The plugin requires `code == 0` and a non-empty `data.sessionId`. The returned ID is the authoritative session ID even during reconnect.

### 6.2 Stop request

```json
{
  "sessionId": "session_123"
}
```

Only an explicit `AvatarSession.stop()` sends this request. A LiveKit disconnect, LiveKit automatic reconnect, or process termination does not stop the remote platform session.

## 7. Renderer LiveKit token

For each start attempt, the plugin signs a renderer token with the developer's LiveKit credentials.

- Identity: `renderer_<uuid>`.
- Participant kind: `agent`.
- Attribute: `lk.publish_on_behalf=<local agent identity>`.
- Room: the exact current room name.
- Grants: room join, publish, subscribe, and publish data.
- Expiration: the configured renderer token TTL.

The implementation uses the current LiveKit Python server SDK API: `AccessToken.with_identity`, `with_ttl`, `with_kind`, `with_attributes`, and `with_grants(VideoGrants(...))`.

A new renderer identity is generated for each new `AvatarSession` start attempt. If an HTTP start attempt fails and is retried on the same instance, a new renderer token and identity are generated so a partially consumed token cannot create an identity collision.

## 8. Start and lifecycle state

`start(agent_session, room, session_id=None)` performs these operations:

1. Validate instance state, credentials, and connected room properties.
2. Read the room's local participant identity and room name; use the configured LiveKit server URL.
3. Generate a renderer token.
4. Install room Data Channel listeners and AgentSession event listeners.
5. Call `/v1/session/start`.
6. Save the authoritative response session ID and transition to active.
7. Return immediately.

`start()` does not wait for renderer participation, a video track, or `scene.ready`. Platform acceptance of `/v1/session/start` is the completion point.

One `AvatarSession` instance represents one platform session lifecycle:

- A compatible repeated `start()` call while active returns the existing successful result without another API request.
- A repeated call with a different room, AgentSession, or requested reconnect ID raises `SessionAlreadyStartedError`.
- `stop()` is idempotent while stopping or stopped; concurrent callers await the same shielded stop operation, so canceling one waiter does not cancel shared teardown.
- After successful stop, the instance cannot start again and operations raise `SessionStoppedError`.
- A new session or a reconnect after process recreation uses a new `AvatarSession` instance.
- If the HTTP start step fails, installed listeners are removed, background tasks from that attempt are canceled, and the object returns to the unstarted state so the caller may retry.
- If explicit stop fails, the error is returned and the instance remains in a stopping state that permits `stop()` retry but never permits a new `start()`.

The object supports async context management. Normal context exit calls `stop()`. Applications that intentionally want the remote session to survive process teardown for later reconnect must not use this context behavior and must not call `stop()`.

## 9. Outbound AgentSession bridge

The plugin automatically forwards these AgentSession events over reliable LiveKit Data Channel messages:

| AgentSession behavior | Data Channel event |
| --- | --- |
| User starts speaking | `input.voice.start` |
| User stops speaking | `input.voice.finish` |
| Partial transcription | `input.asr.partial` |
| Final transcription | `input.asr.final` |
| Agent starts speaking | `response.audio.start` or `response.audio.promptStart` |
| Agent stops speaking | `response.audio.finish` or `response.audio.promptFinish` |

The bridge isolates LiveKit Agents SDK event names and payload extraction from the rest of `AvatarSession`. Implementation must verify these contracts against the selected current dependency version and cover them with contract-style unit tests.

### 9.1 Request correlation

- User speech entering the `speaking` state creates a new UUID request ID.
- Voice boundary, partial/final ASR, and the following agent response reuse that request ID.
- A later user-speaking start transition begins a new turn and replaces it.
- An agent utterance without a current user turn creates its own request ID at speech start and clears it at speech finish.
- Every agent utterance also creates a separate response ID that remains frozen from response start through finish, including during barge-in. A completed user turn is consumed after its correlated response finishes.
- Each partial transcript carries an increasing `seq` within the current user turn, starting at zero.

### 9.2 Prompt mode

Receiving `system.idleTrigger` marks the next agent utterance as a prompt. Its speech boundary messages use `response.audio.promptStart` and `response.audio.promptFinish`.

Prompt mode is consumed by exactly one utterance and resets when that utterance finishes. It also resets if publishing the prompt-start event fails, the session stops, or the room disconnects before the utterance completes. A later idle trigger can arm prompt mode again.

### 9.3 Publication failures

Data Channel publication is scheduled through tracked tasks. Exceptions are consumed and logged. Publication failures are dispatched to local `error` callbacks with an error event object and do not become unhandled background task exceptions.

## 10. Inbound Data Channel protocol

Messages use a JSON envelope:

```json
{
  "event": "session.state",
  "data": {"state": "connected"},
  "requestId": "optional",
  "responseId": "optional",
  "seq": 0,
  "timestamp": 1710000000000
}
```

The plugin accepts packets regardless of Data Channel topic. Topic and sending participant identity are retained as diagnostic fields.

Supported events:

| Protocol event | Plugin callback |
| --- | --- |
| `scene.ready` | `scene.ready` |
| `scene.resourceTransition` | `scene.resourceTransition` |
| `session.state` | `session.state` |
| `session.closing` | `session.closing` |
| `system.idleTrigger` | `system.idleTrigger` |
| `error` | `error` |
| Unknown valid event | `custom_event` |
| Invalid packet or known-event payload | `protocol_error` |

`scene.ready` is dispatched as its own protocol event. It has no relationship to a separate avatar-session readiness state, and repeated valid events are not deduplicated.

Validation matches the reference platform RTC SDK:

- The root must be an object with a string `event`.
- `requestId` and `responseId`, when present, must be strings.
- `seq` and `timestamp`, when present, must be integers but not booleans.
- Known events require an object `data` value when explicitly supplied. Omitted `data` defaults to `{}` so payloadless events such as `scene.ready`, `system.idleTrigger`, and `session.closing` remain valid.
- `session.state` requires string `data.state`.
- `scene.resourceTransition` requires non-empty string `previousResourceId` and `nextResourceId`; optional `message` must be a string.
- `error` requires string `data.message`.

Malformed packets do not reach business callbacks. They produce a local `protocol_error` callback carrying `DataChannelProtocolError` and diagnostic packet metadata where available.

Callback failures are logged and isolated so one callback does not prevent later callbacks from running. Local callback failures are not converted into platform `error` events.

## 11. Error model

Public exceptions include:

- `ConfigurationError`: missing credentials, invalid options, or unusable room state.
- `SessionAlreadyStartedError`: incompatible repeated use of an active instance.
- `SessionStoppedError`: an operation attempted after terminal stop.
- `APIError`: a nonzero platform response code, preserving code and message.
- `SessionStartError`: a nominally successful response missing `data.sessionId`.
- `DataChannelProtocolError`: malformed inbound protocol data.

Transport-level HTTP status, connection, and timeout errors retain the HTTP client's native exception types so callers can apply normal retry policies.

## 12. Testing strategy

Use `pytest` and `pytest-asyncio`. Behavior tests precede implementation changes.

Required coverage:

- Start/stop URLs, bearer authentication, content type, sandbox header, response envelope, HTTP errors, and platform errors.
- New start omits `sessionId`; explicit reconnect sends it; the response ID is authoritative.
- Renderer JWT identity, kind, attributes, room, grants, permissions, and expiration.
- `start()` returns after the HTTP response without waiting for renderer or `scene.ready`.
- Failed start cleans listeners and allows retry.
- Compatible repeated start is idempotent; incompatible repeat fails.
- Concurrent and repeated stop behavior, stop failure retry, and terminal no-restart behavior.
- All six automatic AgentSession event mappings.
- Shared request ID within a user turn, partial transcript sequence values, and independent proactive utterance IDs.
- Idle prompt arming, one-utterance consumption, and every reset path.
- All known inbound events, repeated `scene.ready` delivery, unknown valid events, and malformed protocol cases.
- Data Channel publication failure reporting and callback exception isolation.
- The minimal example imports successfully in a smoke test.

Tests use fake Room, local participant, AgentSession, API client, and token verifier boundaries. They do not require network credentials. A small mock integration test exercises `AvatarSession` through the complete start, event bridge, inbound event, and stop lifecycle.

## 13. Documentation and compatibility

The project supports Python 3.10 and later. The implementation plan must select and document a concrete minimum LiveKit Agents and LiveKit API version after checking current official documentation and installable package metadata. Runtime code must not guess SDK methods or event payloads.

Both README files document:

- Installation and environment variables.
- Backend-only credential handling.
- New-session and explicit-reconnect examples.
- AgentSession integration.
- Event callbacks and `DataChannelEvent` fields.
- Explicit stop semantics.
- Sandbox usage.
- The lack of STT, LLM, TTS, frontend, or hosted LiveKit responsibilities.

## 14. Acceptance criteria

The MVP is ready when:

1. The package builds as `livekit-plugins-facemarket` and imports as `livekit.plugins.facemarket`.
2. A caller can start a new session or explicitly reconnect using a persisted session ID.
3. The generated renderer token lets an agent-kind renderer join the exact developer room and publish on behalf of the local agent.
4. `start()` returns on platform acceptance; `scene.ready` remains an independent protocol event and is never translated into session readiness.
5. AgentSession conversation events are automatically and correctly correlated over reliable Data Channel messages.
6. Inbound protocol messages are validated and dispatched consistently with the reference Facemarket RTC SDK.
7. Only explicit stop terminates the remote session.
8. The full automated test suite and package build pass without real credentials.
9. English and Chinese documentation and the minimal example match the implemented API.
