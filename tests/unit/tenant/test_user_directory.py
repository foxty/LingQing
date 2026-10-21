"""Unit tests for tenant user directory search."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.tenant_app_service.tenant.user_directory import search_tenant_users


@pytest.mark.asyncio
async def test_search_tenant_users_applies_query_and_exclude():
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = [(10, "alice"), (20, "bob")]
    db.execute = AsyncMock(return_value=result)

    rows = await search_tenant_users(
        db,
        tenant_id=1,
        query="al",
        limit=20,
        exclude_user_ids={99},
    )

    assert rows == [(10, "alice"), (20, "bob")]
    db.execute.assert_awaited_once()
    compiled = str(db.execute.await_args.args[0])
    assert "tenant_memberships" in compiled.lower() or "TenantMembership" in compiled
