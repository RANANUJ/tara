"""Owner-scoped scheduled-task persistence adapter."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tara_api.persistence.models import ScheduledTaskModel


class SqlAlchemyScheduledTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_owner(self, task_id: UUID, owner_id: UUID) -> ScheduledTaskModel | None:
        return await self._session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_id, ScheduledTaskModel.owner_id == owner_id))

    async def list_for_owner(self, owner_id: UUID) -> list[ScheduledTaskModel]:
        return list((await self._session.scalars(select(ScheduledTaskModel).where(ScheduledTaskModel.owner_id == owner_id).order_by(ScheduledTaskModel.created_at))).all())

    async def add(self, model: ScheduledTaskModel) -> ScheduledTaskModel:
        self._session.add(model)
        await self._session.flush()
        return model

    async def delete_for_owner(self, task_id: UUID, owner_id: UUID) -> bool:
        model = await self.get_for_owner(task_id, owner_id)
        if model is None:
            return False
        await self._session.delete(model)
        return True

    async def get_for_confirmation(self, owner_id: UUID, confirmation_id: UUID) -> ScheduledTaskModel | None:
        return await self._session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.owner_id == owner_id, ScheduledTaskModel.confirmation_id == confirmation_id))

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
        confirmation_id: UUID,
        next_run_at: datetime,
    ) -> ScheduledTaskModel | None:
        model = await self.get_for_owner(task_id, owner_id)
        if (
            model is None
            or model.state != "pending_confirmation"
            or model.enabled
            or model.confirmation_id != confirmation_id
        ):
            return None
        model.state = "active"
        model.enabled = True
        model.next_run_at = next_run_at
        model.confirmation_status = "executing"
        await self._session.flush()
        return model
