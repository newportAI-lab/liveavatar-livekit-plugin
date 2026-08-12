import pytest

from livekit.plugins.facemarket.errors import DataChannelProtocolError
from livekit.plugins.facemarket.protocol import (
    ERROR,
    IDLE_TRIGGER,
    SCENE_READY,
    SCENE_RESOURCE_TRANSITION,
    SESSION_CLOSING,
    SESSION_STATE,
    DataChannelEvent,
    decode_event,
    encode_event,
)


def test_round_trip_preserves_envelope_metadata():
    original = DataChannelEvent(
        event="input.asr.partial",
        data={"text": "hel"},
        request_id="req-1",
        seq=0,
        timestamp=123,
    )

    assert decode_event(encode_event(original)) == original


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b"[]",
        b'{"event": 1}',
        b'{"event":"session.state","data":{}}',
        b'{"event":"error","data":{"message":1}}',
    ],
)
def test_invalid_packet_raises_protocol_error(payload):
    with pytest.raises(DataChannelProtocolError):
        decode_event(payload)


@pytest.mark.parametrize(
    ("event", "data"),
    [
        (SCENE_READY, {}),
        (
            SCENE_RESOURCE_TRANSITION,
            {"previousResourceId": "previous", "nextResourceId": "next", "message": "loading"},
        ),
        (SESSION_STATE, {"state": "connected"}),
        (SESSION_CLOSING, {}),
        (IDLE_TRIGGER, {}),
        (ERROR, {"message": "renderer failed"}),
    ],
)
def test_known_events_accept_valid_object_data(event, data):
    assert decode_event(encode_event(DataChannelEvent(event=event, data=data))).event == event


@pytest.mark.parametrize(
    "payload",
    [
        b'{"event":"scene.resourceTransition","data":{"nextResourceId":"next"}}',
        b'{"event":"scene.resourceTransition","data":{"previousResourceId":"previous"}}',
        b'{"event":"scene.resourceTransition","data":{"previousResourceId":"","nextResourceId":"next"}}',
        b'{"event":"scene.resourceTransition","data":{"previousResourceId":"   ","nextResourceId":"next"}}',
        b'{"event":"scene.resourceTransition","data":{"previousResourceId":"previous","nextResourceId":"\\t"}}',
        b'{"event":"scene.resourceTransition","data":{"previousResourceId":"previous","nextResourceId":"next","message":1}}',
    ],
)
def test_resource_transition_requires_non_empty_ids_and_string_message(payload):
    with pytest.raises(DataChannelProtocolError):
        decode_event(payload)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"event":"custom","seq":true}',
        b'{"event":"custom","timestamp":false}',
        b'{"event":"custom","seq":"0"}',
        b'{"event":"custom","timestamp":"123"}',
    ],
)
def test_sequence_and_timestamp_must_be_non_boolean_integers(payload):
    with pytest.raises(DataChannelProtocolError):
        decode_event(payload)


def test_explicit_null_correlation_ids_are_accepted_as_absent():
    event = decode_event(b'{"event":"custom","requestId":null,"responseId":null}')

    assert event.request_id is None
    assert event.response_id is None


def test_unknown_event_and_transport_metadata_are_preserved():
    event = decode_event(
        b'{"event":"input.asr.partial","data":{"text":"hel"},"responseId":"res-1"}',
        participant_identity="renderer-1",
        topic="facemarket",
    )

    assert event.event == "input.asr.partial"
    assert event.data == {"text": "hel"}
    assert event.response_id == "res-1"
    assert event.participant_identity == "renderer-1"
    assert event.topic == "facemarket"
