"""Owner-scoped scheduled-task persistence adapter."""

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
