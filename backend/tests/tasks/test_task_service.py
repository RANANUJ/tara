from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from tara_api.auth.rate_limit import InMemoryLoginRateLimiter
from tara_api.auth.security import Argon2idPasswordHasher, SecureSessionTokenGenerator
from tara_api.auth.service import AuthenticationService
from tara_api.capabilities.filesystem import AllowlistedFilesystemListTool
from tara_api.capabilities.registry import CapabilityRegistry
from tara_api.domain.auth import AuthenticatedOwnerContext, Owner, OwnerSession
from tara_api.domain.tasks import ScheduleDefinition, ScheduledTaskCreateCommand, TaskState
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore
from tara_api.persistence.database import Database
from tara_api.persistence.models import ScheduledTaskModel
from tara_api.persistence.safety_store import SqlAlchemySafetyStore
from tara_api.safety.clock import SystemClock
from tara_api.safety.confirmations import DeterministicConfirmationService
from tara_api.safety.policy import DeterministicActionPolicyService
from tara_api.tasks.service import ScheduledTaskService


async def _authenticated_context(
    database: Database,
    email: str = "owner@example.test",
) -> tuple[Owner, OwnerSession]:
    store = SqlAlchemyAuthenticationStore(database)
    authentication = AuthenticationService(
        store,
        store,
        Argon2idPasswordHasher(),
        SecureSessionTokenGenerator(),
        InMemoryLoginRateLimiter(),
        lambda: datetime.now(UTC),
        timedelta(hours=1),
        timedelta(hours=1),
    )
    await authentication.bootstrap(email, "safe-password")
    owner, session, _token = await authentication.login(email, "safe-password")
    return owner, session


def _service(database, root: Path, *, enabled: bool = True) -> ScheduledTaskService:
    registry = CapabilityRegistry(AllowlistedFilesystemListTool((root,)) if enabled else None)
    return ScheduledTaskService(
        database,
        registry,
        DeterministicActionPolicyService(),
        DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock()),
    )


def _command(*, capability_id: str = "filesystem.list", target: str = ".", parameters: dict[str, str | int | bool | None] | None = None, idempotency_key: str = "one") -> ScheduledTaskCreateCommand:
    return ScheduledTaskCreateCommand(
        "Reminder",
        "Drink water",
        capability_id,
        target,
        parameters or {},
        ScheduleDefinition("UTC", datetime(2027, 1, 1, tzinfo=UTC)),
        idempotency_key,
    )


async def test_typed_registered_capability_creation_persists_safe_metadata(database, tmp_path: Path) -> None:
    owner, session = await _authenticated_context(database)

    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root)
    context = AuthenticatedOwnerContext(owner, session)

    task = await service.create(context, _command())

    assert task.state is TaskState.ACTIVE
    assert task.enabled is True
    assert task.capability_id == "filesystem.list"
    assert task.target_summary == "."
    assert task.parameters_hash is not None
    assert task.confirmation_id is None
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
    assert row is not None
    assert row.target_identity_hash is not None
    assert row.parameters_hash is not None
    assert row.confirmation_binding_hash is not None
    assert row.risk_level == "read_only"
    assert row.next_run_at is not None
    assert not hasattr(row, "target")
    assert not hasattr(row, "parameters")


async def test_owner_scoped_creation_is_idempotent(database, tmp_path: Path) -> None:
    owner, session = await _authenticated_context(database)

    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root)
    context = AuthenticatedOwnerContext(owner, session)
    command = _command()

    first = await service.create(context, command)
    second = await service.create(context, command)

    assert first.id == second.id


@pytest.mark.parametrize(
    "service_enabled,command,error_code",
    [
        (True, _command(capability_id="unknown.capability"), "unknown_capability"),
        (False, _command(), "unknown_capability"),
        (True, _command(parameters={"unexpected": "value"}), "invalid_capability_arguments"),
    ],
)
async def test_typed_creation_rejects_unavailable_or_invalid_capability(
    database,
    tmp_path: Path,
    service_enabled: bool,
    command: ScheduledTaskCreateCommand,
    error_code: str,
) -> None:
    owner, session = await _authenticated_context(database)

    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match=error_code):
        await _service(database, root, enabled=service_enabled).create(AuthenticatedOwnerContext(owner, session), command)
