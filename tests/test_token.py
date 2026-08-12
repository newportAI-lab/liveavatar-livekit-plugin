import base64
import json
from datetime import timedelta

import pytest
from livekit.api import TokenVerifier

from livekit.plugins.facemarket.errors import ConfigurationError
from livekit.plugins.facemarket.token import create_renderer_token


def test_renderer_claims_and_ttl():
    ttl = timedelta(hours=4, minutes=30)
    secret = "secret-secret-secret-secret-secret-12"
    result = create_renderer_token(
        api_key="key",
        api_secret=secret,
        room_name="room-1",
        agent_identity="agent-1",
        ttl=ttl,
        identity_factory=lambda: "renderer-fixed",
    )

    claims = TokenVerifier("key", secret).verify(result.token)
    payload = _jwt_payload(result.token)
    assert result.identity == "renderer-fixed"
    assert claims.identity == "renderer-fixed"
    assert payload["kind"] == "agent"
    assert claims.attributes == {"lk.publish_on_behalf": "agent-1"}
    assert claims.video.room == "room-1"
    assert claims.video.room_join and claims.video.can_publish
    assert claims.video.can_subscribe and claims.video.can_publish_data
    assert abs((payload["exp"] - payload["nbf"]) - ttl.total_seconds()) <= 5


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("api_key", ""),
        ("api_secret", ""),
        ("room_name", ""),
        ("agent_identity", ""),
    ],
)
def test_blank_required_input_raises_configuration_error(field, value):
    arguments = {
        "api_key": "key",
        "api_secret": "secret",
        "room_name": "room-1",
        "agent_identity": "agent-1",
        "ttl": timedelta(minutes=1),
        "identity_factory": lambda: "renderer-fixed",
    }
    arguments[field] = value

    with pytest.raises(ConfigurationError):
        create_renderer_token(**arguments)


def _jwt_payload(token):
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
