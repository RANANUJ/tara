"""WebSocket task transport tests for M16 (Part C)."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from tara_api.auth.rate_limit import InMemoryLoginRateLimiter
from tara_api.auth.security import Argon2idPasswordHasher, SecureSessionTokenGenerator
from tara_api.auth.service import AuthenticationService
from tara_api.capabilities.filesystem import AllowlistedFilesystemListTool
from tara_api.capabilities.registry import CapabilityRegistry
from tara_api.domain.models import ActionRiskLevel, JsonValue, PermissionScope, ToolDefinition, ToolRequest, ToolResult, ToolResultStatus
from tara_api.main import create_app
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore
from tara_api.persistence.database import Database
from tara_api.tasks.payloads import TaskPayloadProtector
from tara_api.tasks.service import ScheduledTaskService


class _ConsequentialWsTool:
    definition = ToolDefinition(
        "fake.ws.action",
        "1",
        PermissionScope("fake.ws.action"),
        ActionRiskLevel.OUTWARD_FACING,
        "perform outward ws action",
    )

    def validate_arguments(self, arguments: Mapping[str, JsonValue]) -> dict[str, object]:
        return dict(arguments)

    async def execute(self, _request: ToolRequest, _validated_arguments: dict[str, object]) -> ToolResult:
        return ToolResult(ToolResultStatus.SUCCEEDED, "ok")


@pytest.fixture
def ws_app_client(database: Database, tmp_path: Path) -> tuple[TestClient, str]:
    app = create_app(database=database)
    tmp_path.mkdir(parents=True, exist_ok=True)
    protector = TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    fs_tool = AllowlistedFilesystemListTool((tmp_path,))
    app.state.task_payload_protector = protector
    app.state.capability_registry = CapabilityRegistry(
        fs_tool,
        additional_tools=(_ConsequentialWsTool(),),
    )
    app.state.scheduled_task_service = ScheduledTaskService(
        app.state.database,
        app.state.capability_registry,
        app.state.action_policy,
        app.state.confirmation_service,
        protector,
    )
    client = TestClient(app, raise_server_exceptions=True)
    return client, str(tmp_path)


async def _mint_ticket(database: Database, email: str = "owner@example.test") -> tuple[str, AuthenticationService, UUID]:
    store = SqlAlchemyAuthenticationStore(database)
    auth = AuthenticationService(
        store,
        store,
        Argon2idPasswordHasher(),
        SecureSessionTokenGenerator(),
        InMemoryLoginRateLimiter(),
        lambda: datetime.now(UTC),
        timedelta(hours=1),
        timedelta(hours=1),
    )
    await auth.bootstrap(email, "safe-password")
    _owner, session, token = await auth.login(email, "safe-password")
    return token, auth, session.id


@pytest.mark.asyncio
async def test_websocket_task_commands_lifecycle(database: Database, ws_app_client: tuple[TestClient, str]) -> None:
    client, tmp_dir = ws_app_client
    token, auth, session_id = await _mint_ticket(database)

    # 1. Acquire ticket via auth API
    res = client.post("/api/v1/ws/tickets", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 201
    ticket = res.json()["ticket"]

    # 2. Connect WebSocket
    with client.websocket_connect(f"/api/v1/ws/session?ticket={ticket}") as ws:
        # Hello handshake
        session_id_str = str(session_id)
        ws.send_json({
            "protocol_version": 1,
            "event_id": str(uuid4()),
            "session_id": session_id_str,
            "sequence": 0,
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "session.hello",
            "payload": {},
        })
        accepted = ws.receive_json()
        assert accepted["type"] == "session.accepted"

        # Create read-only task
        run_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        ws.send_json({
            "protocol_version": 1,
            "event_id": str(uuid4()),
            "session_id": str(session_id),
            "sequence": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "task.create",
            "payload": {
                "title": "WS Task",
                "instruction": "WS Instruction",
                "capability_id": "filesystem.list",
                "target": ".",
                "parameters": {},
                "schedule": {"timezone": "UTC", "run_at": run_at},
                "idempotency_key": "ws-key-1",
            },
        })
        created_event = ws.receive_json()
        assert created_event["type"] == "task.created"
        task_id = created_event["payload"]["id"]
        assert created_event["payload"]["title"] == "WS Task"

        # List tasks
        ws.send_json({
            "protocol_version": 1,
            "event_id": str(uuid4()),
            "session_id": str(session_id),
            "sequence": 2,
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "task.list",
            "payload": {},
        })
        list_event = ws.receive_json()
        assert list_event["type"] == "task.tasks"
        assert len(list_event["payload"]["tasks"]) == 1

        # Pause task
        ws.send_json({
            "protocol_version": 1,
            "event_id": str(uuid4()),
            "session_id": str(session_id),
            "sequence": 3,
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "task.pause",
            "payload": {"task_id": task_id},
        })
        paused_event = ws.receive_json()
        assert paused_event["type"] == "task.paused"

        # Resume task
        ws.send_json({
            "protocol_version": 1,
            "event_id": str(uuid4()),
            "session_id": str(session_id),
            "sequence": 4,
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "task.resume",
            "payload": {"task_id": task_id},
        })
        resumed_event = ws.receive_json()
        assert resumed_event["type"] == "task.resumed"

        # Delete task
        ws.send_json({
            "protocol_version": 1,
            "event_id": str(uuid4()),
            "session_id": str(session_id),
            "sequence": 5,
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "task.delete",
            "payload": {"task_id": task_id},
        })
        deleted_event = ws.receive_json()
        assert deleted_event["type"] == "task.deleted"


@pytest.mark.asyncio
async def test_websocket_consequential_confirmation(database: Database, ws_app_client: tuple[TestClient, str]) -> None:
    client, _tmp_dir = ws_app_client
    token, auth, session_id = await _mint_ticket(database)

    res = client.post("/api/v1/ws/tickets", headers={"Authorization": f"Bearer {token}"})
    ticket = res.json()["ticket"]

    with client.websocket_connect(f"/api/v1/ws/session?ticket={ticket}") as ws:
        session_id_str = str(session_id)
        ws.send_json({
            "protocol_version": 1,
            "event_id": str(uuid4()),
            "session_id": session_id_str,
            "sequence": 0,
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "session.hello",
            "payload": {},
        })
        ws.receive_json()

        # Create consequential task
        run_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        ws.send_json({
            "protocol_version": 1,
            "event_id": str(uuid4()),
            "session_id": session_id_str,
            "sequence": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "task.create",
            "payload": {
                "title": "Outward WS Action",
                "instruction": "Do outward action",
                "capability_id": "fake.ws.action",
                "target": "target-1",
                "parameters": {},
                "schedule": {"timezone": "UTC", "run_at": run_at},
                "idempotency_key": "ws-conseq-1",
            },
        })
        pending_event = ws.receive_json()
        assert pending_event["type"] == "task.pending_confirmation"
        task_id = pending_event["payload"]["id"]

        # Confirm task
        ws.send_json({
            "protocol_version": 1,
            "event_id": str(uuid4()),
            "session_id": session_id_str,
            "sequence": 2,
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "task.confirm",
            "payload": {"task_id": task_id, "response": "yes"},
        })
        confirmed_event = ws.receive_json()
        assert confirmed_event["type"] == "task.confirmed"
        assert confirmed_event["payload"]["state"] == "active"
