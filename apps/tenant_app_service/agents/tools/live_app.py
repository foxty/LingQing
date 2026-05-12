"""Agent tools for live app entry operations."""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.shared.live_app.service import LiveAppService
from apps.shared.live_app.workspace import get_app_path
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_rbac import tool_rbac_denied
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)
_DEFAULT_PREVIEW_ENVIRONMENT = "dev"


def _actor_ctx(config: RunnableConfig) -> ActorContext:
    runtime = extract_runtime_context(config)
    return ActorContext(
        tenant_id=runtime.user.tenant_id,
        user_id=runtime.user.user_id,
        user_role=runtime.user.role,
    )


class WriteAppFileSchema(BaseModel):
    """Schema for write_app_file tool arguments."""

    app_id: int = Field(..., description="Target live app identifier.")
    path: str = Field(..., min_length=1, description="Relative file path inside app workspace.")
    content: str | None = Field(
        default=None,
        description="Required full file content to write. Provide complete new file body, not a diff.",
        json_schema_extra={"example": "<!doctype html><html><body>Hello</body></html>"},
    )


class PatchAppFileSchema(BaseModel):
    """Schema for patch_app_file tool arguments."""

    app_id: int = Field(..., description="Target live app identifier.")
    path: str = Field(..., min_length=1, description="Relative file path inside app workspace.")
    old_text: str = Field(
        ...,
        min_length=1,
        description=(
            "Exact text to find in the file. Must match uniquely (exactly one occurrence). "
            "Include enough surrounding context to avoid ambiguity."
        ),
    )
    new_text: str = Field(
        ...,
        description="Replacement text that will substitute old_text in the file.",
    )


def _live_app_preview_url(app_id: int, environment: str = "prod") -> str:
    return f"/api/apps/{app_id}/{environment}/embed"


@tool
async def create_live_app(
    name: str,
    config: RunnableConfig,
    description: str = "",
    data_source_id: int | None = None,
) -> ToolResult:
    """Create one live app and bootstrap workspace lifecycle.

    Args:
        name: Live app display name (must be unique within the tenant).
        config: Agent runtime config carrying tenant/user/thread context.
        description: Optional live app description.
        data_source_id: Optional analytics data source bound to this app.
    """
    try:
        runtime = extract_runtime_context(config)
        async with app_db_session() as db_session:
            denied = await tool_rbac_denied(
                db_session,
                runtime.user.tenant_id,
                runtime.user.role,
                TenantAppPermissions.APPS_WRITE,
                denied_message="You do not have permission to create live apps",
            )
            if denied:
                return denied

            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            created = await service.create_app_with_artifact(
                name=name,
                description=description or None,
                owner_id=runtime.user.user_id,
                data_source_id=data_source_id,
                thread_id=runtime.thread_id,
            )
            record = created.app
            linked_artifact = created.artifact
            if linked_artifact is None:
                return ToolResult.error_result(
                    "Failed to resolve linked artifact for the created app.",
                    code="LIVE_APP_ARTIFACT_NOT_FOUND",
                )
            artifact_payload = linked_artifact.model_dump()
            payload = record.model_dump()
            payload["preview_url"] = _live_app_preview_url(record.app_id, environment=_DEFAULT_PREVIEW_ENVIRONMENT)
            payload["artifact"] = artifact_payload
            return ToolResult.success(payload)
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_CREATE_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to create live app")
        return ToolResult.error_result(f"Failed to create live app: {e}", code="LIVE_APP_CREATE_FAILED")


@tool
async def list_live_apps(config: RunnableConfig) -> ToolResult:
    """List live apps for current tenant.

    Args:
        config: Agent runtime config carrying tenant/user/thread context.
    """
    try:
        runtime = extract_runtime_context(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            records = await service.list_apps_for_actor(actor=_actor_ctx(config))
            payload = records.model_dump()
            for app_item in payload.get("apps", []):
                app_id = app_item.get("app_id")
                if isinstance(app_id, int):
                    app_item["preview_url"] = _live_app_preview_url(app_id, environment=_DEFAULT_PREVIEW_ENVIRONMENT)
            return ToolResult.success(payload)
    except Exception as e:
        logger.exception("Failed to list live apps")
        return ToolResult.error_result(f"Failed to list live apps: {e}", code="LIVE_APP_LIST_FAILED")


@tool
async def get_live_app(app_id: int, config: RunnableConfig) -> ToolResult:
    """Get live app metadata with development context for current tenant.

    Returns app info plus dev workspace context: file list, migration status,
    deployment state, and recent commits — sufficient to resume work without
    additional discovery calls.

    Args:
        app_id: Target live app identifier.
        config: Agent runtime config carrying tenant/user/thread context.
    """
    try:
        runtime = extract_runtime_context(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            record = await service.get_app_for_actor(app_id=app_id, actor=_actor_ctx(config))
            payload = record.model_dump()
            payload["preview_url"] = _live_app_preview_url(record.app_id, environment=_DEFAULT_PREVIEW_ENVIRONMENT)
            actor = _actor_ctx(config)

            dev_context: dict = {}
            try:
                files_result = await service.list_files_for_actor(
                    app_id=app_id,
                    actor=actor,
                    environment="dev",
                )
                dev_context["files"] = files_result.get("files", [])
            except Exception:
                dev_context["files"] = None

            try:
                migrations_result = await service.list_migrations_for_actor(
                    app_id=app_id,
                    actor=actor,
                    environment="dev",
                )
                dev_context["migrations"] = migrations_result.get("migrations", [])
            except Exception:
                dev_context["migrations"] = None

            try:
                commits_result = await service.list_commits_for_actor(
                    app_id=app_id,
                    actor=actor,
                    environment="dev",
                    limit=5,
                )
                dev_context["recent_commits"] = commits_result.get("commits", [])
            except Exception:
                dev_context["recent_commits"] = None

            payload["dev_context"] = dev_context
            return ToolResult.success(payload)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_GET_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to get live app")
        return ToolResult.error_result(f"Failed to get live app: {e}", code="LIVE_APP_GET_FAILED")


@tool
async def list_app_files(app_id: int, config: RunnableConfig, environment: str = "dev") -> ToolResult:
    """List all files under a live app workspace.

    Args:
        app_id: Target live app identifier.
        config: Agent runtime config carrying tenant/user/thread context.
        environment: App environment to inspect ("dev", "test", or "prod").
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.list_files_for_actor(
                app_id=app_id,
                actor=actor,
                environment=environment,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except Exception as e:
        logger.exception("Failed to list live app files")
        return ToolResult.error_result(f"Failed to list app files: {e}", code="LIVE_APP_LIST_FILES_FAILED")


@tool
async def grep_app_files(
    app_id: int,
    pattern: str,
    config: RunnableConfig,
    environment: str = "dev",
    case_insensitive: bool = False,
    max_matches: int = 100,
) -> ToolResult:
    r"""Search app workspace file contents with a Python regex (multiline per file).

    Scans allowed text-like files (html, js, css, json, sql, md) under the environment
    root. Skips very large files.

    Args:
        app_id: Target live app identifier.
        pattern: Regex (Python ``re`` syntax), e.g. ``mutateInsert`` or ``\bfoo\b``.
        config: Agent runtime config carrying tenant/user/thread context.
        environment: Workspace to search: dev, test, or prod.
        case_insensitive: If true, use case-insensitive matching.
        max_matches: Stop after this many matches (capped at 500).
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.grep_files_for_actor(
                app_id=app_id,
                actor=actor,
                pattern=pattern,
                environment=environment,
                case_insensitive=case_insensitive,
                max_matches=max_matches,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_GREP_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to grep live app files")
        return ToolResult.error_result(f"Failed to grep app files: {e}", code="LIVE_APP_GREP_FAILED")


@tool
async def read_app_file(
    app_id: int,
    path: str,
    config: RunnableConfig,
    environment: str = "dev",
    start_line: int | None = None,
    end_line: int | None = None,
) -> ToolResult:
    """Read one file from live app workspace by relative path.

    Supports optional line-range reading: pass start_line and/or end_line to read
    a subset of the file. Line numbers are 1-based (line 1 = first line).
    When omitted, the entire file is returned.

    Args:
        app_id: Target live app identifier.
        path: Relative file path inside app workspace (for example "src/main.js").
        config: Agent runtime config carrying tenant/user/thread context.
        environment: App environment to read from ("dev", "test", or "prod").
        start_line: Optional 1-based start line (inclusive). Defaults to 1 (beginning).
        end_line: Optional 1-based end line (inclusive). Defaults to last line of file.
    """
    try:
        runtime = extract_runtime_context(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.read_file_for_actor(
                app_id=app_id,
                path=path,
                actor=_actor_ctx(config),
                environment=environment,
            )

            # Apply line-range slicing when requested
            if start_line is not None or end_line is not None:
                content = result.get("content", "")
                all_lines = content.splitlines()
                total_lines = len(all_lines)

                # Normalize bounds (1-based → 0-based)
                s = max((start_line or 1) - 1, 0)
                e = end_line if end_line is not None else total_lines
                e = min(e, total_lines)

                if s >= total_lines:
                    return ToolResult.error_result(
                        f"start_line {start_line} exceeds file length ({total_lines} lines).",
                        code="LIVE_APP_FILE_LINE_OUT_OF_RANGE",
                        metadata={"total_lines": total_lines},
                    )
                if s >= e:
                    return ToolResult.error_result(
                        f"start_line ({start_line}) must be less than or equal to end_line ({end_line}).",
                        code="LIVE_APP_FILE_INVALID_LINE_RANGE",
                        metadata={"total_lines": total_lines},
                    )

                sliced_lines = all_lines[s:e]
                result["content"] = "\n".join(sliced_lines)
                result["total_lines"] = total_lines
                result["start_line"] = s + 1
                result["end_line"] = min(e, total_lines)

            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app or file not found", code="LIVE_APP_FILE_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_FILE_READ_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to read live app file")
        return ToolResult.error_result(f"Failed to read app file: {e}", code="LIVE_APP_READ_FILE_FAILED")


@tool(args_schema=WriteAppFileSchema)
async def write_app_file(
    app_id: int,
    path: str,
    content: str | None,
    config: RunnableConfig,
) -> ToolResult:
    """Write one file under live app workspace dev environment by relative path.

    Always writes to the dev environment. Use promote_app_environment to
    propagate changes to test or prod.

    Args:
        app_id: Target live app identifier.
        path: Relative file path inside app workspace (for example "src/main.js").
        content: Full file content to write. Must be provided; empty string is allowed intentionally.
        config: Agent runtime config carrying tenant/user/thread context.
    """
    if content is None:
        return ToolResult.error_result(
            "Missing required parameter 'content'. Provide full file content to write.",
            code="LIVE_APP_FILE_WRITE_CONTENT_REQUIRED",
        )
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.write_file_for_actor(
                app_id=app_id,
                path=path,
                content=content,
                actor=actor,
                environment="dev",
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_FILE_WRITE_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to write live app file")
        return ToolResult.error_result(f"Failed to write app file: {e}", code="LIVE_APP_WRITE_FILE_FAILED")


@tool(args_schema=PatchAppFileSchema)
async def patch_app_file(
    app_id: int,
    path: str,
    old_text: str,
    new_text: str,
    config: RunnableConfig,
) -> ToolResult:
    """Apply a targeted find-and-replace patch to one file under live app dev workspace.

    Reads the current file, verifies ``old_text`` occurs exactly once, replaces it
    with ``new_text``, and writes the result back. This is more token-efficient than
    ``write_app_file`` for small edits because you only send the changed fragment.

    Always operates on the dev environment. Use promote_app_environment to
    propagate changes to test or prod.

    Args:
        app_id: Target live app identifier.
        path: Relative file path inside app workspace (for example "src/main.js").
        old_text: Exact text to find. Must appear exactly once in the file.
        new_text: Replacement text (can be empty string to delete the matched region).
        config: Agent runtime config carrying tenant/user/thread context.
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)

            # Read current content from dev
            read_result = await service.read_file_for_actor(
                app_id=app_id,
                path=path,
                actor=actor,
                environment="dev",
            )
            current_content: str = read_result.get("content", "")

            # Validate uniqueness
            occurrence_count = current_content.count(old_text)
            if occurrence_count == 0:
                return ToolResult.error_result(
                    "old_text not found in file. Ensure the text matches exactly, "
                    "including whitespace and indentation.",
                    code="LIVE_APP_PATCH_TEXT_NOT_FOUND",
                    metadata={"path": path, "file_length": len(current_content)},
                )
            if occurrence_count > 1:
                return ToolResult.error_result(
                    f"old_text matched {occurrence_count} times. "
                    "Include more surrounding context so the match is unique.",
                    code="LIVE_APP_PATCH_TEXT_AMBIGUOUS",
                    metadata={"path": path, "occurrences": occurrence_count},
                )

            # Apply replacement
            patched_content = current_content.replace(old_text, new_text, 1)

            # Write back to dev
            write_result = await service.write_file_for_actor(
                app_id=app_id,
                path=path,
                content=patched_content,
                actor=actor,
                environment="dev",
            )

            payload = {
                **write_result,
                "patch_applied": True,
                "old_length": len(current_content),
                "new_length": len(patched_content),
            }
            return ToolResult.success(payload)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app or file not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_FILE_PATCH_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to patch live app file")
        return ToolResult.error_result(f"Failed to patch app file: {e}", code="LIVE_APP_PATCH_FILE_FAILED")


@tool
async def list_db_migrations(app_id: int, config: RunnableConfig, environment: str = "dev") -> ToolResult:
    """List database migrations with local/applied status.

    Args:
        app_id: Target live app identifier.
        config: Agent runtime config carrying tenant/user/thread context.
        environment: App environment whose migrations are inspected.
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.list_migrations_for_actor(
                app_id=app_id,
                actor=actor,
                environment=environment,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_MIGRATION_LIST_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to list db migrations")
        return ToolResult.error_result(f"Failed to list db migrations: {e}", code="LIVE_APP_LIST_MIGRATIONS_FAILED")


@tool
async def apply_db_migration(
    app_id: int, migration_name: str, config: RunnableConfig, environment: str = "dev"
) -> ToolResult:
    """Apply one database migration by name.

    Args:
        app_id: Target live app identifier.
        migration_name: Migration base name without suffix.
        config: Agent runtime config carrying tenant/user/thread context.
        environment: App environment where migration is applied.
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.apply_migration_for_actor(
                app_id=app_id,
                migration_name=migration_name,
                actor=actor,
                environment=environment,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_MIGRATION_APPLY_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to apply db migration")
        return ToolResult.error_result(f"Failed to apply db migration: {e}", code="LIVE_APP_APPLY_MIGRATION_FAILED")


@tool
async def rollback_db_migration(
    app_id: int, migration_name: str, config: RunnableConfig, environment: str = "dev"
) -> ToolResult:
    """Rollback one database migration by name.

    Args:
        app_id: Target live app identifier.
        migration_name: Migration base name without suffix.
        config: Agent runtime config carrying tenant/user/thread context.
        environment: App environment where migration is rolled back.
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.rollback_migration_for_actor(
                app_id=app_id,
                migration_name=migration_name,
                actor=actor,
                environment=environment,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_MIGRATION_ROLLBACK_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to rollback db migration")
        return ToolResult.error_result(
            f"Failed to rollback db migration: {e}",
            code="LIVE_APP_ROLLBACK_MIGRATION_FAILED",
        )


@tool
async def create_db_migration(
    app_id: int,
    migration_name: str,
    up_sql: str,
    config: RunnableConfig,
    down_sql: str = "",
    environment: str = "dev",
) -> ToolResult:
    """Create one database migration pair in workspace.

    Args:
        app_id: Target live app identifier.
        migration_name: Migration logical name used to build file names.
        up_sql: SQL to execute when applying the migration.
        config: Agent runtime config carrying tenant/user/thread context.
        down_sql: Optional SQL to execute when rolling back the migration.
        environment: App environment where migration files are created.
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.create_migration_for_actor(
                app_id=app_id,
                migration_name=migration_name,
                up_sql=up_sql,
                actor=actor,
                environment=environment,
                down_sql=down_sql or None,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_MIGRATION_CREATE_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to create db migration")
        return ToolResult.error_result(f"Failed to create db migration: {e}", code="LIVE_APP_CREATE_MIGRATION_FAILED")


@tool
async def remove_db_migration(
    app_id: int, migration_name: str, config: RunnableConfig, environment: str = "dev"
) -> ToolResult:
    """Remove one database migration pair from workspace.

    Args:
        app_id: Target live app identifier.
        migration_name: Migration base name without suffix.
        config: Agent runtime config carrying tenant/user/thread context.
        environment: App environment where migration files are removed.
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.remove_migration_for_actor(
                app_id=app_id,
                migration_name=migration_name,
                actor=actor,
                environment=environment,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_MIGRATION_REMOVE_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to remove db migration")
        return ToolResult.error_result(f"Failed to remove db migration: {e}", code="LIVE_APP_REMOVE_MIGRATION_FAILED")


@tool
async def commit_app_changes(
    app_id: int,
    config: RunnableConfig,
    environment: str = "dev",
    message: str = "",
) -> ToolResult:
    """Commit app file changes for one environment.

    Requires app.status.md in the workspace — the commit will be rejected without it.
    Write app.status.md before committing with: current progress, architecture notes,
    key decisions, and open issues.

    Args:
        app_id: Target live app identifier.
        config: Agent runtime config carrying tenant/user/thread context.
        environment: App environment to commit (dev-only in current service policy).
        message: Optional custom commit message.
    """
    try:
        runtime = extract_runtime_context(config)
        app_path = get_app_path(runtime.user.tenant_id, app_id, environment=environment)
        if not (app_path / "app.status.md").exists():
            return ToolResult.error_result(
                "app.status.md is missing. Write it before committing — include current progress, "
                "architecture overview, key decisions, and open issues.",
                code="LIVE_APP_STATUS_REQUIRED",
            )

        async with app_db_session() as db_session:
            actor = _actor_ctx(config)
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.commit_changes_for_actor(
                app_id=app_id,
                actor=actor,
                environment=environment,
                commit_message=message or None,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_COMMIT_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to commit app changes")
        return ToolResult.error_result(f"Failed to commit app changes: {e}", code="LIVE_APP_COMMIT_FAILED")


@tool
async def validate_live_app(
    app_id: int,
    config: RunnableConfig,
    environment: str = _DEFAULT_PREVIEW_ENVIRONMENT,
) -> ToolResult:
    """Preflight validation before promotion: checks entry file, SQL syntax, and migration state.

    Args:
        app_id: Target live app identifier.
        config: Agent runtime config carrying tenant/user/thread context.
        environment: Environment to validate (default: dev).
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.validate_app_for_actor(
                app_id=app_id,
                actor=actor,
                environment=environment,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to validate live app")
        return ToolResult.error_result(f"Failed to validate live app: {e}", code="LIVE_APP_VALIDATION_FAILED")


@tool
async def promote_app_environment(
    app_id: int,
    from_environment: str,
    to_environment: str,
    config: RunnableConfig,
    source_commit: str = "",
    dry_run: bool = False,
) -> ToolResult:
    """Promote app environment in fixed order: dev->test->prod.

    Args:
        app_id: Target live app identifier.
        from_environment: Source environment for promotion.
        to_environment: Target environment for promotion.
        config: Agent runtime config carrying tenant/user/thread context.
        source_commit: Optional explicit source commit; required for some promotion paths.
        dry_run: Whether to preview promotion effects without persisting changes.
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.promote_environment_for_actor(
                app_id=app_id,
                actor=actor,
                from_environment=from_environment,
                to_environment=to_environment,
                source_commit=source_commit or None,
                dry_run=dry_run,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_PROMOTION_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to promote app environment")
        return ToolResult.error_result(f"Failed to promote app environment: {e}", code="LIVE_APP_PROMOTION_FAILED")


@tool
async def list_app_commits(
    app_id: int,
    config: RunnableConfig,
    environment: str = "dev",
    limit: int = 20,
) -> ToolResult:
    """List recent commits for one app environment.

    Args:
        app_id: Target live app identifier.
        config: Agent runtime config carrying tenant/user/thread context.
        environment: App environment to inspect commits from.
        limit: Maximum number of commits to return.
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.list_commits_for_actor(
                app_id=app_id,
                actor=actor,
                environment=environment,
                limit=limit,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_LIST_COMMITS_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to list app commits")
        return ToolResult.error_result(f"Failed to list app commits: {e}", code="LIVE_APP_LIST_COMMITS_FAILED")


@tool
async def list_app_promotions(
    app_id: int,
    config: RunnableConfig,
    limit: int = 20,
) -> ToolResult:
    """List promotion history for one app.

    Args:
        app_id: Target live app identifier.
        config: Agent runtime config carrying tenant/user/thread context.
        limit: Maximum number of promotion records to return.
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.list_promotions_for_actor(app_id=app_id, actor=actor, limit=limit)
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_LIST_PROMOTIONS_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to list app promotions")
        return ToolResult.error_result(f"Failed to list app promotions: {e}", code="LIVE_APP_LIST_PROMOTIONS_FAILED")


@tool
async def get_app_deployment_state(
    app_id: int,
    config: RunnableConfig,
) -> ToolResult:
    """Get current deployed commit pointers for dev/test/prod.

    Args:
        app_id: Target live app identifier.
        config: Agent runtime config carrying tenant/user/thread context.
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.get_deployment_state_for_actor(app_id=app_id, actor=actor)
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_DEPLOYMENT_STATE_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to get app deployment state")
        return ToolResult.error_result(
            f"Failed to get app deployment state: {e}",
            code="LIVE_APP_DEPLOYMENT_STATE_FAILED",
        )


@tool
async def diff_app_environments(
    app_id: int,
    config: RunnableConfig,
    from_environment: str = "dev",
    to_environment: str = "prod",
) -> ToolResult:
    """Diff two live app environments and return file-level drift summary.

    Args:
        app_id: Target live app identifier.
        config: Agent runtime config carrying tenant/user/thread context.
        from_environment: Baseline environment to compare from.
        to_environment: Target environment to compare against.
    """
    try:
        runtime = extract_runtime_context(config)
        actor = _actor_ctx(config)
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            result = await service.diff_environments_for_actor(
                app_id=app_id,
                actor=actor,
                from_environment=from_environment,
                to_environment=to_environment,
            )
            return ToolResult.success(result)
    except ResourceNotFoundError:
        return ToolResult.error_result("Live app not found", code="LIVE_APP_NOT_FOUND")
    except ValidationError as e:
        code = e.details.get("code", "LIVE_APP_DIFF_ENV_VALIDATION_ERROR")
        return ToolResult.error_result(e.message, code=code)
    except Exception as e:
        logger.exception("Failed to diff app environments")
        return ToolResult.error_result(
            f"Failed to diff app environments: {e}",
            code="LIVE_APP_DIFF_ENV_FAILED",
        )
