# Facemarket LiveKit plugin

`livekit-plugins-facemarket` starts a Facemarket renderer in a LiveKit room and bridges LiveKit Agents speech events to its Data Channel protocol.

## Install and compatibility

```bash
pip install livekit-plugins-facemarket
```

Requires Python `>=3.10,<3.15`, LiveKit Agents `>=1.6.6,<2`, and LiveKit API `>=1.1.1,<2`.

## Configuration

Keep secrets in the backend environment:

```bash
export FACEMARKET_API_KEY=...
export FACEMARKET_AVATAR_ID=...
export LIVEKIT_URL=wss://your-livekit.example.com
export LIVEKIT_API_KEY=...
export LIVEKIT_API_SECRET=...
```

Optional variables: `FACEMARKET_BASE_URL` (defaults to `https://facemarket.ai/vih/dispatcher`), `FACEMARKET_PREVIOUS_SESSION_ID` for an explicit reconnect, and `FACEMARKET_PRESERVE_SESSION=true` when job shutdown should leave the remote session alive. Constructor arguments override environment values: `api_key`, `base_url`, `livekit_url`, `livekit_api_key`, `livekit_api_secret`, `sandbox`, and `renderer_token_ttl`. Explicit blank values are invalid, and `renderer_token_ttl` must be positive. Sandbox sends `X-Env-Sandbox: true`.

Never expose API keys or the renderer token in browser code or Data Channel messages.

## Usage

See [examples/basic_agent.py](examples/basic_agent.py). `start()` completes after Facemarket accepts `/v1/session/start`; it does not wait for renderer media or `scene.ready`. Pass `session_id=None` for a new session. Persist `avatar.session_id` and pass it to a *new* `AvatarSession` instance for explicit reconnect after process recreation.

Call `await avatar.stop()` only to explicitly end the remote platform session. A room disconnect does not end it. The example registers `avatar.stop` with `JobContext.add_shutdown_callback`, so it ends the remote session when the job actually shuts down instead of immediately after `AgentSession.start()`. Set `FACEMARKET_PRESERVE_SESSION=true` to skip that callback when preserving the session for later reconnect. `async with AvatarSession(...)` calls `stop()` on exit and has the same terminal semantics.

## Callbacks and protocol

Use `@avatar.on(name)` for these callbacks:

- `scene.ready`, `scene.resourceTransition`, `session.state`, `session.closing`, `system.idleTrigger`
- `error`, `custom_event`, and `protocol_error`

Callbacks receive `DataChannelEvent`, which preserves `event`, `data`, `request_id`, `response_id`, `seq`, `timestamp`, sender `participant_identity`, and `topic`. `protocol_error` receives `DataChannelProtocolError` for malformed packets. `AvatarSession` automatically publishes reliable voice/ASR/response bridge events, assigns a stable response ID per agent utterance, and publishes `control.interrupt` from `await avatar.interrupt(request_id=None)`. Its HTTP client, token factory, and lifecycle coordination remain backend-only boundaries.

`scene.ready` is forwarded only as the platform protocol event `SCENE_READY`; it does not imply or trigger a separate avatar-session readiness state.

## Checks

```bash
python -m pytest -q
python -m ruff check .
python -m black --check livekit tests examples
python -m compileall -q livekit examples
```
