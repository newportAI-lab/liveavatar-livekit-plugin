from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from livekit.plugins.facemarket.api import ApiClient
from livekit.plugins.facemarket.errors import APIError, SessionStartError


def response(payload):
    result = MagicMock()
    result.json.return_value = payload
    return result


@pytest.fixture
def api_and_http():
    http = MagicMock()
    http.post = AsyncMock()
    http.aclose = AsyncMock()
    return ApiClient(api_key="key-1", base_url="https://api.example/", client=http), http


@pytest.mark.asyncio
async def test_new_start_omits_session_id(api_and_http):
    api, http = api_and_http
    http.post.return_value = response({"code": 0, "data": {"sessionId": "new-id"}})

    info = await api.start_session(
        avatar_id="avatar-1",
        agent_identity="agent-1",
        sfu_url="wss://lk",
        renderer_token="jwt",
    )

    assert info.session_id == "new-id"
    assert http.post.call_args.kwargs["json"] == {
        "avatarId": "avatar-1",
        "mode": "rtcAgent",
        "agentIdentity": "agent-1",
        "sfuUrl": "wss://lk",
        "rendererToken": "jwt",
    }


@pytest.mark.asyncio
async def test_start_includes_requested_session_id_and_uses_response_id(api_and_http):
    api, http = api_and_http
    http.post.return_value = response({"code": 0, "data": {"sessionId": "authoritative-id"}})

    info = await api.start_session(
        avatar_id="avatar-1",
        agent_identity="agent-1",
        sfu_url="wss://lk",
        renderer_token="jwt",
        session_id="requested-id",
    )

    assert info.session_id == "authoritative-id"
    assert http.post.call_args.kwargs["json"]["sessionId"] == "requested-id"


@pytest.mark.asyncio
async def test_requests_use_expected_paths_and_headers(api_and_http):
    api, http = api_and_http
    http.post.return_value = response({"code": 0, "data": {"sessionId": "new-id"}})

    await api.start_session(
        avatar_id="avatar-1",
        agent_identity="agent-1",
        sfu_url="wss://lk",
        renderer_token="jwt",
    )
    await api.stop_session("new-id")

    start_call, stop_call = http.post.call_args_list
    assert start_call.args[0] == "https://api.example/v1/session/start"
    assert stop_call.args[0] == "https://api.example/v1/session/stop"
    assert start_call.kwargs["headers"] == {
        "Authorization": "Bearer key-1",
        "Content-Type": "application/json",
    }
    assert stop_call.kwargs["json"] == {"sessionId": "new-id"}


@pytest.mark.asyncio
async def test_sandbox_requests_include_sandbox_header(api_and_http):
    _, http = api_and_http
    api = ApiClient(api_key="key-1", base_url="https://api.example", sandbox=True, client=http)
    http.post.return_value = response({"code": 0, "data": {"sessionId": "new-id"}})

    await api.start_session(
        avatar_id="avatar-1",
        agent_identity="agent-1",
        sfu_url="wss://lk",
        renderer_token="jwt",
    )

    assert http.post.call_args.kwargs["headers"]["X-Env-Sandbox"] == "true"


@pytest.mark.asyncio
async def test_nonzero_response_code_raises_api_error(api_and_http):
    api, http = api_and_http
    http.post.return_value = response({"code": 1001, "message": "avatar not found"})

    with pytest.raises(APIError, match="1001") as error:
        await api.stop_session("session-1")

    assert error.value.code == 1001
    assert error.value.message == "avatar not found"


@pytest.mark.asyncio
async def test_start_without_response_session_id_raises_start_error(api_and_http):
    api, http = api_and_http
    http.post.return_value = response({"code": 0, "message": "success", "data": {}})

    with pytest.raises(SessionStartError):
        await api.start_session(
            avatar_id="avatar-1",
            agent_identity="agent-1",
            sfu_url="wss://lk",
            renderer_token="jwt",
        )


@pytest.mark.asyncio
async def test_http_status_and_timeout_errors_are_preserved(api_and_http):
    api, http = api_and_http
    status_error = httpx.HTTPStatusError("bad status", request=MagicMock(), response=MagicMock())
    http.post.side_effect = status_error

    with pytest.raises(httpx.HTTPStatusError) as received_status_error:
        await api.stop_session("session-1")

    assert received_status_error.value is status_error
    timeout_error = httpx.ReadTimeout("timed out")
    http.post.side_effect = timeout_error

    with pytest.raises(httpx.ReadTimeout) as received_timeout_error:
        await api.stop_session("session-1")

    assert received_timeout_error.value is timeout_error


@pytest.mark.asyncio
async def test_injected_client_is_not_closed_and_aclose_is_idempotent(api_and_http):
    api, http = api_and_http

    await api.aclose()
    await api.aclose()

    http.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_owned_client_is_closed_once(monkeypatch):
    http = MagicMock()
    http.aclose = AsyncMock()
    monkeypatch.setattr("livekit.plugins.facemarket.api.httpx.AsyncClient", lambda timeout: http)
    api = ApiClient(api_key="key-1", base_url="https://api.example")

    await api.aclose()
    await api.aclose()

    http.aclose.assert_awaited_once()
