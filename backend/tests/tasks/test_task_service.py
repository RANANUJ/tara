from datetime import UTC, datetime
from pathlib import Path

from tara_api.domain.tasks import ScheduleDefinition, ScheduledTaskCreateCommand, TaskState
from tara_api.tasks.service import ScheduledTaskService

from tara_api.domain.auth import AuthenticatedOwnerContext, Owner, OwnerSession
from uuid import uuid4


async def test_owner_scoped_creation_is_idempotent(database, tmp_path: Path) -> None:
    now = datetime.now(UTC)
    owner = Owner(uuid4(), "owner@example.test", now)
    context = AuthenticatedOwnerContext(owner, OwnerSession(uuid4(), owner.id, now, now, now, None, None))
    from tara_api.capabilities.filesystem import AllowlistedFilesystemListTool
    from tara_api.capabilities.registry import CapabilityRegistry
    from tara_api.safety.confirmations import DeterministicConfirmationService
    from tara_api.safety.policy import DeterministicActionPolicyService
    from tara_api.safety.clock import SystemClock
    from tara_api.persistence.safety_store import SqlAlchemySafetyStore

    root = tmp_path / "root"
    root.mkdir()
    service = ScheduledTaskService(database, CapabilityRegistry(AllowlistedFilesystemListTool((root,))), DeterministicActionPolicyService(), DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock()))
    schedule = ScheduleDefinition("UTC", datetime(2027, 1, 1, tzinfo=UTC))
    command = ScheduledTaskCreateCommand("Reminder", "Drink water", "filesystem.list", ".", {}, schedule, "one")
    first = await service.create(context, command)
    second = await service.create(context, command)
    assert first.id == second.id and first.state is TaskState.ACTIVE
