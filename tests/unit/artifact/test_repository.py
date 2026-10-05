"""Unit tests for ArtifactRepository race-safe get-or-create."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from apps.shared.artifact.repository import ArtifactRepository
from apps.shared.db.models import Artifact


@pytest.fixture
def artifact_repo() -> ArtifactRepository:
    db = MagicMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.begin_nested = MagicMock()
    db.begin_nested.return_value.__aenter__ = AsyncMock(return_value=None)
    db.begin_nested.return_value.__aexit__ = AsyncMock(return_value=None)
    return ArtifactRepository(db)


@pytest.mark.asyncio
async def test_get_or_create_artifact_recovers_from_integrity_error(artifact_repo: ArtifactRepository):
    existing = Artifact(
        id=4,
        tenant_id=1,
        owner_id=2,
        artifact_type="scheduled_task",
        resource_id=5,
        title="Scheduled Task: Document Parse Worker",
        url="/scheduled-tasks/5",
        artifact_metadata={},
    )
    first_select = MagicMock()
    first_select.scalar_one_or_none.return_value = None
    second_select = MagicMock()
    second_select.scalar_one_or_none.return_value = existing
    artifact_repo.db.execute = AsyncMock(side_effect=[first_select, second_select])
    artifact_repo.db.flush = AsyncMock(
        side_effect=[IntegrityError("stmt", {}, Exception()), None],
    )
    artifact_repo._ensure_resource_acl = AsyncMock()

    artifact = await artifact_repo._get_or_create_artifact(
        tenant_id=1,
        owner_id=2,
        artifact_type="scheduled_task",
        resource_id=5,
        source_thread_id=None,
        title="Scheduled Task: Document Parse Worker",
        url="/scheduled-tasks/5",
        artifact_metadata={"status": "pending"},
    )

    assert artifact is existing
    artifact_repo._ensure_resource_acl.assert_awaited_once_with(artifact=existing, owner_id=2)
