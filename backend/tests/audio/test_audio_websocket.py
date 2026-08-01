"""M7 WebSocket audio lifecycle integration tests."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from tara_api.domain.audio import AudioFrame
from tara_api.transport.audio import CANONICAL_FORMAT, encode_frame


def _bootstrap(client: TestClient) -> tuple[dict[str, str], str]:
    response = client.post("/api/v1/auth/bootstrap", json={"email": "owner@example.test", "password": "correct-horse-battery-staple"}).json()
    return {"Authorization": f"Bearer {response['token']}"}, response["session_id"]


def _ticket(client: TestClient, headers: dict[str, str]) -> str:
    return client.post("/api/v1/ws/tickets", headers=headers).json()["ticket"]


def _event(session_id: str, sequence: int, event_type: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "event_id": str(uuid4()),
        "session_id": session_id,
        "sequence": sequence,
        "timestamp": datetime.now(UTC).isoformat(),
        "type": event_type,
        "payload": payload or {},
    }


def _start_audio(websocket: object, session_id: str, audio_session_id: str) -> None:
    websocket.send_json(_event(session_id, 0, "session.hello"))  # type: ignore[attr-defined]
    assert websocket.receive_json()["type"] == "session.accepted"  # type: ignore[attr-defined]
    websocket.send_json(_event(session_id, 1, "audio.session.start", {"audio_session_id": audio_session_id}))  # type: ignore[attr-defined]
    assert websocket.receive_json()["type"] == "audio.session.accepted"  # type: ignore[attr-defined]
    websocket.send_json(_event(session_id, 2, "audio.format", {"sample_rate": 16000, "sample_width_bytes": 2, "channels": 1, "frame_ms": 20}))  # type: ignore[attr-defined]


def test_binary_before_audio_start_is_rejected(client: TestClient) -> None:
    headers, session_id = _bootstrap(client)
    with client.websocket_connect(f"/api/v1/ws/session?ticket={_ticket(client, headers)}") as websocket:
        websocket.send_json(_event(session_id, 0, "session.hello"))
        websocket.receive_json()
        websocket.send_bytes(b"TAR1")
        error = websocket.receive_json()
        assert error["type"] == "session.error"
        assert "TAR1" not in str(error)


def test_audio_lifecycle_flush_and_ping_have_monotonic_server_events(client: TestClient) -> None:
    headers, session_id = _bootstrap(client)
    audio_session_id = str(uuid4())
    with client.websocket_connect(f"/api/v1/ws/session?ticket={_ticket(client, headers)}") as websocket:
        _start_audio(websocket, session_id, audio_session_id)
        websocket.send_json(_event(session_id, 3, "session.ping"))
        pong = websocket.receive_json()
        assert pong["type"] == "session.pong"
        websocket.send_json(_event(session_id, 4, "audio.flush"))
        completed = websocket.receive_json()
        stopped = websocket.receive_json()
        assert [completed["type"], stopped["type"]] == ["vad.turn.completed", "audio.session.stopped"]
        assert completed["sequence"] < stopped["sequence"]


def test_audio_level_is_throttled_and_stop_disables_frames(client: TestClient) -> None:
    headers, session_id = _bootstrap(client)
    audio_session_id = str(uuid4())
    with client.websocket_connect(f"/api/v1/ws/session?ticket={_ticket(client, headers)}") as websocket:
        _start_audio(websocket, session_id, audio_session_id)
        payload = bytes(CANONICAL_FORMAT.frame_bytes)
        for sequence in range(5):
            websocket.send_bytes(encode_frame(AudioFrame(UUID(audio_session_id), sequence, payload)))
        level = websocket.receive_json()
        assert level["type"] == "audio.level"
        assert 0 <= level["payload"]["level"] <= 1
        websocket.send_json(_event(session_id, 3, "audio.session.stop"))
        assert websocket.receive_json()["type"] == "vad.turn.completed"
        assert websocket.receive_json()["type"] == "audio.session.stopped"
        websocket.send_bytes(encode_frame(AudioFrame(UUID(audio_session_id), 5, payload)))
        assert websocket.receive_json()["type"] == "session.error"


def test_invalid_negotiation_and_second_active_session_are_rejected(client: TestClient) -> None:
    headers, session_id = _bootstrap(client)
    with client.websocket_connect(f"/api/v1/ws/session?ticket={_ticket(client, headers)}") as websocket:
        websocket.send_json(_event(session_id, 0, "session.hello"))
        websocket.receive_json()
        websocket.send_json(_event(session_id, 1, "audio.session.start", {"audio_session_id": str(uuid4())}))
        websocket.receive_json()
        websocket.send_json(_event(session_id, 2, "audio.format", {"sample_rate": 48000}))
        assert websocket.receive_json()["type"] == "session.error"
