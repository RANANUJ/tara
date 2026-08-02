"""M14 fake consequential action confirmation safety tests."""

from datetime import UTC, datetime, timedelta

from tara_api.auth.rate_limit import InMemoryLoginRateLimiter
from tara_api.auth.security import Argon2idPasswordHasher, SecureSessionTokenGenerator
from tara_api.auth.service import AuthenticationService
from tara_api.capabilities.consequential import FakeConsequentialActionService
from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore
from tara_api.persistence.database import Database
from tara_api.persistence.safety_store import SqlAlchemySafetyStore
from tara_api.safety.clock import SystemClock
from tara_api.safety.confirmations import DeterministicConfirmationService


async def test_fake_action_requires_one_valid_confirmation(database: Database) -> None:
    store = SqlAlchemyAuthenticationStore(database)
    auth = AuthenticationService(store, store, Argon2idPasswordHasher(), SecureSessionTokenGenerator(), InMemoryLoginRateLimiter(), lambda: datetime.now(UTC), timedelta(hours=1), timedelta(hours=1))
    await auth.bootstrap("owner@example.test", "safe-password")
    owner, session, _token = await auth.login("owner@example.test", "safe-password")
    context = AuthenticatedOwnerContext(owner, session)
    confirmations = DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock(), context_validator=auth)
    service = FakeConsequentialActionService(confirmations, SqlAlchemySafetyStore(database), auth, enabled=True)

    action = await service.propose(context, "synthetic target")
    assert action is not None and action.state == "awaiting_confirmation"
    assert (await service.respond(context, action.confirmation_id, "maybe")).state == "awaiting_confirmation"
    completed = await service.respond(context, action.confirmation_id, "yes")
    assert completed is not None and completed.state == "succeeded"
    assert (await service.respond(context, action.confirmation_id, "yes")).state == "succeeded"


async def test_uncertain_fake_action_never_claims_success(database: Database) -> None:
    store = SqlAlchemyAuthenticationStore(database)
    auth = AuthenticationService(store, store, Argon2idPasswordHasher(), SecureSessionTokenGenerator(), InMemoryLoginRateLimiter(), lambda: datetime.now(UTC), timedelta(hours=1), timedelta(hours=1))
    await auth.bootstrap("owner@example.test", "safe-password")
    owner, session, _token = await auth.login("owner@example.test", "safe-password")
    context = AuthenticatedOwnerContext(owner, session)
    confirmations = DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock(), context_validator=auth)
    service = FakeConsequentialActionService(confirmations, SqlAlchemySafetyStore(database), auth, enabled=True, uncertain=True)

    action = await service.propose(context, "synthetic target")
    assert action is not None
    assert (await service.respond(context, action.confirmation_id, "yes")).state == "uncertain"
