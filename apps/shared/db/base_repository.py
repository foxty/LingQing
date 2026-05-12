"""Base repository with common CRUD operations."""

from typing import Generic, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository with common CRUD operations.

    Provides generic CRUD methods that can be reused by all repositories.
    """

    def __init__(self, model: Type[ModelType], db: AsyncSession):
        """Initialize base repository.

        Args:
            model: SQLAlchemy model class
            db: Database session
        """
        self.model = model
        self.db = db

    async def get_by_id(self, id: int) -> ModelType | None:
        """Get entity by ID.

        Args:
            id: Entity ID

        Returns:
            Entity or None if not found
        """
        result = await self.db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_all(self, limit: int | None = None, offset: int | None = None) -> list[ModelType]:
        """Get all entities with optional pagination.

        Args:
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of entities
        """
        query = select(self.model)

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Count total number of entities.

        Returns:
            Total count
        """
        result = await self.db.execute(select(self.model))
        return len(result.scalars().all())

    async def create(self, entity: ModelType) -> ModelType:
        """Create new entity.

        Args:
            entity: Entity to create

        Returns:
            Created entity with ID
        """
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def update(self, entity: ModelType) -> ModelType:
        """Update existing entity.

        Args:
            entity: Entity to update

        Returns:
            Updated entity
        """
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def delete(self, entity: ModelType) -> None:
        """Delete entity.

        Args:
            entity: Entity to delete
        """
        await self.db.delete(entity)
        await self.db.flush()

    async def delete_by_id(self, id: int) -> bool:
        """Delete entity by ID.

        Args:
            id: Entity ID

        Returns:
            True if deleted, False if not found
        """
        entity = await self.get_by_id(id)
        if entity:
            await self.delete(entity)
            return True
        return False

    # Transaction Management Methods
    # Note: commit/rollback are handled by @transaction decorator
    # Repositories should only use flush() for internal operations

    async def refresh(self, entity: ModelType) -> None:
        """Refresh entity from database.

        Args:
            entity: Entity to refresh
        """
        await self.db.refresh(entity)
