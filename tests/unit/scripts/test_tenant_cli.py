"""Unit tests for tenant_cli."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts import tenant_cli


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("demo", True),
        ("my-company", True),
        ("acme-001", True),
        ("ab", True),
        ("Demo", False),
        ("-bad", False),
        ("bad-", False),
        ("a", False),
        ("", False),
        ("my_company", False),
    ],
)
def test_validate_slug(slug: str, expected: bool):
    assert tenant_cli.validate_slug(slug) is expected


@pytest.mark.asyncio
async def test_create_tenant_with_defaults_skips_when_slug_exists():
    session = AsyncMock()
    mock_provisioning = MagicMock()
    mock_provisioning.get_tenant_by_slug = AsyncMock(return_value={"id": 42})
    mock_provisioning.provision_tenant = AsyncMock()

    with patch("scripts.tenant_cli.TenantProvisioningService", return_value=mock_provisioning):
        tenant_id = await tenant_cli.create_tenant_with_defaults(
            "Existing Co",
            "existing-co",
            "desc",
            session,
        )

    assert tenant_id == 42
    mock_provisioning.provision_tenant.assert_not_called()


@pytest.mark.asyncio
async def test_create_tenant_with_defaults_provisions_full_stack():
    session = AsyncMock()
    db_info = SimpleNamespace(database="tenant_7_analytics", to_dict=lambda: {"database": "tenant_7_analytics"})

    mock_provisioning = MagicMock()
    mock_provisioning.get_tenant_by_slug = AsyncMock(return_value=None)
    mock_provisioning.provision_tenant = AsyncMock(return_value={"id": 7})
    mock_provisioning.provision_analytics_db = AsyncMock(return_value=db_info)

    mock_user_service = MagicMock()
    mock_user_service.create_user = AsyncMock(return_value=SimpleNamespace(id=100))

    mock_data_source_service = MagicMock()
    mock_data_source_service.create_data_source = AsyncMock()

    with (
        patch("scripts.tenant_cli.TenantProvisioningService", return_value=mock_provisioning),
        patch("scripts.tenant_cli.TenantUserManagementService", return_value=mock_user_service),
        patch("scripts.tenant_cli.DataSourceService", return_value=mock_data_source_service),
    ):
        tenant_id = await tenant_cli.create_tenant_with_defaults(
            "Acme",
            "acme",
            "Enterprise",
            session,
        )

    assert tenant_id == 7
    mock_provisioning.provision_tenant.assert_awaited_once()
    mock_user_service.create_user.assert_awaited_once_with(username="admin", password="admin", role="admin")
    mock_provisioning.provision_analytics_db.assert_awaited_once_with(7)
    mock_data_source_service.create_data_source.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_tenants_prints_rows(capsys):
    mock_provisioning = MagicMock()
    mock_provisioning.get_all_tenants = AsyncMock(
        return_value=[
            {"id": 1, "name": "Demo", "slug": "demo", "status": "active"},
        ]
    )
    mock_session = AsyncMock()

    with (
        patch("scripts.tenant_cli.app_db_session") as mock_session_ctx,
        patch("scripts.tenant_cli.PostgreSQLProvisioningExecutor"),
        patch("scripts.tenant_cli.TenantProvisioningService", return_value=mock_provisioning),
    ):
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        await tenant_cli.list_tenants()

    output = capsys.readouterr().out
    assert "demo" in output
    assert "Total: 1 tenant(s)" in output


@pytest.mark.asyncio
async def test_show_tenant_not_found_exits():
    mock_provisioning = MagicMock()
    mock_provisioning.get_tenant_with_user_count = AsyncMock(return_value=None)
    mock_session = AsyncMock()

    with (
        patch("scripts.tenant_cli.app_db_session") as mock_session_ctx,
        patch("scripts.tenant_cli.PostgreSQLProvisioningExecutor"),
        patch("scripts.tenant_cli.TenantProvisioningService", return_value=mock_provisioning),
        pytest.raises(SystemExit) as exc_info,
    ):
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        await tenant_cli.show_tenant("missing")

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_seed_tags_for_tenant_commits_on_success():
    mock_provisioning = MagicMock()
    mock_provisioning.get_tenant_by_slug = AsyncMock(return_value={"id": 3})
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    with (
        patch("scripts.tenant_cli.app_db_session") as mock_session_ctx,
        patch("scripts.tenant_cli.PostgreSQLProvisioningExecutor"),
        patch("scripts.tenant_cli.TenantProvisioningService", return_value=mock_provisioning),
        patch("scripts.tenant_cli.seed_default_tags", AsyncMock()) as mock_seed,
    ):
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        await tenant_cli.seed_tags_for_tenant("demo")

    mock_seed.assert_awaited_once_with(mock_session, 3)
    mock_session.commit.assert_awaited_once()
