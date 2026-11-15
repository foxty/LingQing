"""Temporary table metadata repository."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import TempTableMetadata


class TempTableRepository(BaseRepository[TempTableMetadata]):
    """Repository for TempTableMetadata CRUD operations."""

    def __init__(self, db: AsyncSession):
        """Initialize temp table repository.

        Args:
            db: Database session
        """
        super().__init__(TempTableMetadata, db)

    async def get_expired_tables(self) -> list[TempTableMetadata]:
        """Get all expired temporary tables.

        Returns:
            List of expired TempTableMetadata records
        """
        result = await self.db.execute(
            select(TempTableMetadata).where(TempTableMetadata.expires_at < datetime.now(UTC))
        )
        return list(result.scalars().all())

    async def delete_metadata(self, temp_meta: TempTableMetadata) -> None:
        """Delete temp table metadata record.

        Args:
            temp_meta: TempTableMetadata record to delete
        """
        await self.db.delete(temp_meta)
