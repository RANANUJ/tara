"""M9D authenticated WebSocket agent-event coverage."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient


def _bootstrap(client: TestClient) -> tuple[dict[str, str], str]:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "owner@example.test", "password": "correct-horse-battery-staple"},
    )
    body = response.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["session_id"]


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


def _ticket(client: TestClient, headers: dict[str, str]) -> str:
    return client.post("/api/v1/ws/tickets", headers=headers).json()["ticket"]


def test_direct_agent_request_emits_ordered_sanitized_terminal_events(client: TestClient) -> None:
    headers, session_id = _bootstrap(client)
    with client.websocket_connect(f"/api/v1/ws/session?ticket={_ticket(client, headers)}") as websocket:
        websocket.send_json(_event(session_id, 0, "session.hello"))
        assert websocket.receive_json()["type"] == "session.accepted"
        websocket.send_json(_event(session_id, 1, "agent.request", {"text": "hello", "idempotency_key": "request-1"}))

        events = [websocket.receive_json() for _ in range(5)]

    assert [event["type"] for event in events] == [
        "agent.started",
        "agent.state",
        "agent.state",
        "agent.state",
        "agent.error",
    ]
    assert events[1]["payload"]["state"] == "queued"
    assert events[-2]["payload"]["state"] == "failed"
    assert events[-1]["payload"]["code"] == "provider_not_configured"


def test_invalid_agent_payload_is_rejected_without_closing_the_connection(client: TestClient) -> None:
    headers, session_id = _bootstrap(client)
    with client.websocket_connect(f"/api/v1/ws/session?ticket={_ticket(client, headers)}") as websocket:
        websocket.send_json(_event(session_id, 0, "session.hello"))
        websocket.receive_json()
        websocket.send_json(_event(session_id, 1, "agent.request", {"text": "hello", "idempotency_key": "request-1", "unexpected": True}))
        error = websocket.receive_json()
        assert error["type"] == "agent.error"
        assert "traceback" not in str(error).lower()

        websocket.send_json(_event(session_id, 2, "session.ping"))
        assert websocket.receive_json()["type"] == "session.pong"
