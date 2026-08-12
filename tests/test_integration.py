import pytest
from fakes import FakeAgentSession, FakeApiClient, FakeRoom
from test_avatar_lifecycle import make_avatar


@pytest.mark.asyncio
async def test_start_bridge_and_stop_integration():
    api, room, agent = FakeApiClient(), FakeRoom(), FakeAgentSession()
    avatar = make_avatar(api)
    await avatar.start(agent, room=room, session_id="old-id")
    assert api.starts[0]["session_id"] == "old-id"
    await avatar.stop()
    assert api.stops == ["server-id"]
