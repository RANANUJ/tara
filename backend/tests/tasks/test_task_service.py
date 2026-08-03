from datetime import UTC, datetime

from tara_api.domain.tasks import ScheduleDefinition, TaskKind, TaskState
from tara_api.tasks.service import ScheduledTaskService

from tara_api.domain.auth import AuthenticatedOwnerContext, Owner, OwnerSession
from uuid import uuid4


async def test_owner_scoped_creation_is_idempotent(database) -> None:
    now = datetime.now(UTC)
    owner = Owner(uuid4(), "owner@example.test", now)
    context = AuthenticatedOwnerContext(owner, OwnerSession(uuid4(), owner.id, now, now, now, None, None))
    from tara_api.capabilities.registry import CapabilityRegistry
    from tara_api.safety.confirmations import DeterministicConfirmationService
    from tara_api.safety.permissions import DefaultDenyPermissionService
    from tara_api.safety.policy import DeterministicActionPolicyService
    from tara_api.safety.clock import SystemClock
    from tara_api.persistence.safety_store import SqlAlchemySafetyStore

    service = ScheduledTaskService(database, CapabilityRegistry(None), DeterministicActionPolicyService(), DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock()))
    schedule = ScheduleDefinition("UTC", datetime(2027, 1, 1, tzinfo=UTC))
    first = await service.create(context, title="Reminder", kind=TaskKind.REMINDER, instruction="Drink water", schedule=schedule, idempotency_key="one")
    second = await service.create(context, title="Reminder", kind=TaskKind.REMINDER, instruction="Drink water", schedule=schedule, idempotency_key="one")
    assert first.id == second.id and first.state is TaskState.ACTIVE
