import asyncio

import pytest
from fakes import FakeAgentSession, FakeApiClient, FakeRoom

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


@pytest.mark.asyncio
async def test_invalid_room_and_incompatible_repeated_start_raise():
    avatar = make_avatar(FakeApiClient())
    with pytest.raises(ConfigurationError):
        await avatar.start(FakeAgentSession(), room=FakeRoom(connection_state="disconnected"))
    agent, room = FakeAgentSession(), FakeRoom()
    await avatar.start(agent, room=room)
    with pytest.raises(SessionAlreadyStartedError):
        await avatar.start(FakeAgentSession(), room=room)


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
async def test_context_manager_stops():
    api = FakeApiClient()
    async with make_avatar(api) as session:
        await session.start(FakeAgentSession(), room=FakeRoom())
    assert api.stops == ["server-id"]
