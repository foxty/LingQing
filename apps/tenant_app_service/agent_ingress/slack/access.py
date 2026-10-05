"""Shared Slack ingress access checks."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.db.models import AgentIngressEndpoint
from apps.shared.external_identity import BindAction, IdentityBindingResult
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.identity_service import SlackIdentityService
from apps.tenant_app_service.auth.repository import UserRepository

logger = get_logger(__name__)


async def user_has_chat_access(db: AsyncSession, tenant_id: int, user_id: int) -> bool:
    """Return True when the user has active membership and chat.access."""
    user_repo = UserRepository(db)
    membership = await user_repo.get_user_membership(tenant_id, user_id)
    if not membership:
        return False
    user, membership_row = membership
    if membership_row.status != "active":
        return False
    try:
        return await role_has_permission(
            db=db,
            tenant_id=tenant_id,
            role_key=user.role,
            permission=Permissions.CHAT_ACCESS,
        )
    except Exception:
        logger.exception("Permission check failed for tenant %s user %s", tenant_id, user_id)
        return False


def is_eligible_slack_identity(result: IdentityBindingResult | None) -> bool:
    """Slack subjects must be bound to an active internal user, not pending/denied."""
    if result is None or result.user_id is None:
        return False
    return result.action not in {BindAction.DENY, BindAction.PENDING}


async def resolve_eligible_slack_user_id(
    db: AsyncSession,
    *,
    tenant_id: int,
    slack_user_id: str,
    endpoint: AgentIngressEndpoint,
    identity_service: SlackIdentityService,
) -> int | None:
    """Resolve Slack user to internal user_id when bound and chat.access is granted."""
    result = await identity_service.resolve_slack_user(
        tenant_id=tenant_id,
        slack_user_id=slack_user_id,
        endpoint=endpoint,
    )
    if not is_eligible_slack_identity(result):
        return None
    assert result is not None and result.user_id is not None
    if not await user_has_chat_access(db, tenant_id, result.user_id):
        return None
    return result.user_id
