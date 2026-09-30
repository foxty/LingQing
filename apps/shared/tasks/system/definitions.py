"""System task definition registry.

Declares all platform-level scheduled tasks as immutable dataclasses.
Each definition maps to one ScheduledTask row per tenant (materialized by
SystemTaskReconciler at startup and on new-tenant creation).

To add a new system task:
1. Write a handler function somewhere in apps/shared/tasks/system/jobs/
2. Return SystemTaskHandlerResult from the handler
3. Map it in apps/shared/tasks/execution_service.py allowlist
4. Add a SystemTaskDefinition entry to SYSTEM_TASK_DEFINITIONS below

The scheduler will automatically create/update the per-tenant rows.
"""

from dataclasses import dataclass, field

from apps.shared.tasks.domain import (
    EXECUTION_MODE_INTERNAL,
    TASK_TYPE_SYSTEM,
)


@dataclass(frozen=True)
class SystemTaskDefinition:
    """Immutable definition of a platform system task.

    Attributes:
        stable_key:     Globally unique key; used as idempotent upsert key
                        combined with tenant_id in the scheduled_tasks table.
        name:           Human-readable task name shown in the UI.
        task_type:      Maps to ScheduledTask.task_type (usually 'system').
        handler_ref:    Fully-qualified 'module:function' dispatched by system task executor.
                        Stored in task_config for consistency with other task types.
        schedule_spec:  Cron spec dict, e.g. {'cron': '0 2 * * *', 'timezone': 'UTC'}.
        execution_mode: 'internal' for in-process; 'sandbox' for Docker.
        default_input_params: Static args passed as TaskRun.input_params each run.
        enabled:        False disables reconciliation for this template.
    """

    stable_key: str
    name: str
    handler_ref: str  # Will be stored in task_config, not DB column
    schedule_spec: dict
    task_type: str = TASK_TYPE_SYSTEM
    execution_mode: str = EXECUTION_MODE_INTERNAL
    default_input_params: dict = field(default_factory=dict)
    enabled: bool = True


# ---------------------------------------------------------------------------
# Platform system task declarations
# All existing hardcoded APScheduler jobs should be declared here.
# ---------------------------------------------------------------------------

SYSTEM_TASK_DEFINITIONS: list[SystemTaskDefinition] = [
    SystemTaskDefinition(
        stable_key="system.vector_sync.incremental",
        name="Vector DB Incremental Sync",
        handler_ref="apps.shared.tasks.system.jobs.vector_sync:sync_to_vector_db",
        schedule_spec={"cron": "*/5 * * * *", "timezone": "UTC"},
        default_input_params={"source": "all", "mode": "incremental", "batch_size": 100},
    ),
    SystemTaskDefinition(
        stable_key="system.vector_sync.orphan_cleanup",
        name="Vector DB Orphan Cleanup",
        handler_ref="apps.shared.tasks.system.jobs.vector_sync:cleanup_orphaned_vectors",
        schedule_spec={"cron": "0 2 * * *", "timezone": "UTC"},
        default_input_params={"dry_run": False},
    ),
    SystemTaskDefinition(
        stable_key="system.asset_metadata_sync",
        name="Asset Metadata Sync",
        handler_ref="apps.shared.tasks.system.jobs.asset_sync:sync_asset_metadata_for_all",
        schedule_spec={"cron": "0 */6 * * *", "timezone": "UTC"},
        default_input_params={},
    ),
    SystemTaskDefinition(
        stable_key="system.document_parse.poll",
        name="Document Parse Worker",
        handler_ref="apps.shared.tasks.system.jobs.document_parse:run_document_parse_jobs",
        schedule_spec={"cron": "*/2 * * * *", "timezone": "UTC"},
        default_input_params={"batch_size": 10},
    ),
    SystemTaskDefinition(
        stable_key="system.cleanup.charts",
        name="Chart Files Cleanup",
        handler_ref="apps.shared.tasks.system.jobs.cleanup:cleanup_old_charts",
        schedule_spec={"cron": "0 * * * *", "timezone": "UTC"},
        default_input_params={"max_age_hours": 24},
    ),
    SystemTaskDefinition(
        stable_key="system.cleanup.temp_tables",
        name="Temp Tables Cleanup",
        handler_ref="apps.shared.tasks.system.jobs.cleanup:cleanup_expired_temp_tables",
        schedule_spec={"cron": "0 * * * *", "timezone": "UTC"},
        default_input_params={},
    ),
    SystemTaskDefinition(
        stable_key="system.document_sync",
        name="Document Drive Sync",
        handler_ref="apps.shared.tasks.system.jobs.document_sync:run_document_sync_jobs",
        schedule_spec={"cron": "*/15 * * * *", "timezone": "UTC"},
        default_input_params={},
    ),
]
