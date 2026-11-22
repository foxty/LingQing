"""Provision platform-managed analytics PostgreSQL databases in integration tests.

Uses the same ``PostgreSQLProvisioningExecutor`` + ``TenantProvisioningService`` path
as ``tenant_cli`` (real ``psql`` DDL against the testcontainers Postgres).
"""

from __future__ import annotations

import os
import shutil
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from apps.shared.db.models import TenantMembership, User
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.value_objects import DatabaseConnectionVO
from apps.shared.external_systems.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.external_systems.data_source.schemas import DataSourceCreate
from apps.shared.external_systems.data_source.service import DataSourceService


def require_psql_cli() -> None:
    if not shutil.which("psql"):
        pytest.skip("psql CLI required for analytics DB provisioning integration tests")


def parse_pg_container_coords(pg_container: str) -> tuple[str, int]:
    parsed = urlparse(pg_container.replace("postgresql+asyncpg://", "postgresql://", 1))
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    return host, port


def sync_provisioning_env_from_testcontainers() -> None:
    """Re-assert psql admin env from testcontainers (ignore developer ``.env.local`` manager DB)."""
    required = (
        "TENANT_APP_DB_HOST",
        "TENANT_APP_DB_PORT",
        "TENANT_APP_DB_USER",
        "TENANT_APP_DB_PASSWORD",
        "TENANT_APP_DB_NAME",
    )
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        pytest.skip(f"testcontainers Postgres env not configured (missing {missing})")

    host = os.environ["TENANT_APP_DB_HOST"]
    port = os.environ["TENANT_APP_DB_PORT"]
    user = os.environ["TENANT_APP_DB_USER"]
    password = os.environ["TENANT_APP_DB_PASSWORD"]
    db_name = os.environ["TENANT_APP_DB_NAME"]

    for prefix in ("TENANT_APP_DB", "TENANT_MANAGER_DB"):
        os.environ[f"{prefix}_HOST"] = host
        os.environ[f"{prefix}_PORT"] = port
        os.environ[f"{prefix}_USER"] = user
        os.environ[f"{prefix}_PASSWORD"] = password
        os.environ[f"{prefix}_NAME"] = db_name


def reload_provisioning_modules() -> tuple[type, type]:
    """Reload config + provisioning modules so ``EnvConfig`` matches testcontainers env."""
    sync_provisioning_env_from_testcontainers()
    import importlib

    import apps.config
    import apps.tenant_app_service.tenant.postgres_executor as postgres_executor_mod
    import apps.tenant_app_service.tenant.provisioning_service as provisioning_service_mod

    importlib.reload(apps.config)
    importlib.reload(postgres_executor_mod)
    importlib.reload(provisioning_service_mod)
    return postgres_executor_mod.PostgreSQLProvisioningExecutor, provisioning_service_mod.TenantProvisioningService


async def provision_tenant_with_managed_analytics(
    session,
    *,
    monkeypatch: pytest.MonkeyPatch,
    role_password: str | None = None,
    pg_host: str | None = None,
    pg_port: int | None = None,
) -> dict[str, Any]:
    """Create tenant, provision analytics DB + managed DataSource (mirrors tenant_cli)."""
    require_psql_cli()
    PostgreSQLProvisioningExecutor, TenantProvisioningService = reload_provisioning_modules()
    if role_password is not None:

        def _fixed_password(self, length: int = 24) -> str:  # noqa: ARG001
            return role_password

        monkeypatch.setattr(PostgreSQLProvisioningExecutor, "_generate_password", _fixed_password)

    suffix = uuid4().hex[:8]
    executor = PostgreSQLProvisioningExecutor()
    provisioning = TenantProvisioningService(session, executor)

    tenant = await provisioning.provision_tenant(
        name=f"analytics_integ_{suffix}",
        slug=f"analytics-integ-{suffix}",
        description="integration provisioned analytics",
    )
    tenant_id = int(tenant["id"])
    connection: DatabaseConnectionVO = await provisioning.provision_analytics_db(
        tenant_id,
        pg_host=pg_host,
        pg_port=pg_port,
    )

    user = User(
        username=f"analytics_admin_{suffix}",
        email=f"analytics_admin_{suffix}@test.local",
        hashed_password="$2b$12$hAjROif0svlKIj.I.K5IwGugZ554XGSE44FPpq.1/9ZdSNr23Djvn.",
        tenant_id=tenant_id,
        role="admin",
        status="active",
    )
    session.add(user)
    await session.flush()
    session.add(
        TenantMembership(
            tenant_id=tenant_id,
            user_id=user.id,
            status="active",
        )
    )
    await session.flush()

    ds_service = DataSourceService(
        tenant_id=tenant_id,
        data_source_repo=DataSourceRepository(session),
        asset_repo=AssetMetadataRepository(session),
    )
    ds = await ds_service.create_data_source(
        DataSourceCreate(
            name=f"Analytics DB {suffix}",
            type="postgres",
            managed=True,
            description="Provisioned analytics database",
            config=connection.to_dict(),
        ),
        owner_id=user.id,
    )

    actor = ActorContext(tenant_id=tenant_id, user_id=user.id, user_role="admin")

    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant["name"],
        "connection": connection,
        "data_source_id": ds.id,
        "user": user,
        "actor": actor,
        "ds_service": ds_service,
        "provisioning": provisioning,
        "executor": executor,
    }


async def provision_standalone_postgres_database(
    *,
    monkeypatch: pytest.MonkeyPatch,
    pg_host: str,
    pg_port: int,
    role_password: str,
) -> dict[str, Any]:
    """Provision a standalone role + database (external warehouse / BYOT), not tenant_{id}_analytics."""
    require_psql_cli()
    PostgreSQLProvisioningExecutor, _TenantProvisioningService = reload_provisioning_modules()

    def _fixed_password(self, length: int = 24) -> str:  # noqa: ARG001
        return role_password

    monkeypatch.setattr(PostgreSQLProvisioningExecutor, "_generate_password", _fixed_password)

    suffix = uuid4().hex[:8]
    role_name = f"ext_role_{suffix}"
    db_name = f"ext_wh_{suffix}"
    executor = PostgreSQLProvisioningExecutor()
    connection = await executor.provision_database(
        db_name=db_name,
        role_name=role_name,
        host=pg_host,
        port=pg_port,
    )
    return {
        "connection": connection,
        "db_name": db_name,
        "role_name": role_name,
        "executor": executor,
        "suffix": suffix,
    }


async def teardown_standalone_postgres_database(stack: dict[str, Any]) -> None:
    executor = stack["executor"]
    await executor.drop_database(stack["db_name"])
    await executor.drop_role(stack["role_name"])