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
export LIVEKIT_API_KEY=...
export LIVEKIT_API_SECRET=...
```

Optional variables: `FACEMARKET_BASE_URL` (defaults to `https://facemarket.ai/vih/dispatcher`) and `FACEMARKET_PREVIOUS_SESSION_ID` for an explicit reconnect. Constructor arguments override environment values: `api_key`, `base_url`, `livekit_api_key`, `livekit_api_secret`, `sandbox`, and `renderer_token_ttl`. Sandbox sends `X-Env-Sandbox: true`.

Never expose API keys or the renderer token in browser code or Data Channel messages.

## Usage

See [examples/basic_agent.py](examples/basic_agent.py). `start()` completes after Facemarket accepts `/v1/session/start`; it does not wait for renderer media or `scene.ready`. Pass `session_id=None` for a new session. Persist `avatar.session_id` and pass it to a *new* `AvatarSession` instance for explicit reconnect after process recreation.

Call `await avatar.stop()` only to explicitly end the remote platform session. A room disconnect does not end it. `async with AvatarSession(...)` calls `stop()` on exit, so do not use the context manager when preserving a session for later reconnect.

## Callbacks and protocol

Use `@avatar.on(name)` for these callbacks:

- `session_ready` (one-shot `scene.ready`)
- `scene.resourceTransition`, `session.state`, `session.closing`, `system.idleTrigger`
- `error`, `custom_event`, and `protocol_error`

Callbacks receive `DataChannelEvent`, which preserves `event`, `data`, `request_id`, `response_id`, `seq`, `timestamp`, sender `participant_identity`, and `topic`. `protocol_error` receives `DataChannelProtocolError` for malformed packets. `AvatarSession` automatically publishes reliable voice/ASR/response bridge events; its HTTP client, token factory, and lifecycle coordination remain backend-only boundaries.

## Checks

```bash
python -m pytest -q
python -m ruff check livekit tests
python -m black --check livekit tests
python -m compileall -q livekit examples
```
