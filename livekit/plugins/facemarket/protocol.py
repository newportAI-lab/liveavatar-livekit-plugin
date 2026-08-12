import json
from dataclasses import dataclass
from typing import Any

from .errors import DataChannelProtocolError

SCENE_READY = "scene.ready"
SCENE_RESOURCE_TRANSITION = "scene.resourceTransition"
SESSION_STATE = "session.state"
SESSION_CLOSING = "session.closing"
IDLE_TRIGGER = "system.idleTrigger"
ERROR = "error"
CUSTOM_EVENT = "custom_event"
PROTOCOL_ERROR = "protocol_error"
SESSION_READY = "session_ready"

_KNOWN_EVENTS = {
    SCENE_READY,
    SCENE_RESOURCE_TRANSITION,
    SESSION_STATE,
    SESSION_CLOSING,
    IDLE_TRIGGER,
    ERROR,
}


@dataclass(frozen=True)
class DataChannelEvent:
    event: str
    data: Any = None
    request_id: str | None = None
    response_id: str | None = None
    seq: int | None = None
    timestamp: int | None = None
    participant_identity: str | None = None
    topic: str | None = None


def encode_event(event: DataChannelEvent) -> bytes:
    payload: dict[str, Any] = {"event": event.event}
    fields = {
        "data": event.data,
        "requestId": event.request_id,
        "responseId": event.response_id,
        "seq": event.seq,
        "timestamp": event.timestamp,
    }
    payload.update({key: value for key, value in fields.items() if value is not None})
    return json.dumps(payload, separators=(",", ":")).encode()


def decode_event(
    data: bytes, *, participant_identity: str | None = None, topic: str | None = None
) -> DataChannelEvent:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DataChannelProtocolError("invalid JSON Data Channel payload") from error

    if not isinstance(payload, dict) or not isinstance(payload.get("event"), str):
        raise DataChannelProtocolError("Data Channel event must be an object with a string event")

    _validate_common_fields(payload)
    _validate_known_event(payload)
    return DataChannelEvent(
        event=payload["event"],
        data=payload.get("data"),
        request_id=payload.get("requestId"),
        response_id=payload.get("responseId"),
        seq=payload.get("seq"),
        timestamp=payload.get("timestamp"),
        participant_identity=participant_identity,
        topic=topic,
    )


def _validate_common_fields(payload: dict[str, Any]) -> None:
    for field in ("requestId", "responseId"):
        if field in payload and payload[field] is not None and not isinstance(payload[field], str):
            raise DataChannelProtocolError(f"{field} must be a string")
    for field in ("seq", "timestamp"):
        if field in payload and (
            isinstance(payload[field], bool) or not isinstance(payload[field], int)
        ):
            raise DataChannelProtocolError(f"{field} must be an integer")


def _validate_known_event(payload: dict[str, Any]) -> None:
    event = payload["event"]
    if event not in _KNOWN_EVENTS:
        return

    event_data = payload.get("data")
    if not isinstance(event_data, dict):
        raise DataChannelProtocolError(f"{event} data must be an object")
    if event == SESSION_STATE and not isinstance(event_data.get("state"), str):
        raise DataChannelProtocolError("session.state data.state must be a string")
    if event == SCENE_RESOURCE_TRANSITION:
        for field in ("previousResourceId", "nextResourceId"):
            if not isinstance(event_data.get(field), str) or not event_data[field].strip():
                raise DataChannelProtocolError(
                    f"scene.resourceTransition {field} must be non-empty"
                )
        if "message" in event_data and not isinstance(event_data["message"], str):
            raise DataChannelProtocolError("scene.resourceTransition message must be a string")
    if event == ERROR and not isinstance(event_data.get("message"), str):
        raise DataChannelProtocolError("error data.message must be a string")
