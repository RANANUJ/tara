"""Owner-scoped scheduled-task persistence adapter."""

from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from tara_api.persistence.models import ScheduledTaskModel, ScheduledTaskRunModel, TaskExecutionPayloadModel


class SqlAlchemyScheduledTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_owner(self, task_id: UUID, owner_id: UUID) -> ScheduledTaskModel | None:
        return cast(
            ScheduledTaskModel | None,
            await self._session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_id, ScheduledTaskModel.owner_id == owner_id)),
        )

    async def get_claimed_for_execution(self, task_id: UUID, owner_id: UUID, run_id: UUID) -> ScheduledTaskModel | None:
        return cast(
            ScheduledTaskModel | None,
            await self._session.scalar(
                select(ScheduledTaskModel).where(
                    ScheduledTaskModel.id == task_id,
                    ScheduledTaskModel.owner_id == owner_id,
                    ScheduledTaskModel.claim_id == run_id,
                    ScheduledTaskModel.state == "active",
                    ScheduledTaskModel.enabled.is_(True),
                )
            ),
        )

    async def list_for_owner(self, owner_id: UUID) -> list[ScheduledTaskModel]:
        return list((await self._session.scalars(select(ScheduledTaskModel).where(ScheduledTaskModel.owner_id == owner_id).order_by(ScheduledTaskModel.created_at))).all())

    async def get_by_idempotency(
        self,
        owner_id: UUID,
        session_id: UUID,
        idempotency_key_hash: str,
    ) -> ScheduledTaskModel | None:
        return cast(
            ScheduledTaskModel | None,
            await self._session.scalar(
                select(ScheduledTaskModel).where(
                    ScheduledTaskModel.owner_id == owner_id,
                    ScheduledTaskModel.owner_session_id == session_id,
                    ScheduledTaskModel.idempotency_key_hash == idempotency_key_hash,
                )
            ),
        )

    async def add(self, model: ScheduledTaskModel) -> ScheduledTaskModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def add_payload(self, model: TaskExecutionPayloadModel) -> TaskExecutionPayloadModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_payload(self, task_id: UUID, owner_id: UUID) -> TaskExecutionPayloadModel | None:
        return cast(
            TaskExecutionPayloadModel | None,
            await self._session.scalar(
                select(TaskExecutionPayloadModel).where(
                    TaskExecutionPayloadModel.task_id == task_id,
                    TaskExecutionPayloadModel.owner_id == owner_id,
                )
            ),
        )

    async def get_active_payload(self, task_id: UUID, owner_id: UUID, now: datetime) -> TaskExecutionPayloadModel | None:
        return cast(
            TaskExecutionPayloadModel | None,
            await self._session.scalar(
                select(TaskExecutionPayloadModel).where(
                    TaskExecutionPayloadModel.task_id == task_id,
                    TaskExecutionPayloadModel.owner_id == owner_id,
                    TaskExecutionPayloadModel.revoked_at.is_(None),
                    (TaskExecutionPayloadModel.expires_at.is_(None)) | (TaskExecutionPayloadModel.expires_at > now),
                )
            ),
        )

    async def revoke_payload(self, task_id: UUID, owner_id: UUID, now: datetime) -> bool:
        result = await self._session.execute(
            update(TaskExecutionPayloadModel)
            .where(
                TaskExecutionPayloadModel.task_id == task_id,
                TaskExecutionPayloadModel.owner_id == owner_id,
                TaskExecutionPayloadModel.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        return bool(cast(CursorResult[object], result).rowcount)

    async def replace_payload(self, task_id: UUID, owner_id: UUID, *, capability_id: str, binding_hash: str, payload_version: int, key_version: str, nonce: bytes, ciphertext: bytes, now: datetime) -> bool:
        result = await self._session.execute(
            update(TaskExecutionPayloadModel)
            .where(TaskExecutionPayloadModel.task_id == task_id, TaskExecutionPayloadModel.owner_id == owner_id, TaskExecutionPayloadModel.revoked_at.is_(None))
            .values(capability_id=capability_id, binding_hash=binding_hash, payload_version=payload_version, key_version=key_version, nonce=nonce, ciphertext=ciphertext, created_at=now)
        )
        return bool(cast(CursorResult[object], result).rowcount)

    async def delete_payload(self, task_id: UUID, owner_id: UUID) -> bool:
        payload = await self.get_payload(task_id, owner_id)
        if payload is None:
            return False
        await self._session.delete(payload)
        return True

    async def list_inactive_payloads(self, now: datetime, limit: int) -> list[TaskExecutionPayloadModel]:
        return list(
            (
                await self._session.scalars(
                    select(TaskExecutionPayloadModel)
                    .where((TaskExecutionPayloadModel.revoked_at.is_not(None)) | (TaskExecutionPayloadModel.expires_at <= now))
                    .order_by(TaskExecutionPayloadModel.created_at)
                    .limit(limit)
                )
            ).all()
        )

    async def cleanup_payloads(self, cutoff: datetime, limit: int) -> int:
        candidates = list(
            (
                await self._session.scalars(
                    select(TaskExecutionPayloadModel.id)
                    .where(
                        (TaskExecutionPayloadModel.revoked_at <= cutoff)
                        | (TaskExecutionPayloadModel.expires_at <= cutoff)
                    )
                    .order_by(TaskExecutionPayloadModel.created_at)
                    .limit(limit)
                )
            ).all()
        )
        if not candidates:
            return 0
        result = await self._session.execute(delete(TaskExecutionPayloadModel).where(TaskExecutionPayloadModel.id.in_(candidates)))
        return int(cast(CursorResult[object], result).rowcount)

    async def cleanup_completed_payloads(self, cutoff: datetime, limit: int) -> int:
        candidates = list(
            (
                await self._session.scalars(
                    select(TaskExecutionPayloadModel.id)
                    .join(ScheduledTaskModel, ScheduledTaskModel.id == TaskExecutionPayloadModel.task_id)
                    .where(
                        ScheduledTaskModel.state == "completed",
                        ScheduledTaskModel.last_run_at.is_not(None),
                        ScheduledTaskModel.last_run_at <= cutoff,
                    )
                    .order_by(ScheduledTaskModel.last_run_at)
                    .limit(limit)
                )
            ).all()
        )
        if not candidates:
            return 0
        result = await self._session.execute(delete(TaskExecutionPayloadModel).where(TaskExecutionPayloadModel.id.in_(candidates)))
        return int(cast(CursorResult[object], result).rowcount)

    async def recover_stale_claims(self, now: datetime, limit: int) -> int:
        stale = list(
            (
                await self._session.scalars(
                    select(ScheduledTaskModel)
                    .where(
                        ScheduledTaskModel.state == "active",
                        ScheduledTaskModel.enabled.is_(True),
                        ScheduledTaskModel.claim_id.is_not(None),
                        ScheduledTaskModel.claim_expires_at <= now,
                    )
                    .order_by(ScheduledTaskModel.claim_expires_at)
                    .limit(limit)
                )
            ).all()
        )
        for task in stale:
            if task.claim_id is None:
                continue
            await self._session.execute(
                update(ScheduledTaskRunModel)
                .where(
                    ScheduledTaskRunModel.task_id == task.id,
                    ScheduledTaskRunModel.run_id == task.claim_id,
                    ScheduledTaskRunModel.state.in_(("claimed", "running")),
                )
                .values(state="failed", finished_at=now, error_code="task_claim_lease_expired")
            )
            task.claim_id, task.claimed_at, task.claim_expires_at = None, None, None
        await self._session.flush()
        return len(stale)

    async def cleanup_runs(self, cutoff: datetime, limit: int) -> int:
        candidates = list(
            (
                await self._session.scalars(
                    select(ScheduledTaskRunModel.id)
                    .where(ScheduledTaskRunModel.finished_at.is_not(None), ScheduledTaskRunModel.finished_at <= cutoff)
                    .order_by(ScheduledTaskRunModel.finished_at)
                    .limit(limit)
                )
            ).all()
        )
        if not candidates:
            return 0
        result = await self._session.execute(delete(ScheduledTaskRunModel).where(ScheduledTaskRunModel.id.in_(candidates)))
        return int(cast(CursorResult[object], result).rowcount)

    async def cancel_for_owner(self, task_id: UUID, owner_id: UUID, now: datetime) -> bool:
        task = await self.get_for_owner(task_id, owner_id)
        if task is None:
            return False
        if task.state == "canceled":
            return True
        run_id = task.claim_id
        task.state, task.enabled, task.next_run_at = "canceled", False, None
        task.claim_id, task.claimed_at, task.claim_expires_at = None, None, None
        await self.revoke_payload(task_id, owner_id, now)
        if run_id is not None:
            await self._session.execute(
                update(ScheduledTaskRunModel)
                .where(
                    ScheduledTaskRunModel.task_id == task_id,
                    ScheduledTaskRunModel.run_id == run_id,
                    ScheduledTaskRunModel.state.in_(("claimed", "running")),
                )
                .values(state="canceled", finished_at=now, error_code="task_canceled")
            )
        await self._session.flush()
        return True

    async def mark_running(self, task_id: UUID, run_id: UUID, now: datetime) -> bool:
        result = await self._session.execute(
            update(ScheduledTaskRunModel)
            .where(ScheduledTaskRunModel.task_id == task_id, ScheduledTaskRunModel.run_id == run_id, ScheduledTaskRunModel.state == "claimed")
            .values(state="running", started_at=now)
        )
        return bool(cast(CursorResult[object], result).rowcount)

    async def complete_claim(self, task_id: UUID, run_id: UUID, now: datetime, next_run_at: datetime | None, outcome: str) -> bool:
        task_result = await self._session.execute(
            update(ScheduledTaskModel)
            .where(ScheduledTaskModel.id == task_id, ScheduledTaskModel.claim_id == run_id, ScheduledTaskModel.state == "active")
            .values(
                claim_id=None, claimed_at=None, claim_expires_at=None, state="active" if next_run_at else "completed", enabled=next_run_at is not None,
                next_run_at=next_run_at, last_run_at=now, last_outcome=outcome,
            )
        )
        run_result = await self._session.execute(
            update(ScheduledTaskRunModel)
            .where(ScheduledTaskRunModel.task_id == task_id, ScheduledTaskRunModel.run_id == run_id, ScheduledTaskRunModel.state == "running")
            .values(state="completed", finished_at=now, outcome_code=outcome)
        )
        return bool(cast(CursorResult[object], task_result).rowcount and cast(CursorResult[object], run_result).rowcount)

    async def delete_for_owner(self, task_id: UUID, owner_id: UUID) -> bool:
        model = await self.get_for_owner(task_id, owner_id)
        if model is None:
            return False
        await self._session.delete(model)
        return True

    async def get_for_confirmation(self, owner_id: UUID, confirmation_id: UUID) -> ScheduledTaskModel | None:
        return cast(
            ScheduledTaskModel | None,
            await self._session.scalar(
                select(ScheduledTaskModel).where(ScheduledTaskModel.owner_id == owner_id, ScheduledTaskModel.confirmation_id == confirmation_id)
            ),
        )

    async def attach_confirmation(
        self,
        task_id: UUID,
        owner_id: UUID,
        confirmation_id: UUID,
        status: str,
        binding_hash: str,
        expires_at: datetime,
    ) -> ScheduledTaskModel | None:
        model = await self.get_for_owner(task_id, owner_id)
        if model is None or model.confirmation_id is not None:
            return None
        model.confirmation_id = confirmation_id
        model.confirmation_status = status
        model.confirmation_binding_hash = binding_hash
        model.confirmation_expires_at = expires_at
        model.enabled, model.next_run_at, model.state = False, None, "pending_confirmation"
        await self._session.flush()
        return model

    async def clear_confirmation(self, task_id: UUID, owner_id: UUID) -> bool:
        model = await self.get_for_owner(task_id, owner_id)
        if model is None:
            return False
        model.confirmation_id = None
        model.confirmation_status = None
        model.confirmation_expires_at = None
        model.confirmation_binding_hash = None
        await self._session.flush()
        return True

    async def invalidate_confirmation(self, task_id: UUID, owner_id: UUID) -> ScheduledTaskModel | None:
        model = await self.get_for_owner(task_id, owner_id)
        if model is None:
            return None
        model.confirmation_id = None
        model.confirmation_status = None
        model.confirmation_expires_at = None
        model.confirmation_binding_hash = None
        model.state = "pending_confirmation"
        model.enabled = False
        model.next_run_at = None
        await self._session.flush()
        return model

    async def activate_after_confirmation(
        self,
        task_id: UUID,
        owner_id: UUID,
        session_id: UUID,
        confirmation_id: UUID,
        binding_hash: str,
        next_run_at: datetime,
    ) -> ScheduledTaskModel | None:
        statement = (
            update(ScheduledTaskModel)
            .where(
                ScheduledTaskModel.id == task_id,
                ScheduledTaskModel.owner_id == owner_id,
                ScheduledTaskModel.owner_session_id == session_id,
                ScheduledTaskModel.state == "pending_confirmation",
                ScheduledTaskModel.enabled.is_(False),
                ScheduledTaskModel.confirmation_id == confirmation_id,
                ScheduledTaskModel.confirmation_binding_hash == binding_hash,
            )
            .values(
                state="active",
                enabled=True,
                next_run_at=next_run_at,
                confirmation_status="executing",
            )
            .returning(ScheduledTaskModel)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def claim_due(
        self,
        now: datetime,
        limit: int,
        lease: timedelta,
    ) -> list[tuple[ScheduledTaskModel, UUID]]:
        candidates = list(
            (
                await self._session.scalars(
                    select(ScheduledTaskModel)
                    .where(
                        ScheduledTaskModel.state == "active",
                        ScheduledTaskModel.enabled.is_(True),
                        ScheduledTaskModel.next_run_at.is_not(None),
                        ScheduledTaskModel.next_run_at <= now,
                        (ScheduledTaskModel.claim_id.is_(None))
                        | (ScheduledTaskModel.claim_expires_at < now),
                    )
                    .order_by(ScheduledTaskModel.next_run_at)
                    .limit(limit)
                )
            ).all()
        )
        claimed: list[tuple[ScheduledTaskModel, UUID]] = []
        for candidate in candidates:
            run_id = uuid4()
            statement = (
                update(ScheduledTaskModel)
                .where(
                    ScheduledTaskModel.id == candidate.id,
                    ScheduledTaskModel.state == "active",
                    ScheduledTaskModel.enabled.is_(True),
                    ScheduledTaskModel.next_run_at == candidate.next_run_at,
                    (ScheduledTaskModel.claim_id.is_(None))
                    | (ScheduledTaskModel.claim_expires_at < now),
                )
                .values(claim_id=run_id, claimed_at=now, claim_expires_at=now + lease)
                .returning(ScheduledTaskModel)
            )
            task = (await self._session.execute(statement)).scalar_one_or_none()
            if task is None or task.next_run_at is None:
                continue
            self._session.add(
                ScheduledTaskRunModel(
                    run_id=run_id,
                    task_id=task.id,
                    owner_id=task.owner_id,
                    scheduled_for=task.next_run_at,
                    claimed_at=now,
                    state="claimed",
                )
            )
            claimed.append((task, run_id))
        await self._session.flush()
        return claimed

    async def fail_claim(self, task_id: UUID, run_id: UUID, now: datetime, error_code: str) -> bool:
        task_result = await self._session.execute(
            update(ScheduledTaskModel)
            .where(ScheduledTaskModel.id == task_id, ScheduledTaskModel.claim_id == run_id, ScheduledTaskModel.state == "active")
            .values(
                claim_id=None,
                claimed_at=None,
                claim_expires_at=None,
                state="failed",
                enabled=False,
                next_run_at=None,
                last_run_at=now,
                last_outcome=error_code,
            )
        )
        run_result = await self._session.execute(
            update(ScheduledTaskRunModel)
            .where(
                ScheduledTaskRunModel.task_id == task_id,
                ScheduledTaskRunModel.run_id == run_id,
                ScheduledTaskRunModel.state.in_(("claimed", "running")),
            )
            .values(state="failed", finished_at=now, error_code=error_code)
        )
        return bool(
            cast(CursorResult[object], task_result).rowcount
            and cast(CursorResult[object], run_result).rowcount
        )
