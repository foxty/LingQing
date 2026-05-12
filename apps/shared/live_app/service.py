"""Service layer for live app runtime operations."""

import hashlib
import re
import tempfile
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.artifact.access import ArtifactAccessGuard
from apps.shared.artifact.domain import ArtifactType
from apps.shared.artifact.lifecycle import ArtifactLifecycle
from apps.shared.artifact.schemas import Artifact
from apps.shared.audit_event.repository import AuditEventRepository
from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import InternalServiceError, ResourceNotFoundError, ValidationError
from apps.shared.data_source.repository import DataSourceRepository
from apps.shared.domain.actor import ActorContext
from apps.shared.live_app.adapters import (
    db_live_app_to_domain,
    domain_live_app_list_to_dto,
    domain_live_app_to_dto,
)
from apps.shared.live_app.data_executor import LiveAppDataExecutor
from apps.shared.live_app.domain import (
    LiveAppAuditEventType,
    LiveAppConfig,
    LiveAppDeploymentState,
    LiveAppMigration,
    LiveAppPromotionMigrationSummary,
    LiveAppPromotionPayload,
    LiveAppPromotionRecord,
    LiveAppRecord,
)
from apps.shared.live_app.repository import LiveAppRepository
from apps.shared.live_app.schemas import (
    LiveAppCreateWithArtifactResult,
    LiveAppListDTO,
    LiveAppRecordDTO,
)
from apps.shared.live_app.workspace import (
    ALLOWED_LIVE_APP_ENVIRONMENTS,
    DEFAULT_LIVE_APP_ENVIRONMENT,
    LiveAppWriteLockTimeoutError,
    commit_app_changes,
    delete_app_file,
    ensure_entry_file,
    get_latest_commit_for_app_environment,
    grep_app_files,
    has_uncommitted_changes,
    init_app_repo,
    is_commit_in_app_environment_history,
    list_app_commits_for_environment,
    list_app_files,
    list_app_files_at_commit,
    read_app_file,
    read_entry,
    sync_environment_from_commit,
    write_app_file,
)
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

_FORBIDDEN_SQL_PATTERNS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge|call)\b",
    re.IGNORECASE,
)
_NAMESPACE_PATTERN = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\.")
_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_MIGRATION_UP_SUFFIX = ".up.sql"
_MIGRATION_DOWN_SUFFIX = ".down.sql"
_MIGRATION_SEQUENCE_PATTERN = re.compile(r"^(\d+)_")
_MIGRATION_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


class LiveAppService(TenantAwareService):
    """Tenant-scoped business service for live app entry operations."""

    def __init__(self, tenant_id: int, db_session: AsyncSession):
        super().__init__(tenant_id=tenant_id, db_session=db_session)
        self.repo = LiveAppRepository(db_session)
        self.artifacts = ArtifactLifecycle(
            db=db_session,
            tenant_id=tenant_id,
            artifact_type=ArtifactType.APP,
            entity_repo=self.repo,
        )
        self.data_source_repo = DataSourceRepository(db_session)
        self.audit_repo = AuditEventRepository(db_session)
        self.data_executor = LiveAppDataExecutor(tenant_id=tenant_id, db_session=db_session)

    @classmethod
    def create(cls, tenant_id: int, db_session: AsyncSession) -> "LiveAppService":
        return cls(tenant_id=tenant_id, db_session=db_session)

    def _app_guard(self, actor: ActorContext) -> ArtifactAccessGuard:
        return ArtifactAccessGuard(
            db=self.db_session,
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            artifact_type=ArtifactType.APP.value,
        )

    async def require_read_access(self, *, app_id: int, actor: ActorContext) -> None:
        await self._app_guard(actor).require_read(resource_id=app_id)

    async def require_write_access(self, *, app_id: int, actor: ActorContext) -> None:
        await self._app_guard(actor).require_write(resource_id=app_id)

    async def require_owner_access(self, *, app_id: int, actor: ActorContext) -> None:
        await self._app_guard(actor).require_owner_or_manage(
            resource_id=app_id,
            allow_shared_write=False,
        )

    async def get_app_for_actor(self, app_id: int, *, actor: ActorContext) -> LiveAppRecordDTO:
        await self.require_read_access(app_id=app_id, actor=actor)
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})
        return domain_live_app_to_dto(db_live_app_to_domain(live_app))

    async def list_apps_for_actor(self, *, actor: ActorContext) -> LiveAppListDTO:
        has_manage = await role_has_permission(
            db=self.db_session,
            tenant_id=actor.tenant_id,
            role_key=actor.user_role,
            permission=TenantAppPermissions.ARTIFACTS_MANAGE,
        )
        apps = await self.artifacts.list_entities(
            user_id=actor.user_id,
            has_manage=has_manage,
        )
        return domain_live_app_list_to_dto([db_live_app_to_domain(item) for item in apps])

    async def get_entry_page_for_actor(
        self,
        app_id: int,
        *,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_read_access(app_id=app_id, actor=actor)
        return await self.get_entry_page(app_id=app_id, environment=environment)

    async def read_file_for_actor(
        self,
        app_id: int,
        path: str,
        *,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_read_access(app_id=app_id, actor=actor)
        return await self.read_file(app_id=app_id, path=path, environment=environment)

    async def list_files_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_read_access(app_id=app_id, actor=actor)
        return await self.list_files(app_id=app_id, environment=environment)

    async def grep_files_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        pattern: str,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        case_insensitive: bool = False,
        max_matches: int = 100,
        max_file_bytes: int = 512_000,
    ) -> dict:
        await self.require_read_access(app_id=app_id, actor=actor)
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError(f"Live app {app_id} not found")
        normalized_env = self._normalize_environment(environment)

        try:
            result = grep_app_files(
                tenant_id=self.tenant_id,
                app_id=app_id,
                pattern=pattern,
                environment=normalized_env,
                case_insensitive=case_insensitive,
                max_matches=max_matches,
                max_file_bytes=max_file_bytes,
            )
        except ValueError as e:
            raise ValidationError(
                str(e),
                details={"code": "APP_GREP_INVALID", "app_id": app_id, "pattern": pattern},
            ) from e

        result["app_id"] = live_app.id
        return result

    async def write_file_for_actor(
        self,
        *,
        app_id: int,
        path: str,
        content: str,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_write_access(app_id=app_id, actor=actor)
        return await self.write_file(
            app_id=app_id,
            path=path,
            content=content,
            environment=environment,
            actor_user_id=actor.user_id,
        )

    async def list_migrations_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_read_access(app_id=app_id, actor=actor)
        return await self.list_migrations(app_id=app_id, environment=environment)

    async def validate_app_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_read_access(app_id=app_id, actor=actor)
        return await self.validate_app(app_id=app_id, environment=environment)

    async def apply_migration_for_actor(
        self,
        *,
        app_id: int,
        migration_name: str,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_write_access(app_id=app_id, actor=actor)
        return await self.apply_migration(
            app_id=app_id,
            migration_name=migration_name,
            environment=environment,
            actor_user_id=actor.user_id,
        )

    async def rollback_migration_for_actor(
        self,
        *,
        app_id: int,
        migration_name: str,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_write_access(app_id=app_id, actor=actor)
        return await self.rollback_migration(
            app_id=app_id,
            migration_name=migration_name,
            environment=environment,
            actor_user_id=actor.user_id,
        )

    async def create_migration_for_actor(
        self,
        *,
        app_id: int,
        migration_name: str,
        up_sql: str,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        down_sql: str | None = None,
    ) -> dict:
        await self.require_write_access(app_id=app_id, actor=actor)
        return await self.create_migration(
            app_id=app_id,
            migration_name=migration_name,
            up_sql=up_sql,
            environment=environment,
            down_sql=down_sql,
            actor_user_id=actor.user_id,
        )

    async def remove_migration_for_actor(
        self,
        *,
        app_id: int,
        migration_name: str,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_write_access(app_id=app_id, actor=actor)
        return await self.remove_migration(
            app_id=app_id,
            migration_name=migration_name,
            environment=environment,
            actor_user_id=actor.user_id,
        )

    async def commit_changes_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        commit_message: str | None = None,
    ) -> dict:
        await self.require_write_access(app_id=app_id, actor=actor)
        return await self.commit_changes(
            app_id=app_id,
            environment=environment,
            commit_message=commit_message,
            actor_user_id=actor.user_id,
        )

    async def promote_environment_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        from_environment: str,
        to_environment: str,
        source_commit: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        await self.require_write_access(app_id=app_id, actor=actor)
        return await self.promote_environment(
            app_id=app_id,
            from_environment=from_environment,
            to_environment=to_environment,
            source_commit=source_commit,
            dry_run=dry_run,
            actor_user_id=actor.user_id,
        )

    async def list_commits_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        limit: int = 20,
    ) -> dict:
        await self.require_read_access(app_id=app_id, actor=actor)
        return await self.list_commits(app_id=app_id, environment=environment, limit=limit)

    async def list_promotions_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        limit: int = 20,
    ) -> dict:
        await self.require_read_access(app_id=app_id, actor=actor)
        return await self.list_promotions(app_id=app_id, limit=limit)

    async def get_deployment_state_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
    ) -> dict:
        await self.require_read_access(app_id=app_id, actor=actor)
        return await self.get_deployment_state(app_id=app_id)

    async def diff_environments_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        from_environment: str = "dev",
        to_environment: str = "prod",
    ) -> dict:
        await self.require_read_access(app_id=app_id, actor=actor)
        return await self.diff_environments(
            app_id=app_id,
            from_environment=from_environment,
            to_environment=to_environment,
        )

    async def query_data_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        sql: str,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_read_access(app_id=app_id, actor=actor)
        return await self.query_data(
            app_id=app_id,
            sql=sql,
            environment=environment,
            actor_user_id=actor.user_id,
        )

    async def mutate_data_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        operation: str,
        table: str,
        data: dict | list[dict] | None = None,
        where: dict | None = None,
        row_id: int | str | None = None,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_write_access(app_id=app_id, actor=actor)
        return await self.mutate_data(
            app_id=app_id,
            operation=operation,
            table=table,
            data=data,
            where=where,
            row_id=row_id,
            environment=environment,
            actor_user_id=actor.user_id,
        )

    async def import_data_for_actor(
        self,
        *,
        app_id: int,
        actor: ActorContext,
        table: str,
        mode: str,
        file_name: str,
        file_content: bytes,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        await self.require_write_access(app_id=app_id, actor=actor)
        return await self.import_data(
            app_id=app_id,
            table=table,
            mode=mode,
            file_name=file_name,
            file_content=file_content,
            environment=environment,
            actor_user_id=actor.user_id,
        )

    async def create_app_with_artifact(
        self,
        *,
        name: str,
        description: str | None = None,
        owner_id: int,
        data_source_id: int | None = None,
        thread_id: str | None = None,
    ) -> LiveAppCreateWithArtifactResult:
        normalized_name = (name or "").strip()
        if not normalized_name:
            raise ValidationError(
                "Live app name is required.",
                details={"code": "APP_INVALID_NAME"},
            )

        try:
            resolved_data_source_id = await self._resolve_live_app_data_source_id(data_source_id)
            live_app = await self.repo.add(
                tenant_id=self.tenant_id,
                owner_id=owner_id,
                data_source_id=resolved_data_source_id,
                name=normalized_name,
                description=(description or "").strip() or None,
                app_config=LiveAppConfig().to_dict(),
            )
        except IntegrityError as e:
            raise ValidationError(
                "Live app with same name already exists.",
                details={"code": "APP_NAME_CONFLICT", "name": normalized_name},
            ) from e

        init_app_repo(self.tenant_id, live_app.id)
        self._bootstrap_app_workspace(app_id=live_app.id, entry_file=live_app.entry_file)
        await self._ensure_environment_schemas(
            app_id=live_app.id,
            data_source_id=resolved_data_source_id,
        )
        linked_artifact = await self.artifacts.link_on_create(
            resource_id=live_app.id,
            owner_id=owner_id,
            title=live_app.name,
            url=f"/api/apps/{live_app.id}/dev/embed",
            thread_id=thread_id,
            metadata={
                "app_id": live_app.id,
                "entry_file": live_app.entry_file,
                "sdk_version": live_app.sdk_version,
            },
        )
        return LiveAppCreateWithArtifactResult(
            app=domain_live_app_to_dto(db_live_app_to_domain(live_app)),
            artifact=Artifact.create_live_app(linked_artifact),
        )

    async def get_app(self, app_id: int) -> LiveAppRecord:
        return await self._get_app(app_id)

    async def _get_app(self, app_id: int) -> LiveAppRecord:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})
        return db_live_app_to_domain(live_app)

    async def list_apps(
        self,
        user_id: int,
        *,
        has_artifacts_manage: bool = False,
    ) -> list[LiveAppRecord]:
        return await self._list_apps(
            user_id=user_id,
            has_artifacts_manage=has_artifacts_manage,
        )

    async def _list_apps(
        self,
        user_id: int,
        *,
        has_artifacts_manage: bool = False,
    ) -> list[LiveAppRecord]:
        apps = await self.artifacts.list_entities(
            user_id=user_id,
            has_manage=has_artifacts_manage,
        )
        return [db_live_app_to_domain(item) for item in apps]

    async def delete_app(self, app_id: int) -> None:
        deleted = await self.repo.delete_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not deleted:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})
        await self.artifacts.delete_cascade(resource_id=app_id)

    async def get_entry_page(self, app_id: int, *, environment: str = DEFAULT_LIVE_APP_ENVIRONMENT) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError(f"Live app {app_id} not found")
        normalized_env = self._normalize_environment(environment)
        deployed_state = self._deployment_state_from_live_app(live_app).to_dict()

        ensure_entry_file(
            tenant_id=self.tenant_id,
            app_id=app_id,
            entry_file=live_app.entry_file,
            environment=normalized_env,
        )
        html = read_entry(
            tenant_id=self.tenant_id,
            app_id=app_id,
            entry_file=live_app.entry_file,
            environment=normalized_env,
        )
        return {
            "app_id": live_app.id,
            "entry_file": live_app.entry_file,
            "sdk_version": live_app.sdk_version,
            "environment": normalized_env,
            "deployed_commit": deployed_state.get(normalized_env),
            "html": html,
        }

    async def list_files(self, app_id: int, *, environment: str = DEFAULT_LIVE_APP_ENVIRONMENT) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError(f"Live app {app_id} not found")
        normalized_env = self._normalize_environment(environment)

        ensure_entry_file(
            tenant_id=self.tenant_id,
            app_id=app_id,
            entry_file=live_app.entry_file,
            environment=normalized_env,
        )
        files = list_app_files(tenant_id=self.tenant_id, app_id=app_id, environment=normalized_env)
        return {"app_id": live_app.id, "environment": normalized_env, "files": files}

    async def read_file(self, app_id: int, path: str, *, environment: str = DEFAULT_LIVE_APP_ENVIRONMENT) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError(f"Live app {app_id} not found")
        normalized_env = self._normalize_environment(environment)

        try:
            content = read_app_file(
                tenant_id=self.tenant_id,
                app_id=app_id,
                relative_path=path,
                environment=normalized_env,
            )
        except FileNotFoundError as e:
            raise ResourceNotFoundError(f"File '{path}' not found in live app {app_id}") from e
        except ValueError as e:
            raise ValidationError(
                "Invalid file path or file type for live app read.",
                details={"code": "APP_INVALID_FILE_PATH", "path": path, "app_id": app_id},
            ) from e

        return {"app_id": live_app.id, "environment": normalized_env, "path": path, "content": content}

    async def write_file(
        self,
        app_id: int,
        path: str,
        content: str,
        *,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        actor_user_id: int | None = None,
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError(f"Live app {app_id} not found")
        normalized_env = self._normalize_environment(environment)

        try:
            write_result = self._write_content_no_commit(
                new_content=content,
                read_current=lambda: read_app_file(
                    tenant_id=self.tenant_id,
                    app_id=app_id,
                    relative_path=path,
                    environment=normalized_env,
                ),
                write_new=lambda new_content: write_app_file(
                    tenant_id=self.tenant_id,
                    app_id=app_id,
                    relative_path=path,
                    content=new_content,
                    environment=normalized_env,
                ),
            )
        except LiveAppWriteLockTimeoutError as e:
            raise ValidationError(
                "Live app is currently being updated by another writer.",
                details={"code": "APP_CONFLICT_LOCKED", "app_id": app_id},
            ) from e
        except ValueError as e:
            raise ValidationError(
                "Invalid file path or file type for live app write.",
                details={"code": "APP_INVALID_FILE_PATH", "path": path, "app_id": app_id},
            ) from e
        except RuntimeError as e:
            raise InternalServiceError(f"Failed to commit live app file changes: {e}") from e

        result = {
            "app_id": live_app.id,
            "environment": normalized_env,
            "path": path,
            "updated": write_result["updated"],
            "committed": write_result["committed"],
        }
        await self._record_audit_event(
            actor_user_id=actor_user_id,
            event_type=LiveAppAuditEventType.FILE_WRITE,
            payload=result,
        )
        return result

    async def query_data(
        self,
        app_id: int,
        sql: str,
        *,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        actor_user_id: int | None = None,
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})
        if live_app.data_source_id is None:
            raise InternalServiceError(
                "Live app data source is not configured.",
                details={"code": "APP_RUNTIME_BROKEN", "app_id": app_id},
            )

        normalized_env = self._normalize_environment(environment)
        schema_name = self._schema_for_environment(app_id=app_id, environment=normalized_env)
        self._validate_query_sql_scope(app_id=app_id, sql=sql, schema_name=schema_name)

        try:
            df = await self.data_executor.query_data(
                data_source_id=live_app.data_source_id,
                sql_query=sql,
                schema_name=schema_name,
            )
        except Exception as e:
            raise ValidationError(
                "Invalid SQL for live app query.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id, "cause": str(e)},
            ) from e

        columns = [str(col) for col in list(df.columns)]
        rows = df.values.tolist()
        payload = {"app_id": app_id, "environment": normalized_env, "row_count": len(rows)}
        await self._record_audit_event(
            actor_user_id=actor_user_id,
            event_type=LiveAppAuditEventType.DATA_QUERY,
            payload=payload,
        )
        return {"rows": rows, "columns": columns, "row_count": len(rows), "environment": normalized_env}

    async def mutate_data(
        self,
        app_id: int,
        operation: str,
        table: str,
        data: dict | list[dict] | None = None,
        *,
        where: dict | None = None,
        row_id: int | str | None = None,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        actor_user_id: int | None = None,
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})
        if live_app.data_source_id is None:
            raise InternalServiceError(
                "Live app data source is not configured.",
                details={"code": "APP_RUNTIME_BROKEN", "app_id": app_id},
            )

        op = operation.lower()
        allowed_ops = ("insert", "update", "update_by_id", "delete_by_id")
        if op not in allowed_ops:
            raise ValidationError(
                f"Unsupported operation. Allowed: {', '.join(allowed_ops)}.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )

        normalized_env = self._normalize_environment(environment)
        full_table_name = self._resolve_app_table_name(app_id=app_id, table=table, environment=normalized_env)

        try:
            if op == "insert":
                if not data:
                    raise ValidationError(
                        "Insert operation requires data.",
                        details={"code": "APP_INVALID_SQL", "app_id": app_id},
                    )
                rows = self._normalize_mutation_rows(app_id=app_id, data=data)
                affected_rows = await self.data_executor.insert_rows(
                    data_source_id=live_app.data_source_id,
                    full_table_name=full_table_name,
                    rows=rows,
                )
            elif op == "update_by_id":
                if not data or not isinstance(data, dict):
                    raise ValidationError(
                        "Update operation requires data as a single object.",
                        details={"code": "APP_INVALID_SQL", "app_id": app_id},
                    )
                if row_id is None:
                    raise ValidationError(
                        "update_by_id requires an id.",
                        details={"code": "APP_INVALID_SQL", "app_id": app_id},
                    )
                affected_rows = await self.data_executor.update_by_id(
                    data_source_id=live_app.data_source_id,
                    full_table_name=full_table_name,
                    row_id=row_id,
                    data=data,
                )
            elif op == "update":
                if not data or not isinstance(data, dict):
                    raise ValidationError(
                        "Update operation requires data as a single object.",
                        details={"code": "APP_INVALID_SQL", "app_id": app_id},
                    )
                if not where:
                    raise ValidationError(
                        "Update operation requires where conditions.",
                        details={"code": "APP_INVALID_SQL", "app_id": app_id},
                    )
                affected_rows = await self.data_executor.update_rows(
                    data_source_id=live_app.data_source_id,
                    full_table_name=full_table_name,
                    data=data,
                    where=where,
                )
            else:
                if row_id is None:
                    raise ValidationError(
                        "delete_by_id requires an id.",
                        details={"code": "APP_INVALID_SQL", "app_id": app_id},
                    )
                affected_rows = await self.data_executor.delete_by_id(
                    data_source_id=live_app.data_source_id,
                    full_table_name=full_table_name,
                    row_id=row_id,
                )
        except ValidationError:
            raise
        except ValueError as e:
            raise ValidationError(
                f"Invalid mutation payload for {op}.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id, "cause": str(e)},
            ) from e
        except Exception as e:
            raise ValidationError(
                f"Failed to execute {op} on live app table.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id, "cause": str(e)},
            ) from e

        payload = {
            "app_id": app_id,
            "environment": normalized_env,
            "operation": op,
            "table": full_table_name,
            "affected_rows": affected_rows,
        }
        await self._record_audit_event(
            actor_user_id=actor_user_id,
            event_type=LiveAppAuditEventType.DATA_MUTATE,
            payload=payload,
        )
        return payload

    async def import_data(
        self,
        app_id: int,
        table: str,
        mode: str,
        file_name: str,
        file_content: bytes,
        *,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        actor_user_id: int | None = None,
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})
        if live_app.data_source_id is None:
            raise InternalServiceError(
                "Live app data source is not configured.",
                details={"code": "APP_RUNTIME_BROKEN", "app_id": app_id},
            )

        normalized_env = self._normalize_environment(environment)
        normalized_mode = (mode or "").strip().lower()
        if normalized_mode not in {"append", "replace"}:
            raise ValidationError(
                "Unsupported import mode.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )

        full_table_name = self._resolve_app_import_table_name(app_id=app_id, table=table, environment=normalized_env)
        if not file_content:
            raise ValidationError(
                "Import file cannot be empty.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )
        if not (file_name or "").lower().endswith(".csv"):
            raise ValidationError(
                "Only CSV import is supported in v1.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )

        suffix = Path(file_name).suffix or ".csv"
        temp_file_path: Path | None = None
        with tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, delete=False) as temp_file:
            temp_file.write(file_content)
            temp_file_path = Path(temp_file.name)

        try:
            imported_rows = await self.data_executor.import_csv(
                data_source_id=live_app.data_source_id,
                full_table_name=full_table_name,
                csv_file_path=str(temp_file_path),
                mode=normalized_mode,
            )
        except Exception as e:
            raise ValidationError(
                "Failed to import CSV into live app table.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id, "cause": str(e)},
            ) from e
        finally:
            if temp_file_path is not None:
                temp_file_path.unlink(missing_ok=True)

        payload = {
            "app_id": app_id,
            "environment": normalized_env,
            "table": full_table_name,
            "file_name": file_name,
            "mode": normalized_mode,
            "imported_rows": imported_rows,
        }
        await self._record_audit_event(
            actor_user_id=actor_user_id,
            event_type=LiveAppAuditEventType.DATA_IMPORT,
            payload=payload,
        )
        return payload

    async def list_migrations(self, app_id: int, *, environment: str = DEFAULT_LIVE_APP_ENVIRONMENT) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})

        normalized_env = self._normalize_environment(environment)
        schema_name = self._schema_for_environment(app_id=app_id, environment=normalized_env)
        local = self._collect_local_migrations(app_id=app_id, environment=normalized_env)
        applied_by_name: dict[str, dict] = {}

        if live_app.data_source_id is not None:
            applied = await self.data_executor.list_applied_migrations(
                data_source_id=live_app.data_source_id,
                schema_name=schema_name,
            )
            applied_by_name = {item["name"]: item for item in applied}

        migrations: list[dict] = []
        for item in local:
            applied_info = applied_by_name.get(item.name)
            migrations.append(
                {
                    "name": item.name,
                    "path": item.path,
                    "checksum": item.checksum,
                    "has_down": item.has_down,
                    "applied": applied_info is not None,
                    "applied_at": None if applied_info is None else applied_info["applied_at"],
                }
            )
        return {"app_id": app_id, "environment": normalized_env, "migrations": migrations}

    async def validate_app(
        self,
        app_id: int,
        *,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
    ) -> dict:
        """Preflight validation: checks entry file, SQL syntax, and migration state."""
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})

        normalized_env = self._normalize_environment(environment)
        checks: list[dict] = []

        # 1. Entry file exists and is non-empty
        try:
            entry = read_entry(
                tenant_id=self.tenant_id,
                app_id=app_id,
                entry_file=live_app.entry_file,
                environment=normalized_env,
            )
            if not entry or not entry.strip():
                checks.append({"check": "entry_file", "status": "fail", "message": "Entry file is empty."})
            else:
                checks.append({"check": "entry_file", "status": "pass", "message": f"{len(entry)} bytes"})
        except Exception as e:
            checks.append({"check": "entry_file", "status": "fail", "message": str(e)})
            entry = ""

        # 2. Extract and dry-run SQL from component attributes
        sql_queries = re.findall(r'source="([^"]+)"', entry)
        if not sql_queries:
            checks.append({"check": "sql_validation", "status": "skip", "message": "No SQL source attributes found."})
        elif live_app.data_source_id is None:
            checks.append({"check": "sql_validation", "status": "skip", "message": "No data source configured."})
        else:
            schema_name = self._schema_for_environment(app_id=app_id, environment=normalized_env)
            sql_errors: list[dict] = []
            for sql in sql_queries:
                dry_sql = f"SELECT * FROM ({sql}) _v LIMIT 0"
                try:
                    await self.data_executor.query_data(
                        data_source_id=live_app.data_source_id,
                        sql_query=dry_sql,
                        schema_name=schema_name,
                    )
                except Exception as e:
                    sql_errors.append({"sql": sql, "error": str(e)})
            if sql_errors:
                checks.append(
                    {
                        "check": "sql_validation",
                        "status": "fail",
                        "message": f"{len(sql_errors)} of {len(sql_queries)} queries failed.",
                        "errors": sql_errors,
                    }
                )
            else:
                checks.append(
                    {
                        "check": "sql_validation",
                        "status": "pass",
                        "message": f"{len(sql_queries)} queries validated.",
                    }
                )

        # 3. Migration state: check for unapplied migrations
        try:
            migration_result = await self.list_migrations(app_id=app_id, environment=environment)
            migrations = migration_result.get("migrations", [])
            unapplied = [m["name"] for m in migrations if not m["applied"]]
            if unapplied:
                checks.append(
                    {
                        "check": "migrations",
                        "status": "fail",
                        "message": f"{len(unapplied)} unapplied migration(s).",
                        "unapplied": unapplied,
                    }
                )
            else:
                checks.append(
                    {
                        "check": "migrations",
                        "status": "pass",
                        "message": f"{len(migrations)} migration(s), all applied.",
                    }
                )
        except Exception as e:
            checks.append({"check": "migrations", "status": "fail", "message": str(e)})

        passed = all(c["status"] in ("pass", "skip") for c in checks)
        return {
            "app_id": app_id,
            "environment": normalized_env,
            "valid": passed,
            "checks": checks,
        }

    async def apply_migration(
        self,
        app_id: int,
        migration_name: str,
        *,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        actor_user_id: int | None = None,
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})
        if live_app.data_source_id is None:
            raise InternalServiceError(
                "Live app data source is not configured.",
                details={"code": "APP_RUNTIME_BROKEN", "app_id": app_id},
            )

        normalized_env = self._normalize_environment(environment)
        schema_name = self._schema_for_environment(app_id=app_id, environment=normalized_env)
        migration = self._get_local_migration(app_id=app_id, migration_name=migration_name, environment=normalized_env)
        try:
            result = await self.data_executor.apply_migration(
                data_source_id=live_app.data_source_id,
                schema_name=schema_name,
                migration_name=migration.name,
                checksum=migration.checksum,
                up_sql=migration.up_sql,
            )
        except ValueError as e:
            raise ValidationError(
                "Migration conflicts with applied history.",
                details={"code": "APP_MIGRATION_CONFLICT", "app_id": app_id, "migration": migration_name},
            ) from e
        except Exception as e:
            raise ValidationError(
                f"Failed to apply migration: {e}",
                details={"code": "APP_MIGRATION_APPLY_FAILED", "app_id": app_id, "migration": migration_name},
            ) from e

        payload = {"app_id": app_id, "environment": normalized_env, "migration": migration.name, **result}
        await self._record_audit_event(
            actor_user_id=actor_user_id,
            event_type=LiveAppAuditEventType.MIGRATION_APPLY,
            payload=payload,
        )
        return payload

    async def rollback_migration(
        self,
        app_id: int,
        migration_name: str,
        *,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        actor_user_id: int | None = None,
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})
        if live_app.data_source_id is None:
            raise InternalServiceError(
                "Live app data source is not configured.",
                details={"code": "APP_RUNTIME_BROKEN", "app_id": app_id},
            )

        normalized_env = self._normalize_environment(environment)
        schema_name = self._schema_for_environment(app_id=app_id, environment=normalized_env)
        migration = self._get_local_migration(app_id=app_id, migration_name=migration_name, environment=normalized_env)
        if not migration.down_sql:
            raise ValidationError(
                "Rollback SQL not found for migration.",
                details={"code": "APP_MIGRATION_DOWN_MISSING", "app_id": app_id, "migration": migration_name},
            )

        try:
            result = await self.data_executor.rollback_migration(
                data_source_id=live_app.data_source_id,
                schema_name=schema_name,
                migration_name=migration.name,
                down_sql=migration.down_sql,
            )
        except Exception as e:
            raise ValidationError(
                f"Failed to rollback migration: {e}",
                details={"code": "APP_MIGRATION_ROLLBACK_FAILED", "app_id": app_id, "migration": migration_name},
            ) from e

        payload = {"app_id": app_id, "environment": normalized_env, "migration": migration.name, **result}
        await self._record_audit_event(
            actor_user_id=actor_user_id,
            event_type=LiveAppAuditEventType.MIGRATION_ROLLBACK,
            payload=payload,
        )
        return payload

    async def create_migration(
        self,
        app_id: int,
        migration_name: str,
        up_sql: str,
        *,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        down_sql: str | None = None,
        actor_user_id: int | None = None,
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})

        normalized_env = self._normalize_environment(environment)
        normalized_name = self._normalize_migration_name(app_id=app_id, migration_name=migration_name)
        normalized_up_sql = (up_sql or "").strip()
        if not normalized_up_sql:
            raise ValidationError(
                "Migration up SQL cannot be empty.",
                details={"code": "APP_MIGRATION_INVALID", "app_id": app_id, "migration": normalized_name},
            )

        up_path = f"migrations/{normalized_name}{_MIGRATION_UP_SUFFIX}"
        down_path = f"migrations/{normalized_name}{_MIGRATION_DOWN_SUFFIX}"
        existing = self._find_local_migration(app_id=app_id, migration_name=normalized_name, environment=normalized_env)
        if existing is not None:
            raise ValidationError(
                "Migration already exists.",
                details={"code": "APP_MIGRATION_ALREADY_EXISTS", "app_id": app_id, "migration": normalized_name},
            )

        try:
            write_app_file(
                tenant_id=self.tenant_id,
                app_id=app_id,
                relative_path=up_path,
                content=normalized_up_sql + "\n",
                environment=normalized_env,
            )
            if down_sql is not None and down_sql.strip():
                write_app_file(
                    tenant_id=self.tenant_id,
                    app_id=app_id,
                    relative_path=down_path,
                    content=down_sql.strip() + "\n",
                    environment=normalized_env,
                )
            committed = False
        except LiveAppWriteLockTimeoutError as e:
            raise ValidationError(
                "Live app is currently being updated by another writer.",
                details={"code": "APP_CONFLICT_LOCKED", "app_id": app_id},
            ) from e
        except ValueError as e:
            raise ValidationError(
                "Invalid migration path.",
                details={"code": "APP_MIGRATION_INVALID", "app_id": app_id, "migration": normalized_name},
            ) from e
        except RuntimeError as e:
            raise InternalServiceError(f"Failed to commit migration changes: {e}") from e

        payload = {
            "app_id": app_id,
            "environment": normalized_env,
            "migration": normalized_name,
            "created": True,
            "committed": committed,
        }
        await self._record_audit_event(
            actor_user_id=actor_user_id,
            event_type=LiveAppAuditEventType.MIGRATION_CREATE,
            payload=payload,
        )
        return payload

    async def remove_migration(
        self,
        app_id: int,
        migration_name: str,
        *,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        actor_user_id: int | None = None,
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})

        normalized_env = self._normalize_environment(environment)
        normalized_name = self._normalize_migration_name(app_id=app_id, migration_name=migration_name)
        migration = self._find_local_migration(
            app_id=app_id, migration_name=normalized_name, environment=normalized_env
        )
        if migration is None:
            raise ValidationError(
                "Migration file not found in app workspace.",
                details={"code": "APP_MIGRATION_NOT_FOUND", "app_id": app_id, "migration": normalized_name},
            )

        try:
            delete_app_file(
                tenant_id=self.tenant_id,
                app_id=app_id,
                relative_path=migration.path,
                environment=normalized_env,
            )
            if migration.down_path:
                delete_app_file(
                    tenant_id=self.tenant_id,
                    app_id=app_id,
                    relative_path=migration.down_path,
                    environment=normalized_env,
                )
            committed = False
        except LiveAppWriteLockTimeoutError as e:
            raise ValidationError(
                "Live app is currently being updated by another writer.",
                details={"code": "APP_CONFLICT_LOCKED", "app_id": app_id},
            ) from e
        except ValueError as e:
            raise ValidationError(
                "Invalid migration path.",
                details={"code": "APP_MIGRATION_INVALID", "app_id": app_id, "migration": normalized_name},
            ) from e
        except RuntimeError as e:
            raise InternalServiceError(f"Failed to commit migration removal changes: {e}") from e

        payload = {
            "app_id": app_id,
            "environment": normalized_env,
            "migration": normalized_name,
            "removed": True,
            "committed": committed,
        }
        await self._record_audit_event(
            actor_user_id=actor_user_id,
            event_type=LiveAppAuditEventType.MIGRATION_REMOVE,
            payload=payload,
        )
        return payload

    async def commit_changes(
        self,
        app_id: int,
        *,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        commit_message: str | None = None,
        actor_user_id: int | None = None,
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})
        normalized_env = self._normalize_environment(environment)
        self._ensure_dev_only_git_operation(
            app_id=app_id,
            environment=normalized_env,
            operation="commit",
        )
        message = (commit_message or "").strip() or f"live_app:{app_id}:{normalized_env} apply user-intent batch"

        try:
            committed = commit_app_changes(
                tenant_id=self.tenant_id,
                app_id=app_id,
                environment=normalized_env,
                commit_message=message,
            )
        except RuntimeError as e:
            raise InternalServiceError(f"Failed to commit live app changes: {e}") from e

        payload = {"app_id": app_id, "environment": normalized_env, "committed": committed, "message": message}
        await self._record_audit_event(
            actor_user_id=actor_user_id,
            event_type=LiveAppAuditEventType.COMMIT,
            payload=payload,
        )
        return payload

    async def promote_environment(
        self,
        app_id: int,
        *,
        from_environment: str,
        to_environment: str,
        source_commit: str | None = None,
        dry_run: bool = False,
        actor_user_id: int | None = None,
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})

        normalized_from_env = self._normalize_environment(from_environment)
        normalized_to_env = self._normalize_environment(to_environment)
        self._validate_environment_promotion(
            app_id=app_id,
            from_environment=normalized_from_env,
            to_environment=normalized_to_env,
        )
        if live_app.data_source_id is None:
            raise InternalServiceError(
                "Live app data source is not configured.",
                details={"code": "APP_RUNTIME_BROKEN", "app_id": app_id},
            )
        current_state = self._deployment_state_from_live_app(live_app)

        if normalized_from_env == "test" and normalized_to_env == "prod" and not (source_commit or "").strip():
            raise ValidationError(
                "Explicit source commit is required for test to prod promotion.",
                details={"code": "APP_PROMOTION_SOURCE_COMMIT_REQUIRED", "app_id": app_id},
            )

        resolved_source_commit = (source_commit or "").strip() or get_latest_commit_for_app_environment(
            tenant_id=self.tenant_id,
            app_id=app_id,
            environment=normalized_from_env,
        )
        if not resolved_source_commit:
            raise ValidationError(
                "No committed source version found for promotion.",
                details={
                    "code": "APP_PROMOTION_SOURCE_COMMIT_NOT_FOUND",
                    "app_id": app_id,
                    "from_environment": normalized_from_env,
                },
            )

        if not is_commit_in_app_environment_history(
            tenant_id=self.tenant_id,
            app_id=app_id,
            environment="dev",
            commit_sha=resolved_source_commit,
        ):
            raise ValidationError(
                "Source commit is not in dev app history.",
                details={
                    "code": "APP_PROMOTION_SOURCE_COMMIT_NOT_IN_DEV_HISTORY",
                    "app_id": app_id,
                    "source_commit": resolved_source_commit,
                },
            )

        try:
            source_files = list_app_files_at_commit(
                tenant_id=self.tenant_id,
                app_id=app_id,
                environment="dev",
                commit_sha=resolved_source_commit,
            )
        except RuntimeError as e:
            raise ValidationError(
                "Invalid source commit for promotion.",
                details={
                    "code": "APP_PROMOTION_SOURCE_COMMIT_INVALID",
                    "app_id": app_id,
                    "from_environment": normalized_from_env,
                    "source_commit": resolved_source_commit,
                },
            ) from e

        if not source_files:
            raise ValidationError(
                "Source commit does not contain app files for promotion.",
                details={
                    "code": "APP_PROMOTION_SOURCE_COMMIT_EMPTY",
                    "app_id": app_id,
                    "source_commit": resolved_source_commit,
                },
            )

        source_migration_paths = [
            path for path in source_files if path.startswith("migrations/") and path.endswith(_MIGRATION_UP_SUFFIX)
        ]
        self._validate_migration_order(app_id=app_id, migration_paths=source_migration_paths)

        if normalized_from_env == "test" and normalized_to_env == "prod":
            if current_state.test is None:
                raise ValidationError(
                    "Test deployment state is missing; cannot promote to prod.",
                    details={"code": "APP_PROMOTION_TEST_STATE_MISSING", "app_id": app_id},
                )
            if current_state.test != resolved_source_commit:
                raise ValidationError(
                    "Source commit must match current test deployment for prod promotion.",
                    details={
                        "code": "APP_PROMOTION_SOURCE_COMMIT_MISMATCH_TEST",
                        "app_id": app_id,
                        "source_commit": resolved_source_commit,
                        "test_deployed_commit": current_state.test,
                    },
                )
        warnings: list[str] = []
        if normalized_from_env == "dev":
            try:
                if has_uncommitted_changes(tenant_id=self.tenant_id, app_id=app_id, environment="dev"):
                    warnings.append(
                        "Dev workspace has uncommitted changes that differ from the committed snapshot being promoted."
                    )
            except RuntimeError:
                logger.warning("Failed to check uncommitted changes for app %s", app_id, exc_info=True)

        target_files = set(
            list_app_files(
                tenant_id=self.tenant_id,
                app_id=app_id,
                environment=normalized_to_env,
            )
        )
        source_file_set = set(source_files)
        dry_run_mode = bool(dry_run)
        removed_files = sorted(target_files - source_file_set)

        if not dry_run_mode:
            sync_environment_from_commit(
                tenant_id=self.tenant_id,
                app_id=app_id,
                source_environment="dev",
                target_environment=normalized_to_env,
                commit_sha=resolved_source_commit,
            )

        if dry_run_mode:
            migration_result = await self._preview_migrations_for_promotion(
                app_id=app_id,
                live_app=live_app,
                target_environment=normalized_to_env,
                source_files=source_files,
            )
        else:
            migration_result = await self._apply_migrations_for_promotion(
                app_id=app_id,
                live_app=live_app,
                target_environment=normalized_to_env,
            )

        payload_model = LiveAppPromotionPayload(
            app_id=app_id,
            from_environment=normalized_from_env,
            to_environment=normalized_to_env,
            promoted_files=len(source_files),
            removed_files=removed_files,
            source_commit=resolved_source_commit,
            dry_run=dry_run_mode,
            migrations=migration_result,
            deployment_state=(
                self._predicted_deployment_state(
                    current_state=current_state,
                    target_environment=normalized_to_env,
                    source_commit=resolved_source_commit,
                )
                if dry_run_mode
                else self._set_deployed_commit(
                    live_app=live_app,
                    environment=normalized_to_env,
                    source_commit=resolved_source_commit,
                )
            ),
            warnings=warnings,
        )
        payload = payload_model.to_dict()
        if not dry_run_mode:
            await self._record_audit_event(
                actor_user_id=actor_user_id,
                event_type=LiveAppAuditEventType.ENVIRONMENT_PROMOTE,
                payload=payload,
            )
        return payload

    async def get_deployment_state(self, app_id: int) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})
        return {
            "app_id": app_id,
            "deployment_state": self._deployment_state_from_live_app(live_app).to_dict(),
        }

    async def diff_environments(
        self,
        app_id: int,
        *,
        from_environment: str = "dev",
        to_environment: str = "prod",
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})

        normalized_from_env = self._normalize_environment(from_environment)
        normalized_to_env = self._normalize_environment(to_environment)
        if normalized_from_env == normalized_to_env:
            raise ValidationError(
                "Source and target environments must be different.",
                details={
                    "code": "APP_ENV_DIFF_INVALID_ENV",
                    "app_id": app_id,
                    "from_environment": normalized_from_env,
                    "to_environment": normalized_to_env,
                },
            )

        from_files = list_app_files(tenant_id=self.tenant_id, app_id=app_id, environment=normalized_from_env)
        to_files = list_app_files(tenant_id=self.tenant_id, app_id=app_id, environment=normalized_to_env)
        from_set = set(from_files)
        to_set = set(to_files)
        shared_paths = sorted(from_set & to_set)

        changed_files: list[dict[str, str]] = []
        for path in shared_paths:
            from_content = read_app_file(
                tenant_id=self.tenant_id,
                app_id=app_id,
                relative_path=path,
                environment=normalized_from_env,
            )
            to_content = read_app_file(
                tenant_id=self.tenant_id,
                app_id=app_id,
                relative_path=path,
                environment=normalized_to_env,
            )
            if from_content == to_content:
                continue
            changed_files.append(
                {
                    "path": path,
                    "from_sha256": hashlib.sha256(from_content.encode("utf-8")).hexdigest(),
                    "to_sha256": hashlib.sha256(to_content.encode("utf-8")).hexdigest(),
                }
            )

        deployment_state = self._deployment_state_from_live_app(live_app).to_dict()
        from_deployed_commit = deployment_state.get(normalized_from_env)
        to_deployed_commit = deployment_state.get(normalized_to_env)
        return {
            "app_id": app_id,
            "from_environment": normalized_from_env,
            "to_environment": normalized_to_env,
            "from_deployed_commit": from_deployed_commit,
            "to_deployed_commit": to_deployed_commit,
            "same_deployed_commit": from_deployed_commit is not None and from_deployed_commit == to_deployed_commit,
            "files": {
                "only_in_from": sorted(from_set - to_set),
                "only_in_to": sorted(to_set - from_set),
                "changed": changed_files,
            },
            "summary": {
                "from_files": len(from_files),
                "to_files": len(to_files),
                "only_in_from_count": len(from_set - to_set),
                "only_in_to_count": len(to_set - from_set),
                "changed_count": len(changed_files),
                "in_sync": len(from_set - to_set) == 0 and len(to_set - from_set) == 0 and len(changed_files) == 0,
            },
        }

    async def list_commits(
        self,
        app_id: int,
        *,
        environment: str = DEFAULT_LIVE_APP_ENVIRONMENT,
        limit: int = 20,
    ) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})
        normalized_env = self._normalize_environment(environment)
        self._ensure_dev_only_git_operation(
            app_id=app_id,
            environment=normalized_env,
            operation="list_commits",
        )
        max_items = max(1, min(int(limit), 100))
        try:
            commits = list_app_commits_for_environment(
                tenant_id=self.tenant_id,
                app_id=app_id,
                environment=normalized_env,
                limit=max_items,
            )
        except RuntimeError as e:
            raise InternalServiceError(f"Failed to list live app commits: {e}") from e
        return {"app_id": app_id, "environment": normalized_env, "commits": commits}

    async def list_promotions(self, app_id: int, *, limit: int = 20) -> dict:
        live_app = await self.repo.get_for_tenant(app_id=app_id, tenant_id=self.tenant_id)
        if not live_app:
            raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})

        max_items = max(1, min(int(limit), 100))
        events = await self.audit_repo.list_events(
            tenant_id=self.tenant_id,
            event_type=LiveAppAuditEventType.ENVIRONMENT_PROMOTE.value,
            limit=max_items * 3,
        )
        promotions: list[dict] = []
        for event in events:
            payload = event.payload or {}
            if payload.get("app_id") != app_id:
                continue
            promotions.append(
                LiveAppPromotionRecord(
                    created_at=None if event.created_at is None else event.created_at.isoformat(),
                    actor_user_id=event.actor_user_id,
                    from_environment=payload.get("from_environment"),
                    to_environment=payload.get("to_environment"),
                    source_commit=payload.get("source_commit"),
                    promoted_files=int(payload.get("promoted_files", 0)),
                    removed_files=list(payload.get("removed_files", [])),
                    migrations=LiveAppPromotionMigrationSummary.from_mapping(payload.get("migrations")),
                ).to_dict()
            )
            if len(promotions) >= max_items:
                break
        return {"app_id": app_id, "promotions": promotions}

    def _validate_query_sql_scope(self, *, app_id: int, sql: str, schema_name: str) -> None:
        raw_sql = (sql or "").strip()
        if not raw_sql:
            raise ValidationError(
                "SQL is required for live app query.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )
        if not raw_sql.lower().startswith("select"):
            raise ValidationError(
                "Only SELECT queries are allowed for live app query endpoint.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )
        if _FORBIDDEN_SQL_PATTERNS.search(raw_sql):
            raise ValidationError(
                "Forbidden SQL keyword in query.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )

        namespaces = {match.group(1).lower() for match in _NAMESPACE_PATTERN.finditer(raw_sql)}
        if namespaces and any(ns != schema_name for ns in namespaces):
            raise ValidationError(
                "Query references namespace outside the app scope.",
                details={"code": "APP_NAMESPACE_VIOLATION", "app_id": app_id, "expected_namespace": schema_name},
            )

    def _resolve_app_table_name(self, *, app_id: int, table: str, environment: str) -> str:
        raw = (table or "").strip()
        if not raw:
            raise ValidationError(
                "Table is required for mutation.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )
        allowed_schema = self._schema_for_environment(app_id=app_id, environment=environment)
        if "." in raw:
            schema, name = raw.split(".", maxsplit=1)
            schema = schema.strip()
            name = name.strip()
        else:
            schema, name = allowed_schema, raw

        if schema != allowed_schema:
            raise ValidationError(
                "Mutation targets table outside app namespace.",
                details={"code": "APP_NAMESPACE_VIOLATION", "app_id": app_id, "expected_namespace": allowed_schema},
            )
        if not _IDENTIFIER_PATTERN.match(schema) or not _IDENTIFIER_PATTERN.match(name):
            raise ValidationError(
                "Invalid table identifier for mutation.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )
        return f"{schema}.{name}"

    def _resolve_app_import_table_name(self, *, app_id: int, table: str, environment: str) -> str:
        raw = (table or "").strip()
        if not raw:
            raise ValidationError(
                "Table is required for import.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )
        allowed_schema = self._schema_for_environment(app_id=app_id, environment=environment)
        if "." in raw:
            schema, name = raw.split(".", maxsplit=1)
            schema = schema.strip()
            name = name.strip()
        else:
            schema, name = allowed_schema, raw

        if schema != allowed_schema:
            raise ValidationError(
                "Import targets table outside app namespace.",
                details={"code": "APP_IMPORT_TARGET_FORBIDDEN", "app_id": app_id, "expected_namespace": allowed_schema},
            )
        if not _IDENTIFIER_PATTERN.match(schema) or not _IDENTIFIER_PATTERN.match(name):
            raise ValidationError(
                "Invalid table identifier for import.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )
        return f"{schema}.{name}"

    def _normalize_mutation_rows(self, *, app_id: int, data: dict | list[dict]) -> list[dict]:
        if isinstance(data, dict):
            rows = [data]
        elif isinstance(data, list):
            rows = data
        else:
            raise ValidationError(
                "Mutation data must be an object or array of objects.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )
        if not rows:
            raise ValidationError(
                "Mutation data cannot be empty.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )
        if any(not isinstance(row, dict) or not row for row in rows):
            raise ValidationError(
                "Each mutation row must be a non-empty object.",
                details={"code": "APP_INVALID_SQL", "app_id": app_id},
            )
        return rows

    def _collect_local_migrations(self, *, app_id: int, environment: str) -> list[LiveAppMigration]:
        files = list_app_files(tenant_id=self.tenant_id, app_id=app_id, environment=environment)
        migration_paths = [
            path for path in files if path.startswith("migrations/") and path.endswith(_MIGRATION_UP_SUFFIX)
        ]
        migration_paths.sort()
        self._validate_migration_order(app_id=app_id, migration_paths=migration_paths)
        down_path_set = set(
            path for path in files if path.startswith("migrations/") and path.endswith(_MIGRATION_DOWN_SUFFIX)
        )
        result: list[LiveAppMigration] = []
        for path in migration_paths:
            sql = read_app_file(
                tenant_id=self.tenant_id,
                app_id=app_id,
                relative_path=path,
                environment=environment,
            )
            name = Path(path).name.removesuffix(_MIGRATION_UP_SUFFIX)
            down_path = path.removesuffix(_MIGRATION_UP_SUFFIX) + _MIGRATION_DOWN_SUFFIX
            down_sql = (
                read_app_file(
                    tenant_id=self.tenant_id,
                    app_id=app_id,
                    relative_path=down_path,
                    environment=environment,
                )
                if down_path in down_path_set
                else None
            )
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            result.append(
                LiveAppMigration(
                    name=name,
                    path=path,
                    down_path=down_path if down_path in down_path_set else None,
                    checksum=checksum,
                    up_sql=sql,
                    down_sql=down_sql,
                )
            )
        return result

    def _find_local_migration(self, *, app_id: int, migration_name: str, environment: str) -> LiveAppMigration | None:
        for item in self._collect_local_migrations(app_id=app_id, environment=environment):
            if item.name == migration_name:
                return item
        return None

    def _get_local_migration(self, *, app_id: int, migration_name: str, environment: str) -> LiveAppMigration:
        result = self._find_local_migration(app_id=app_id, migration_name=migration_name, environment=environment)
        if result is not None:
            return result
        raise ValidationError(
            "Migration file not found in app workspace.",
            details={"code": "APP_MIGRATION_NOT_FOUND", "app_id": app_id, "migration": migration_name},
        )

    def _validate_migration_order(self, *, app_id: int, migration_paths: list[str]) -> None:
        if not migration_paths:
            return

        names = [Path(path).name.removesuffix(_MIGRATION_UP_SUFFIX) for path in migration_paths]
        if len(names) != len(set(names)):
            raise ValidationError(
                "Duplicate migration names detected.",
                details={"code": "APP_MIGRATION_ORDER_INVALID", "app_id": app_id},
            )

        parsed_sequences: list[tuple[int, str]] = []
        for name in names:
            match = _MIGRATION_SEQUENCE_PATTERN.match(name)
            if match:
                parsed_sequences.append((int(match.group(1)), name))
            else:
                parsed_sequences.append((-1, name))

        if any(seq == -1 for seq, _ in parsed_sequences):
            if any(seq != -1 for seq, _ in parsed_sequences):
                raise ValidationError(
                    "Migration sequence naming must be consistent (all prefixed or none).",
                    details={"code": "APP_MIGRATION_ORDER_INVALID", "app_id": app_id},
                )
            return

        ordered = sorted(parsed_sequences, key=lambda item: item[0])
        for idx in range(1, len(ordered)):
            previous_seq = ordered[idx - 1][0]
            current_seq = ordered[idx][0]
            if current_seq != previous_seq + 1:
                raise ValidationError(
                    "Migration sequence has gaps or duplicates.",
                    details={"code": "APP_MIGRATION_ORDER_INVALID", "app_id": app_id},
                )

    def _normalize_migration_name(self, *, app_id: int, migration_name: str) -> str:
        normalized = (migration_name or "").strip()
        if not normalized or not _MIGRATION_NAME_PATTERN.match(normalized):
            raise ValidationError(
                "Invalid migration name.",
                details={"code": "APP_MIGRATION_INVALID", "app_id": app_id, "migration": migration_name},
            )
        return normalized

    def _normalize_environment(self, environment: str) -> str:
        normalized = (environment or "").strip().lower()
        if normalized not in ALLOWED_LIVE_APP_ENVIRONMENTS:
            raise ValidationError(
                "Invalid live app environment.",
                details={"code": "APP_INVALID_ENVIRONMENT", "environment": environment},
            )
        return normalized

    def _schema_for_environment(self, *, app_id: int, environment: str) -> str:
        if environment == "prod":
            return f"app_{app_id}"
        return f"app_{app_id}_{environment}"

    def _validate_environment_promotion(self, *, app_id: int, from_environment: str, to_environment: str) -> None:
        allowed_transitions = {
            "dev": "test",
            "test": "prod",
        }
        expected_next = allowed_transitions.get(from_environment)
        if expected_next != to_environment:
            raise ValidationError(
                "Invalid live app environment promotion path.",
                details={
                    "code": "APP_INVALID_ENV_PROMOTION",
                    "app_id": app_id,
                    "from_environment": from_environment,
                    "to_environment": to_environment,
                    "allowed_transitions": [{"from": "dev", "to": "test"}, {"from": "test", "to": "prod"}],
                },
            )

    def _ensure_dev_only_git_operation(self, *, app_id: int, environment: str, operation: str) -> None:
        if environment == "dev":
            return
        raise ValidationError(
            "Git history is managed in dev environment only.",
            details={
                "code": "APP_GIT_DEV_ONLY",
                "app_id": app_id,
                "environment": environment,
                "operation": operation,
            },
        )

    def _deployment_state_from_live_app(self, live_app) -> LiveAppDeploymentState:
        config = LiveAppConfig.from_mapping(live_app.app_config)
        return config.deployed_commits

    def _predicted_deployment_state(
        self,
        *,
        current_state: LiveAppDeploymentState,
        target_environment: str,
        source_commit: str,
    ) -> LiveAppDeploymentState:
        return current_state.with_environment(environment=target_environment, commit=source_commit)

    def _set_deployed_commit(self, *, live_app, environment: str, source_commit: str) -> LiveAppDeploymentState:
        config = LiveAppConfig.from_mapping(live_app.app_config)
        updated = config.with_deployed_commit(environment=environment, commit=source_commit)
        live_app.app_config = updated.to_dict()
        return updated.deployed_commits

    async def _apply_migrations_for_promotion(
        self, *, app_id: int, live_app, target_environment: str
    ) -> LiveAppPromotionMigrationSummary:
        local_migrations = self._collect_local_migrations(app_id=app_id, environment=target_environment)
        if live_app.data_source_id is None:
            raise InternalServiceError(
                "Live app data source is not configured.",
                details={"code": "APP_RUNTIME_BROKEN", "app_id": app_id},
            )
        schema_name = self._schema_for_environment(app_id=app_id, environment=target_environment)
        applied_names: list[str] = []
        skipped_names: list[str] = []
        for migration in local_migrations:
            try:
                result = await self.data_executor.apply_migration(
                    data_source_id=live_app.data_source_id,
                    schema_name=schema_name,
                    migration_name=migration.name,
                    checksum=migration.checksum,
                    up_sql=migration.up_sql,
                )
            except ValueError as e:
                raise ValidationError(
                    "Migration conflicts with applied history during promotion.",
                    details={"code": "APP_MIGRATION_CONFLICT", "app_id": app_id, "migration": migration.name},
                ) from e
            except Exception as e:
                raise ValidationError(
                    "Failed to apply migration during promotion.",
                    details={"code": "APP_MIGRATION_APPLY_FAILED", "app_id": app_id, "migration": migration.name},
                ) from e

            if result.get("applied"):
                applied_names.append(migration.name)
            else:
                skipped_names.append(migration.name)

        return LiveAppPromotionMigrationSummary(
            enabled=True,
            schema=schema_name,
            total=len(local_migrations),
            mode="apply",
            status="success",
            applied=applied_names,
            skipped=skipped_names,
            reason="applied",
        )

    async def _preview_migrations_for_promotion(
        self,
        *,
        app_id: int,
        live_app,
        target_environment: str,
        source_files: list[str],
    ) -> LiveAppPromotionMigrationSummary:
        migration_names: list[str] = []
        for path in sorted(source_files):
            if path.startswith("migrations/") and path.endswith(_MIGRATION_UP_SUFFIX):
                migration_names.append(Path(path).name.removesuffix(_MIGRATION_UP_SUFFIX))

        if live_app.data_source_id is None:
            raise InternalServiceError(
                "Live app data source is not configured.",
                details={"code": "APP_RUNTIME_BROKEN", "app_id": app_id},
            )

        schema_name = self._schema_for_environment(app_id=app_id, environment=target_environment)
        applied = await self.data_executor.list_applied_migrations(
            data_source_id=live_app.data_source_id,
            schema_name=schema_name,
        )
        applied_set = {str(item["name"]) for item in applied}
        pending = [name for name in migration_names if name not in applied_set]
        already_applied = [name for name in migration_names if name in applied_set]
        return LiveAppPromotionMigrationSummary(
            enabled=True,
            schema=schema_name,
            total=len(migration_names),
            mode="dry_run",
            status="success",
            pending=pending,
            already_applied=already_applied,
            reason="dry_run",
        )

    def _write_content_no_commit(
        self,
        *,
        new_content: str,
        read_current,
        write_new,
    ) -> dict[str, bool]:
        try:
            current = read_current()
            if current == new_content:
                return {"updated": False, "committed": False}
        except FileNotFoundError:
            pass

        write_new(new_content)
        return {"updated": True, "committed": False}

    async def _resolve_live_app_data_source_id(self, requested_data_source_id: int | None) -> int:
        if requested_data_source_id is not None:
            selected = await self.data_source_repo.get_by_id_and_tenant(
                data_source_id=requested_data_source_id,
                tenant_id=self.tenant_id,
            )
            if selected is None:
                raise ValidationError(
                    "Data source not found for tenant.",
                    details={"code": "APP_DATASOURCE_NOT_FOUND", "data_source_id": requested_data_source_id},
                )
            if not selected.managed:
                raise ValidationError(
                    "Live app requires a managed data source.",
                    details={"code": "APP_DATASOURCE_NOT_MANAGED", "data_source_id": requested_data_source_id},
                )
            return int(selected.id)

        data_sources = await self.data_source_repo.list_by_tenant(self.tenant_id)
        for candidate in data_sources:
            if candidate.managed:
                return int(candidate.id)

        raise ValidationError(
            "No managed data source is available for this tenant.",
            details={"code": "APP_MANAGED_DATASOURCE_REQUIRED"},
        )

    def _bootstrap_app_workspace(self, *, app_id: int, entry_file: str) -> None:
        for environment in sorted(ALLOWED_LIVE_APP_ENVIRONMENTS):
            ensure_entry_file(
                tenant_id=self.tenant_id,
                app_id=app_id,
                entry_file=entry_file,
                environment=environment,
            )

    async def _ensure_environment_schemas(self, *, app_id: int, data_source_id: int) -> None:
        for environment in sorted(ALLOWED_LIVE_APP_ENVIRONMENTS):
            schema_name = self._schema_for_environment(app_id=app_id, environment=environment)
            try:
                await self.data_executor.ensure_schema(
                    data_source_id=data_source_id,
                    schema_name=schema_name,
                )
            except Exception as e:
                raise InternalServiceError(
                    "Failed to initialize live app environment schema.",
                    details={
                        "code": "APP_SCHEMA_INIT_FAILED",
                        "app_id": app_id,
                        "environment": environment,
                        "schema_name": schema_name,
                    },
                ) from e

    async def _record_audit_event(
        self,
        *,
        actor_user_id: int | None,
        event_type: LiveAppAuditEventType,
        payload: dict,
    ) -> None:
        try:
            async with self.db_session.begin_nested():
                await self.audit_repo.add_event(
                    tenant_id=self.tenant_id,
                    actor_user_id=actor_user_id,
                    event_type=event_type,
                    payload=payload,
                )
        except Exception:
            # Keep write flow available even if audit persistence is temporarily unavailable.
            logger.warning("Failed to persist live app audit event", exc_info=True)
