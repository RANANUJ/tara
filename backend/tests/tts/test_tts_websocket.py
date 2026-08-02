"""M10C authenticated TTS delivery with deterministic fake providers only."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from tara_api.config.settings import Settings
from tara_api.main import create_app


def _event(session_id: str, sequence: int, event_type: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    return {"protocol_version": 1, "event_id": str(uuid4()), "session_id": session_id, "sequence": sequence, "timestamp": datetime.now(UTC).isoformat(), "type": event_type, "payload": payload or {}}


def _client(database, database_url: str) -> TestClient:  # type: ignore[no-untyped-def]
    settings = Settings(_env_file=None, environment="test", service_secret="test-secret", database_url=database_url, llm_provider="fake", tts_provider="fake")
    return TestClient(create_app(settings, database))


def _bootstrap(client: TestClient) -> tuple[dict[str, str], str]:
    login = client.post("/api/v1/auth/bootstrap", json={"email": "owner@example.test", "password": "correct-horse-battery-staple"}).json()
    return {"Authorization": f"Bearer {login['token']}"}, login["session_id"]


def test_completed_agent_response_delivers_one_ordered_tts_stream(database, database_url: str) -> None:
    with _client(database, database_url) as client:
        headers, session_id = _bootstrap(client)
        ticket = client.post("/api/v1/ws/tickets", headers=headers).json()["ticket"]
        with client.websocket_connect(f"/api/v1/ws/session?ticket={ticket}") as websocket:
            websocket.send_json(_event(session_id, 0, "session.hello"))
            websocket.receive_json()
            websocket.send_json(_event(session_id, 1, "agent.request", {"text": "hello", "idempotency_key": "tts-one"}))
            events = [websocket.receive_json() for _ in range(17)]

    types = [event["type"] for event in events]
    assert "agent.response" in types
    assert types.count("tts.started") == 1
    assert types.count("tts.audio.start") == 1
    assert types.count("tts.audio.end") == 1, types
    chunks = [event["payload"] for event in events if event["type"] == "tts.audio.chunk"]
    assert [item["sequence"] for item in chunks] == list(range(len(chunks)))
    assert sum(item["final"] for item in chunks) == 1
    assert all("audio_base64" not in str(event) for event in events if event["type"] != "tts.audio.chunk")


def test_tts_cancel_rejects_unknown_request_without_identity_leak(database, database_url: str) -> None:
    with _client(database, database_url) as client:
        headers, session_id = _bootstrap(client)
        ticket = client.post("/api/v1/ws/tickets", headers=headers).json()["ticket"]
        with client.websocket_connect(f"/api/v1/ws/session?ticket={ticket}") as websocket:
            websocket.send_json(_event(session_id, 0, "session.hello"))
            websocket.receive_json()
            websocket.send_json(_event(session_id, 1, "tts.cancel", {"synthesis_request_id": str(uuid4())}))
            error = websocket.receive_json()

    assert error["type"] == "tts.error"
    assert "owner" not in str(error["payload"]).lower()
