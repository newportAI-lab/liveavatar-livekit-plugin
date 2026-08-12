import asyncio
from datetime import timedelta

import pytest
from fakes import FakeAgentSession, FakeApiClient, FakeRoom

from livekit import rtc
from livekit.plugins.facemarket import avatar as avatar_module
from livekit.plugins.facemarket.avatar import AvatarSession
from livekit.plugins.facemarket.errors import (
    ConfigurationError,
    SessionAlreadyStartedError,
    SessionStoppedError,
)


def token_factory(**kwargs):
    from livekit.plugins.facemarket.token import RendererToken

    return RendererToken("jwt", "renderer-1")


def make_avatar(api):
    return AvatarSession(
        "avatar-1",
        api_key="facemarket",
        livekit_url="wss://lk",
        livekit_api_key="lk",
        livekit_api_secret="secret",
        api_client=api,
        token_factory=token_factory,
    )


@pytest.mark.asyncio
async def test_start_uses_room_fields_and_is_compatible_idempotent():
    api, room, agent = FakeApiClient(), FakeRoom(), FakeAgentSession()
    avatar = make_avatar(api)

    await avatar.start(agent, room=room)
    await avatar.start(agent, room=room)

    assert avatar.session_id == "server-id"
    assert len(api.starts) == 1
    assert api.starts[0] == {
        "avatar_id": "avatar-1",
        "agent_identity": "agent-1",
        "sfu_url": "wss://lk",
        "renderer_token": "jwt",
        "session_id": None,
    }
    assert room.isconnected_calls == 1


@pytest.mark.asyncio
async def test_invalid_room_and_incompatible_repeated_start_raise():
    avatar = make_avatar(FakeApiClient())
    with pytest.raises(ConfigurationError):
        await avatar.start(FakeAgentSession(), room=FakeRoom(connected=False))
    agent, room = FakeAgentSession(), FakeRoom()
    await avatar.start(agent, room=room)
    with pytest.raises(SessionAlreadyStartedError):
        await avatar.start(FakeAgentSession(), room=room)


@pytest.mark.asyncio
async def test_real_room_contract_exposes_connectivity_but_not_server_url():
    room = rtc.Room()
    avatar = make_avatar(FakeApiClient())

    assert room.isconnected() is False
    assert not hasattr(room, "url")
    with pytest.raises(ConfigurationError, match="connected"):
        await avatar.start(FakeAgentSession(), room=room)


@pytest.mark.asyncio
async def test_livekit_url_falls_back_to_environment(monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "wss://environment-livekit")
    api = FakeApiClient()
    avatar = AvatarSession(
        "avatar-1",
        api_key="facemarket",
        livekit_api_key="lk",
        livekit_api_secret="secret",
        api_client=api,
        token_factory=token_factory,
    )

    await avatar.start(FakeAgentSession(), room=FakeRoom())

    assert api.starts[0]["sfu_url"] == "wss://environment-livekit"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "environment"),
    [
        ("api_key", "FACEMARKET_API_KEY"),
        ("base_url", "FACEMARKET_BASE_URL"),
        ("livekit_url", "LIVEKIT_URL"),
        ("livekit_api_key", "LIVEKIT_API_KEY"),
        ("livekit_api_secret", "LIVEKIT_API_SECRET"),
    ],
)
async def test_explicit_blank_configuration_does_not_fall_back_to_environment(
    monkeypatch, field, environment
):
    monkeypatch.setenv(environment, "environment-value")
    arguments = {
        "api_key": "facemarket",
        "base_url": "https://facemarket.example",
        "livekit_url": "wss://lk",
        "livekit_api_key": "lk",
        "livekit_api_secret": "secret",
    }
    arguments[field] = "   "
    avatar = AvatarSession(
        "avatar-1",
        **arguments,
        api_client=FakeApiClient(),
        token_factory=token_factory,
    )

    with pytest.raises(ConfigurationError, match=field):
        await avatar.start(FakeAgentSession(), room=FakeRoom())


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl", [timedelta(0), timedelta(seconds=-1)])
async def test_renderer_token_ttl_must_be_positive(ttl):
    avatar = AvatarSession(
        "avatar-1",
        api_key="facemarket",
        livekit_url="wss://lk",
        livekit_api_key="lk",
        livekit_api_secret="secret",
        renderer_token_ttl=ttl,
        api_client=FakeApiClient(),
        token_factory=token_factory,
    )

    with pytest.raises(ConfigurationError, match="renderer_token_ttl"):
        await avatar.start(FakeAgentSession(), room=FakeRoom())


@pytest.mark.asyncio
async def test_failed_start_cleans_listeners_and_can_retry():
    api, room, agent = FakeApiClient(), FakeRoom(), FakeAgentSession()
    api.fail_start = True
    avatar = make_avatar(api)
    with pytest.raises(RuntimeError):
        await avatar.start(agent, room=room)
    assert not room.callbacks["data_received"]
    api.fail_start = False
    await avatar.start(agent, room=room)
    assert avatar.session_id == "server-id"


@pytest.mark.asyncio
async def test_stop_is_concurrent_retryable_and_terminal():
    api, room, agent = FakeApiClient(), FakeRoom(), FakeAgentSession()
    avatar = make_avatar(api)
    await avatar.start(agent, room=room)
    await asyncio.gather(avatar.stop(), avatar.stop())
    assert api.stops == ["server-id"]
    with pytest.raises(SessionStoppedError):
        await avatar.start(agent, room=room)


@pytest.mark.asyncio
async def test_cancelling_one_stop_waiter_does_not_cancel_shared_stop():
    class DelayedStopApiClient(FakeApiClient):
        def __init__(self):
            super().__init__()
            self.stop_started = asyncio.Event()
            self.release_stop = asyncio.Event()

        async def stop_session(self, session_id):
            self.stops.append(session_id)
            self.stop_started.set()
            await self.release_stop.wait()

    api = DelayedStopApiClient()
    avatar = make_avatar(api)
    await avatar.start(FakeAgentSession(), room=FakeRoom())
    cancelled_waiter = asyncio.create_task(avatar.stop())
    await api.stop_started.wait()
    completing_waiter = asyncio.create_task(avatar.stop())

    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter
    api.release_stop.set()
    await completing_waiter

    assert api.stops == ["server-id"]


@pytest.mark.asyncio
async def test_stop_can_retry_after_internal_cancellation():
    class CancelOnceApiClient(FakeApiClient):
        async def stop_session(self, session_id):
            self.stops.append(session_id)
            if len(self.stops) == 1:
                raise asyncio.CancelledError

    api = CancelOnceApiClient()
    avatar = make_avatar(api)
    await avatar.start(FakeAgentSession(), room=FakeRoom())

    with pytest.raises(asyncio.CancelledError):
        await avatar.stop()
    await avatar.stop()

    assert api.stops == ["server-id", "server-id"]


@pytest.mark.asyncio
async def test_stop_can_retry_after_api_failure():
    api = FakeApiClient()
    avatar = make_avatar(api)
    await avatar.start(FakeAgentSession(), room=FakeRoom())
    api.fail_stop = True

    with pytest.raises(RuntimeError, match="stop failed"):
        await avatar.stop()
    api.fail_stop = False
    await avatar.stop()

    assert api.stops == ["server-id", "server-id"]


@pytest.mark.asyncio
async def test_stop_retries_owned_client_teardown_without_repeating_remote_stop(monkeypatch):
    class CloseFailsOnceApiClient(FakeApiClient):
        def __init__(self):
            super().__init__()
            self.close_attempts = 0

        async def aclose(self):
            self.close_attempts += 1
            if self.close_attempts == 1:
                raise RuntimeError("close failed")
            self.closed = True

    api = CloseFailsOnceApiClient()
    monkeypatch.setattr(avatar_module, "ApiClient", lambda *args: api)
    avatar = AvatarSession(
        "avatar-1",
        api_key="facemarket",
        livekit_url="wss://lk",
        livekit_api_key="lk",
        livekit_api_secret="secret",
        token_factory=token_factory,
    )
    await avatar.start(FakeAgentSession(), room=FakeRoom())

    with pytest.raises(RuntimeError, match="close failed"):
        await avatar.stop()
    await avatar.stop()

    assert api.stops == ["server-id"]
    assert api.close_attempts == 2


@pytest.mark.asyncio
async def test_context_manager_stops():
    api = FakeApiClient()
    async with make_avatar(api) as session:
        await session.start(FakeAgentSession(), room=FakeRoom())
    assert api.stops == ["server-id"]


@pytest.mark.asyncio
async def test_stop_during_start_waits_then_stops_authoritative_session_once():
    class DelayedApiClient(FakeApiClient):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.delay = True
            self.release = asyncio.Event()

        async def start_session(self, **kwargs):
            self.starts.append(kwargs)
            self.started.set()
            await self.release.wait()
            from livekit.plugins.facemarket.api import SessionInfo

            return SessionInfo(self.session_id)

    api, room, agent = DelayedApiClient(), FakeRoom(), FakeAgentSession()
    session = make_avatar(api)
    start_task = asyncio.create_task(session.start(agent, room=room))
    await api.started.wait()
    stop_task = asyncio.create_task(session.stop())
    api.release.set()
    await asyncio.gather(start_task, stop_task)

    assert api.stops == ["server-id"]
    assert session.session_id == "server-id"
    with pytest.raises(SessionStoppedError):
        await session.start(agent, room=room)


@pytest.mark.asyncio
async def test_token_failure_after_listener_install_cleans_up_and_allows_retry():
    api, room, agent = FakeApiClient(), FakeRoom(), FakeAgentSession()
    attempts = 0

    def flaky_token_factory(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("token failed")
        return token_factory(**kwargs)

    session = AvatarSession(
        "avatar-1",
        api_key="facemarket",
        livekit_url="wss://lk",
        livekit_api_key="lk",
        livekit_api_secret="secret",
        api_client=api,
        token_factory=flaky_token_factory,
    )
    with pytest.raises(RuntimeError, match="token failed"):
        await session.start(agent, room=room)

    assert not room.callbacks["data_received"]
    assert not room.callbacks["disconnected"]
    assert all(not callbacks for callbacks in agent.callbacks.values())
    await session.start(agent, room=room)
    assert session.session_id == "server-id"


@pytest.mark.asyncio
async def test_cancelled_start_cleans_up_and_allows_retry_without_hanging_stop():
    class DelayedApiClient(FakeApiClient):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.delay = True

        async def start_session(self, **kwargs):
            self.starts.append(kwargs)
            self.started.set()
            if self.delay:
                await asyncio.Future()
            from livekit.plugins.facemarket.api import SessionInfo

            return SessionInfo(self.session_id)

    api, room, agent = DelayedApiClient(), FakeRoom(), FakeAgentSession()
    session = make_avatar(api)
    start_task = asyncio.create_task(session.start(agent, room=room))
    await api.started.wait()
    start_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await start_task

    assert not room.callbacks["data_received"]
    assert not room.callbacks["disconnected"]
    assert all(not callbacks for callbacks in agent.callbacks.values())
    api.delay = False
    await session.start(agent, room=room)
    assert session.session_id == "server-id"
    await asyncio.wait_for(session.stop(), timeout=0.1)
    with pytest.raises(SessionStoppedError):
        await session.start(agent, room=room)
