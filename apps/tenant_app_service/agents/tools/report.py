"""Report generation and persistence tools."""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.domain.actor import ActorContext
from apps.shared.report.domain import ReportFormat
from apps.shared.report.service import ReportService
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_rbac import tool_rbac_denied
from apps.tenant_app_service.agents.tools.tool_result import ToolResult
from apps.tenant_app_service.agents.tools.tool_session import agent_tool_db_session

logger = get_logger(__name__)


def _actor_ctx(config: RunnableConfig) -> ActorContext:
    runtime = extract_runtime_context(config)
    return ActorContext(
        tenant_id=runtime.user.tenant_id,
        user_id=runtime.user.user_id,
        user_role=runtime.user.role,
    )


@tool
async def create_report(
    title: str,
    content: str,
    format: ReportFormat = ReportFormat.MARKDOWN,
    config: RunnableConfig = None,
) -> ToolResult:
    """Create and persist a durable report artifact.

    The report is stored independently from thread lifecycle. If thread context is available, the report is also linked into the thread for immediate UI rendering in the current conversation.

    Format Guidelines:
    - markdown (default): Use for structured documents with headings, lists, tables, and code blocks. Renders as formatted text with markdown syntax support.

    Examples:
    - Create a data analysis report: format="markdown" with tables and charts as markdown images

    Args:
        title: Report title
        content: Full report content in the specified format
        format: Content format (markdown). Defaults to markdown.
        config: Runtime config

    Returns:
        ToolResult with persisted report metadata and optional artifact payload
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id
    user_id = runtime.user.user_id
    thread_id = runtime.thread_id

    logger.info(
        "Creating report",
        extra={"tenant_id": tenant_id, "user_id": user_id, "thread_id": thread_id, "title": title},
    )

    async with agent_tool_db_session(config) as session:
        denied = await tool_rbac_denied(
            session,
            tenant_id,
            runtime.user.role,
            TenantAppPermissions.REPORTS_WRITE,
            denied_message="You do not have permission to create reports",
        )
        if denied:
            return denied

        service = ReportService.create(tenant_id=tenant_id, db_session=session)

        result = await service.create_report(
            title=title,
            content=content,
            format=format if isinstance(format, str) else format.value,
            thread_id=thread_id,
            owner_id=user_id,
            report_metadata={"length": len(content)},
        )

        artifact_payload = None
        if result.artifact:
            artifact_payload = result.artifact.model_dump()

        return ToolResult.success(
            {
                "report_id": result.report.id,
                "title": result.report.title,
                "format": result.report.format,
                "report_url": f"/reports/{result.report.id}",
                "message": f"Report '{result.report.title}' created successfully",
                "artifact": artifact_payload,
            }
        )


@tool
async def get_report(
    report_id: int,
    config: RunnableConfig = None,
) -> ToolResult:
    """Get report details for read-before-update workflows.

    Args:
        report_id: Report ID
        config: Runtime config

    Returns:
        ToolResult with report content and metadata
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id

    async with agent_tool_db_session(config) as session:
        service = ReportService.create(tenant_id=tenant_id, db_session=session)
        report = await service.get_report_for_actor(report_id, actor=_actor_ctx(config))

        return ToolResult.success(
            {
                "report_id": report.id,
                "title": report.title,
                "content": report.content,
                "format": report.format,
                "source_thread_id": report.source_thread_id,
                "report_url": f"/reports/{report.id}",
                "updated_at": report.updated_at.isoformat() if report.updated_at else None,
            }
        )


@tool
async def update_report(
    report_id: int,
    content: str,
    title: str | None = None,
    format: ReportFormat | None = None,
    config: RunnableConfig = None,
) -> ToolResult:
    """Update an existing report (owner only).

    This performs a full content update and optional metadata updates.

    Format Guidelines:
    - markdown: Use for structured documents with headings, lists, tables, and code blocks

    Args:
        report_id: Report ID to update
        content: Full updated report content
        title: Optional updated title
        format: Optional content format (markdown)
        config: Runtime config

    Returns:
        ToolResult with updated report metadata
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id

    logger.info(
        "Updating report",
        extra={"tenant_id": tenant_id, "user_id": runtime.user.user_id, "report_id": report_id},
    )

    async with agent_tool_db_session(config) as session:
        service = ReportService.create(tenant_id=tenant_id, db_session=session)

        updated = await service.update_report_for_actor(
            report_id=report_id,
            actor=_actor_ctx(config),
            title=title,
            content=content,
            format=format.value if isinstance(format, ReportFormat) else format,
            report_metadata={"length": len(content)},
        )

        return ToolResult.success(
            {
                "report_id": updated.id,
                "title": updated.title,
                "format": updated.format,
                "report_url": f"/reports/{updated.id}",
                "updated_at": updated.updated_at.isoformat() if updated.updated_at else None,
                "message": f"Report '{updated.title}' updated successfully",
            }
        )
