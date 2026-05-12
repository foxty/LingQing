"""PostgreSQL executor for database and role management.

Implements unified provisioning via `psql` CLI for DDL operations that
cannot run inside transaction blocks, then initializes schema via SQLAlchemy.
"""

import os
import secrets
import string
import subprocess

from apps.config import EnvConfig
from apps.shared.domain.value_objects import DatabaseConnectionVO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.tenant.provisioning_executor import ProvisioningExecutor

logger = get_logger(__name__)


class PostgreSQLProvisioningExecutor(ProvisioningExecutor):
    """PostgreSQL implementation of tenant infrastructure provisioning via psql CLI.

    Uses subprocess to invoke psql for DDL operations that cannot run inside
    transaction blocks (CREATE/DROP DATABASE, CREATE ROLE, etc.).
    """

    def _generate_password(self, length: int = 24) -> str:
        """Generate secure random password."""
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(secrets.choice(chars) for _ in range(length))

    def _escape_sql(self, value: str) -> str:
        return value.replace("'", "''")

    def _run_psql(
        self,
        host: str,
        port: int,
        sql: str,
        db: str | None = None,
        user: str = "postgres",
        password: str | None = None,
    ) -> None:
        env = os.environ.copy()
        if password is not None:
            env["PGPASSWORD"] = password
        cmd = [
            "psql",
            "-U",
            user,
            "-h",
            host,
            "-p",
            str(port),
            "-v",
            "ON_ERROR_STOP=1",
        ]
        if db:
            cmd.extend(["-d", db])
        cmd.extend(["-c", sql])
        subprocess.run(cmd, check=True, env=env, capture_output=False)

    def _get_admin_credentials(self) -> tuple[str, str, str]:
        """Get admin credentials from environment configuration.

        Priority:
        1. TENANT_MANAGER_DB_USER / TENANT_MANAGER_DB_PASSWORD
        2. TENANT_APP_DB_USER / TENANT_APP_DB_PASSWORD
        """
        use_manager_credentials = bool(EnvConfig.TENANT_MANAGER_DB_USER and EnvConfig.TENANT_MANAGER_DB_PASSWORD)

        if use_manager_credentials:
            admin_user = EnvConfig.TENANT_MANAGER_DB_USER
            admin_password = EnvConfig.TENANT_MANAGER_DB_PASSWORD
            admin_db = EnvConfig.TENANT_MANAGER_DB_NAME or EnvConfig.TENANT_APP_DB_NAME or "postgres"
        else:
            admin_user = EnvConfig.TENANT_APP_DB_USER
            admin_password = EnvConfig.TENANT_APP_DB_PASSWORD
            admin_db = EnvConfig.TENANT_APP_DB_NAME or "postgres"

        if not admin_user or not admin_password:
            raise ValueError(
                "Missing admin DB credentials. Set TENANT_MANAGER_DB_USER/TENANT_MANAGER_DB_PASSWORD "
                "or TENANT_APP_DB_USER/TENANT_APP_DB_PASSWORD."
            )
        return admin_user, admin_password, admin_db

    async def provision_database(self, db_name: str, role_name: str, host: str, port: int) -> DatabaseConnectionVO:
        password = self._generate_password()
        admin_user, admin_password, admin_db = self._get_admin_credentials()
        role_sql = (
            f"DO $$ BEGIN\n"
            f"    CREATE ROLE \"{role_name}\" WITH LOGIN PASSWORD '{self._escape_sql(password)}';\n"
            f"EXCEPTION WHEN duplicate_object THEN\n"
            f"    ALTER ROLE \"{role_name}\" WITH PASSWORD '{self._escape_sql(password)}';\n"
            f"END $$;"
        )
        self._run_psql(host, port, role_sql, db=admin_db, user=admin_user, password=admin_password)
        # Allow role to create databases, then create DB as the role so it's the owner
        self._run_psql(
            host,
            port,
            f'ALTER ROLE "{role_name}" CREATEDB',
            db=admin_db,
            user=admin_user,
            password=admin_password,
        )
        self._run_psql(
            host,
            port,
            f'CREATE DATABASE "{db_name}"',
            db="postgres",
            user=role_name,
            password=password,
        )
        logger.info(f"Provisioned database {db_name} for role {role_name}")
        return DatabaseConnectionVO.from_credentials(
            host=host,
            port=port,
            database=db_name,
            username=role_name,
            password=password,
        )

    async def drop_role(self, role_name: str) -> None:
        """Drop PostgreSQL role.

        Args:
            role_name: Role name to drop
        """
        admin_user, admin_password, admin_db = self._get_admin_credentials()
        self._run_psql(
            EnvConfig.TENANT_APP_DB_HOST,
            EnvConfig.TENANT_APP_DB_PORT,
            f'DROP ROLE IF EXISTS "{role_name}"',
            db=admin_db,
            user=admin_user,
            password=admin_password,
        )
        logger.info(f"Dropped role {role_name}")

    async def drop_database(self, db_name: str) -> None:
        """Drop PostgreSQL database and terminate active connections.

        Args:
            db_name: Database name to drop
        """
        admin_user, admin_password, admin_db = self._get_admin_credentials()

        # Terminate active connections
        terminate_sql = (
            f"SELECT pg_terminate_backend(pg_stat_activity.pid) "
            f"FROM pg_stat_activity "
            f"WHERE pg_stat_activity.datname = '{db_name}' AND pid <> pg_backend_pid();"
        )
        self._run_psql(
            EnvConfig.TENANT_APP_DB_HOST,
            EnvConfig.TENANT_APP_DB_PORT,
            terminate_sql,
            db=admin_db,
            user=admin_user,
            password=admin_password,
        )
        logger.debug(f"Terminated connections to {db_name}")
        # Drop database
        self._run_psql(
            EnvConfig.TENANT_APP_DB_HOST,
            EnvConfig.TENANT_APP_DB_PORT,
            f'DROP DATABASE IF EXISTS "{db_name}"',
            db=admin_db,
            user=admin_user,
            password=admin_password,
        )
        logger.info(f"Dropped database {db_name}")
