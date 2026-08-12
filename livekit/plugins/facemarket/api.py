from dataclasses import dataclass

import httpx

from .errors import APIError, SessionStartError


@dataclass(frozen=True)
class SessionInfo:
    session_id: str


class ApiClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        sandbox: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if sandbox:
            self._headers["X-Env-Sandbox"] = "true"
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        self._closed = False

    async def start_session(
        self,
        *,
        avatar_id: str,
        agent_identity: str,
        sfu_url: str,
        renderer_token: str,
        session_id: str | None = None,
    ) -> SessionInfo:
        payload = {
            "avatarId": avatar_id,
            "mode": "rtcAgent",
            "agentIdentity": agent_identity,
            "sfuUrl": sfu_url,
            "rendererToken": renderer_token,
        }
        if session_id is not None:
            payload["sessionId"] = session_id
        response = await self._post("/v1/session/start", payload)
        result = self._response_body(response)
        response_session_id = result.get("data", {}).get("sessionId")
        if not isinstance(response_session_id, str) or not response_session_id:
            raise SessionStartError(0, "missing data.sessionId")
        return SessionInfo(session_id=response_session_id)

    async def stop_session(self, session_id: str) -> None:
        response = await self._post("/v1/session/stop", {"sessionId": session_id})
        self._response_body(response)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            await self._client.aclose()

    async def _post(self, path: str, payload: dict[str, str]) -> httpx.Response:
        response = await self._client.post(
            f"{self._base_url}{path}", json=payload, headers=self._headers
        )
        response.raise_for_status()
        return response

    @staticmethod
    def _response_body(response: httpx.Response) -> dict[object, object]:
        payload = response.json()
        if not isinstance(payload, dict):
            raise APIError(-1, "invalid response")
        code = payload.get("code")
        message = payload.get("message", "")
        if code != 0:
            raise APIError(code if isinstance(code, int) else -1, str(message))
        return payload
