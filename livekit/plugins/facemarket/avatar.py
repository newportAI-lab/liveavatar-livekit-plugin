import asyncio
import os
from datetime import timedelta
from enum import Enum
from types import TracebackType
from typing import Any

from .agent_bridge import AgentSessionBridge
from .api import ApiClient
from .errors import ConfigurationError, SessionAlreadyStartedError, SessionStoppedError
from .events import EventDispatcher
from .protocol import (
    CUSTOM_EVENT,
    IDLE_TRIGGER,
    PROTOCOL_ERROR,
    SCENE_READY,
    SESSION_READY,
    DataChannelEvent,
    decode_event,
    encode_event,
)
from .token import create_renderer_token


class _State(Enum):
    NEW = "new"
    STARTING = "starting"
    ACTIVE = "active"
    STOPPING = "stopping"
    STOPPED = "stopped"


class AvatarSession:
    def __init__(
        self,
        avatar_id: str,
        api_key: str | None = None,
        base_url: str | None = None,
        livekit_url: str | None = None,
        livekit_api_key: str | None = None,
        livekit_api_secret: str | None = None,
        sandbox: bool = False,
        renderer_token_ttl: timedelta = timedelta(hours=4, minutes=30),
        *,
        api_client: Any | None = None,
        token_factory: Any = create_renderer_token,
    ) -> None:
        self._avatar_id = avatar_id
        self._api_key = _configured_value(api_key, "FACEMARKET_API_KEY")
        self._base_url = _configured_value(
            base_url,
            "FACEMARKET_BASE_URL",
            "https://facemarket.ai/vih/dispatcher",
        )
        self._livekit_url = _configured_value(livekit_url, "LIVEKIT_URL")
        self._livekit_api_key = _configured_value(livekit_api_key, "LIVEKIT_API_KEY")
        self._livekit_api_secret = _configured_value(livekit_api_secret, "LIVEKIT_API_SECRET")
        self._sandbox = sandbox
        self._renderer_token_ttl = renderer_token_ttl
        self._api_client = api_client
        self._owns_api_client = api_client is None
        self._token_factory = token_factory
        self._events = EventDispatcher()
        self._lock = asyncio.Lock()
        self._state = _State.NEW
        self._session_id: str | None = None
        self._start_args: tuple[Any, Any, str | None] | None = None
        self._bridge: AgentSessionBridge | None = None
        self._room: Any | None = None
        self._room_callbacks = {
            "data_received": self._on_data_received,
            "disconnected": self._on_disconnected,
        }
        self._tasks: set[asyncio.Task[Any]] = set()
        self._stop_task: asyncio.Task[None] | None = None
        self._start_complete: asyncio.Future[bool] | None = None
        self._ready_seen = False
        self._listeners_installed = False
        self._remote_stop_succeeded = False

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def on(self, event: str):
        return self._events.on(event)

    async def start(self, agent_session: Any, *, room: Any, session_id: str | None = None) -> None:
        async with self._lock:
            if self._state is _State.STOPPED:
                raise SessionStoppedError("AvatarSession has stopped")
            if self._state is _State.ACTIVE:
                if self._start_args == (agent_session, room, session_id):
                    return
                raise SessionAlreadyStartedError("AvatarSession already started")
            if self._state is not _State.NEW:
                raise SessionAlreadyStartedError("AvatarSession is already starting or stopping")
            self._validate(agent_session, room)
            self._state = _State.STARTING
            self._start_complete = asyncio.get_running_loop().create_future()
            self._room = room
            self._start_args = (agent_session, room, session_id)
            if self._api_client is None:
                self._api_client = ApiClient(self._api_key, self._base_url, self._sandbox)
            self._bridge = AgentSessionBridge(agent_session, self._publish)
            self._install_listeners()
        try:
            token = self._token_factory(
                api_key=self._livekit_api_key,
                api_secret=self._livekit_api_secret,
                room_name=room.name,
                agent_identity=room.local_participant.identity,
                ttl=self._renderer_token_ttl,
            )
            result = await self._api_client.start_session(
                avatar_id=self._avatar_id,
                agent_identity=room.local_participant.identity,
                sfu_url=self._livekit_url,
                renderer_token=token.token,
                session_id=session_id,
            )
        except BaseException:
            async with self._lock:
                self._complete_start(False)
                if self._state is not _State.STOPPING:
                    await self._cleanup_failed_start()
            raise
        async with self._lock:
            self._session_id = result.session_id
            if self._state is _State.STARTING:
                self._state = _State.ACTIVE
            self._complete_start(True)

    async def stop(self) -> None:
        async with self._lock:
            if self._state is _State.STOPPED:
                return
            if self._stop_task is None:
                self._state = _State.STOPPING
                self._stop_task = asyncio.create_task(self._stop_impl())
            task = self._stop_task
        try:
            await asyncio.shield(task)
        except BaseException:
            async with self._lock:
                if task.done() and self._stop_task is task:
                    self._stop_task = None
            raise

    async def interrupt(self, request_id: str | None = None) -> None:
        if self._state is _State.STOPPED:
            raise SessionStoppedError("AvatarSession has stopped")
        self._publish(DataChannelEvent(event="control.interrupt", request_id=request_id))

    async def __aenter__(self) -> "AvatarSession":  # noqa: PYI034 - Python 3.10 lacks Self.
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.stop()

    def _validate(self, agent_session: Any, room: Any) -> None:
        for name, value in (
            ("avatar_id", self._avatar_id),
            ("api_key", self._api_key),
            ("base_url", self._base_url),
            ("livekit_url", self._livekit_url),
            ("livekit_api_key", self._livekit_api_key),
            ("livekit_api_secret", self._livekit_api_secret),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ConfigurationError(f"{name} must not be blank")
        if self._renderer_token_ttl.total_seconds() <= 0:
            raise ConfigurationError("renderer_token_ttl must be positive")
        if not room.isconnected() or not room.name:
            raise ConfigurationError("room must be connected with a name")
        if not room.local_participant.identity.strip():
            raise ConfigurationError("room local participant identity is required")

    def _install_listeners(self) -> None:
        for name, callback in self._room_callbacks.items():
            self._room.on(name, callback)
        self._bridge.install()
        self._listeners_installed = True

    def _uninstall_listeners(self) -> None:
        if not self._listeners_installed:
            return
        if self._room is not None:
            for name, callback in self._room_callbacks.items():
                self._room.off(name, callback)
        if self._bridge is not None:
            self._bridge.uninstall()
        self._listeners_installed = False

    async def _cleanup_failed_start(self) -> None:
        self._uninstall_listeners()
        await self._cancel_tasks()
        if self._owns_api_client and self._api_client is not None:
            await self._api_client.aclose()
            self._api_client = None
        self._bridge = None
        self._room = None
        self._start_args = None
        self._state = _State.NEW

    async def _stop_impl(self) -> None:
        start_complete = self._start_complete if self._state is _State.STOPPING else None
        if start_complete is not None:
            await start_complete
        if not self._remote_stop_succeeded and self._session_id is not None:
            await self._api_client.stop_session(self._session_id)
            self._remote_stop_succeeded = True
        self._uninstall_listeners()
        if self._bridge is not None:
            self._bridge.reset()
        await self._cancel_tasks()
        if self._owns_api_client and self._api_client is not None:
            await self._api_client.aclose()
        async with self._lock:
            self._state = _State.STOPPED

    def _complete_start(self, succeeded: bool) -> None:
        if self._start_complete is not None and not self._start_complete.done():
            self._start_complete.set_result(succeeded)

    def _on_data_received(self, packet: Any) -> None:
        participant = getattr(packet, "participant", None)
        try:
            event = decode_event(
                packet.data,
                participant_identity=getattr(participant, "identity", None),
                topic=getattr(packet, "topic", None),
            )
        except Exception as error:  # noqa: BLE001 - malformed external RTC packets are isolated.
            self._track(self._events.dispatch(PROTOCOL_ERROR, error))
            return
        if event.event == SCENE_READY:
            if not self._ready_seen:
                self._ready_seen = True
                self._track(self._events.dispatch(SESSION_READY, event))
        elif event.event == IDLE_TRIGGER:
            if self._bridge is not None:
                self._bridge.arm_prompt()
            self._track(self._events.dispatch(event.event, event))
        elif event.event in {
            "scene.resourceTransition",
            "session.state",
            "session.closing",
            "error",
        }:
            self._track(self._events.dispatch(event.event, event))
        else:
            self._track(self._events.dispatch(CUSTOM_EVENT, event))

    def _on_disconnected(self) -> None:
        if self._bridge is not None:
            self._bridge.reset()

    def _publish(self, event: DataChannelEvent) -> asyncio.Task[Any]:
        return self._track(self._publish_impl(event))

    async def _publish_impl(self, event: DataChannelEvent) -> bool:
        try:
            await self._room.local_participant.publish_data(encode_event(event), reliable=True)
        except Exception as error:  # noqa: BLE001 - publishing errors become local callbacks.
            await self._events.dispatch(
                "error", DataChannelEvent(event="error", data={"error": str(error)})
            )
            return False
        return True

    def _track(self, coroutine: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _cancel_tasks(self) -> None:
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def _configured_value(
    value: str | None, environment: str, default: str | None = None
) -> str | None:
    if value is not None:
        return value
    return os.getenv(environment, default)
