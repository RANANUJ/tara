"""REST API transport tests for M16 Scheduled Tasks."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

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


class _ConsequentialTestTool:
    definition = ToolDefinition(
        "fake.scheduled.send",
        "1",
        PermissionScope("fake.scheduled.send"),
        ActionRiskLevel.OUTWARD_FACING,
        "perform a non-production scheduled action",
    )

    def validate_arguments(self, arguments: Mapping[str, JsonValue]) -> dict[str, object]:
        return dict(arguments)

    async def execute(self, _request: ToolRequest, _validated_arguments: dict[str, object]) -> ToolResult:
        return ToolResult(ToolResultStatus.SUCCEEDED, "ok")


@pytest.fixture
def test_client(database: Database, tmp_path: Path) -> TestClient:
    app = create_app(database=database)
    tmp_path.mkdir(parents=True, exist_ok=True)
    protector = TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    fs_tool = AllowlistedFilesystemListTool((tmp_path,))
    app.state.task_payload_protector = protector
    app.state.capability_registry = CapabilityRegistry(
        fs_tool,
        additional_tools=(_ConsequentialTestTool(),),
    )
    app.state.scheduled_task_service = ScheduledTaskService(
        app.state.database,
        app.state.capability_registry,
        app.state.action_policy,
        app.state.confirmation_service,
        protector,
    )
    return TestClient(app, raise_server_exceptions=True)


async def _auth_headers(database: Database, email: str = "owner@example.test") -> dict[str, str]:
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
    _owner, _session, token = await auth.login(email, "safe-password")
    return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_requests_rejected(test_client: TestClient) -> None:
    res = test_client.get("/api/v1/tasks")
    assert res.status_code == 401

    res = test_client.post(
        "/api/v1/tasks",
        json={
            "title": "Task",
            "instruction": "Do things",
            "capability_id": "filesystem.list",
            "target": ".",
            "parameters": {},
            "schedule": {"timezone": "UTC", "run_at": "2027-01-01T00:00:00Z"},
            "idempotency_key": "unauth-1",
        },
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_scheduled_task_crud_and_lifecycle_api(database: Database, test_client: TestClient, tmp_path: Path) -> None:
    headers = await _auth_headers(database)

    # 1. Create read-only task
    run_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    create_payload = {
        "title": "List Files",
        "instruction": "List root directory",
        "capability_id": "filesystem.list",
        "target": ".",
        "parameters": {},
        "schedule": {"timezone": "UTC", "run_at": run_at},
        "idempotency_key": "task-api-1",
    }

    res = test_client.post("/api/v1/tasks", json=create_payload, headers=headers)
    if res.status_code != 201:
        print("CREATE ERROR RESPONSE:", res.json())
    assert res.status_code == 201
    data = res.json()
    task_id = data["id"]
    assert data["title"] == "List Files"
    assert data["state"] == "active"
    assert data["enabled"] is True
    assert data["capability_id"] == "filesystem.list"
    assert "target" not in data
    assert "parameters" not in data
    assert data["target_summary"] == "configured target"

    # 2. Get task
    res = test_client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["id"] == task_id

    # 3. List tasks
    res = test_client.get("/api/v1/tasks", headers=headers)
    assert res.status_code == 200
    tasks = res.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == task_id

    # 4. Pause task
    res = test_client.post(f"/api/v1/tasks/{task_id}/pause", headers=headers)
    assert res.status_code == 200
    res = test_client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert res.json()["state"] == "paused"
    assert res.json()["enabled"] is False

    # 5. Resume task
    res = test_client.post(f"/api/v1/tasks/{task_id}/resume", headers=headers)
    assert res.status_code == 200
    res = test_client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert res.json()["state"] == "active"

    # 6. Disable task
    res = test_client.post(f"/api/v1/tasks/{task_id}/disable", headers=headers)
    assert res.status_code == 200
    res = test_client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert res.json()["state"] == "disabled"

    # 7. Enable task
    res = test_client.post(f"/api/v1/tasks/{task_id}/enable", headers=headers)
    assert res.status_code == 200
    res = test_client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert res.json()["state"] == "active"

    # 8. Cancel task
    res = test_client.post(f"/api/v1/tasks/{task_id}/cancel", headers=headers)
    assert res.status_code == 200
    res = test_client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert res.json()["state"] == "canceled"

    # 9. Delete task
    res = test_client.delete(f"/api/v1/tasks/{task_id}", headers=headers)
    assert res.status_code == 200
    res = test_client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_consequential_confirmation_flow_api(database: Database, test_client: TestClient) -> None:
    headers = await _auth_headers(database)

    # Create consequential task
    run_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    create_payload = {
        "title": "Send Outward Briefing",
        "instruction": "Send briefing message",
        "capability_id": "fake.scheduled.send",
        "target": "recipient@example.test",
        "parameters": {"content": "payload"},
        "schedule": {"timezone": "UTC", "run_at": run_at},
        "idempotency_key": "consequential-api-1",
    }

    res = test_client.post("/api/v1/tasks", json=create_payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    task_id = data["id"]
    assert data["state"] == "pending_confirmation"
    assert data["enabled"] is False
    assert data["confirmation_id"] is not None

    # Approve confirmation
    res = test_client.post(f"/api/v1/tasks/{task_id}/approve", json={"response": "yes"}, headers=headers)
    assert res.status_code == 200
    approved = res.json()
    assert approved["state"] == "active"
    assert approved["enabled"] is True


@pytest.mark.asyncio
async def test_update_task_and_runs_api(database: Database, test_client: TestClient, tmp_path: Path) -> None:
    headers = await _auth_headers(database)

    run_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    create_payload = {
        "title": "Initial Title",
        "instruction": "Initial instruction",
        "capability_id": "filesystem.list",
        "target": ".",
        "parameters": {},
        "schedule": {"timezone": "UTC", "run_at": run_at},
        "idempotency_key": "update-api-1",
    }
    res = test_client.post("/api/v1/tasks", json=create_payload, headers=headers)
    task_id = res.json()["id"]

    # Update task title and instruction
    update_payload = {"title": "Updated Title", "instruction": "Updated instruction"}
    res = test_client.put(f"/api/v1/tasks/{task_id}", json=update_payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["title"] == "Updated Title"

    # Get runs history (empty initially)
    res = test_client.get(f"/api/v1/tasks/{task_id}/runs", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_foreign_task_non_enumeration_api(database: Database, test_client: TestClient) -> None:
    headers = await _auth_headers(database)
    random_id = str(uuid4())

    assert test_client.get(f"/api/v1/tasks/{random_id}", headers=headers).status_code == 404
    assert test_client.post(f"/api/v1/tasks/{random_id}/pause", headers=headers).status_code == 404
    assert test_client.delete(f"/api/v1/tasks/{random_id}", headers=headers).status_code == 404
