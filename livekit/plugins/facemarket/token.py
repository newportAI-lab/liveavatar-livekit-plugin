from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from livekit.api import AccessToken, VideoGrants

from .errors import ConfigurationError


@dataclass(frozen=True)
class RendererToken:
    token: str
    identity: str


def create_renderer_token(
    *,
    api_key: str,
    api_secret: str,
    room_name: str,
    agent_identity: str,
    ttl: timedelta,
    identity_factory: Callable[[], str] | None = None,
) -> RendererToken:
    _validate_required("api_key", api_key)
    _validate_required("api_secret", api_secret)
    _validate_required("room_name", room_name)
    _validate_required("agent_identity", agent_identity)

    identity = identity_factory() if identity_factory else f"renderer_{uuid4()}"
    _validate_required("renderer identity", identity)
    token = (
        AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_ttl(ttl)
        .with_kind("agent")
        .with_attributes({"lk.publish_on_behalf": agent_identity})
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )
    return RendererToken(token=token, identity=identity)


def _validate_required(name: str, value: str) -> None:
    if not value.strip():
        raise ConfigurationError(f"{name} must not be blank")
