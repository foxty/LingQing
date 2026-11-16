"""Tenant audit event type constants (PRD §6 sign-off)."""

from __future__ import annotations

from enum import StrEnum


class TenantAuditEventType(StrEnum):
    """Mandatory and reserved audit event names for tenant ``audit_events``."""

    # auth.*
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"  # reserved — no write in v1

    # user.*
    USER_CREATE = "user.create"
    USER_MEMBERSHIP_DEACTIVATE = "user.membership.deactivate"
    USER_MEMBERSHIP_REACTIVATE = "user.membership.reactivate"
    USER_ROLE_UPDATE = "user.role.update"
    USER_PERMISSION_UPDATE = "user.permission.update"  # reserved

    # kb.*
    KB_DOCUMENT_CREATE = "kb.document.create"
    KB_DOCUMENT_UPDATE = "kb.document.update"  # reserved
    KB_DOCUMENT_DELETE = "kb.document.delete"
    KB_DOCUMENT_ACCESS_POLICY_UPDATE = "kb.document.access_policy.update"
    KB_DOCUMENT_PUBLISH = "kb.document.publish"  # reserved
    KB_DOCUMENT_READ = "kb.document.read"  # reserved

    # agent.*
    AGENT_CREATE = "agent.create"
    AGENT_UPDATE = "agent.update"
    AGENT_DELETE = "agent.delete"
    AGENT_STATUS_UPDATE = "agent.status.update"
    SKILL_CREATE = "skill.create"
    SKILL_STATUS_UPDATE = "skill.status.update"
    SKILL_ENV_VARS_UPDATE = "skill.env_vars.update"
    SKILL_DELETE = "skill.delete"

    # slack.*
    SLACK_AGENT_INGRESS_ENDPOINT_CREATE = "slack.agent_ingress_endpoint.create"
    SLACK_AGENT_INGRESS_ENDPOINT_DELETE = "slack.agent_ingress_endpoint.delete"
    SLACK_INTEGRATION_UPDATE = "slack.integration.update"

    # datasource.*
    DATASOURCE_CREATE = "datasource.create"
    DATASOURCE_UPDATE = "datasource.update"
    DATASOURCE_DELETE = "datasource.delete"

    # export.*
    EXPORT_DATA = "export.data"

    # audit.*
    AUDIT_LOG_EXPORT = "audit.log.export"
    AUDIT_LOG_VIEW = "audit.log.view"  # reserved


MANDATORY_EVENT_TYPES: frozenset[str] = frozenset(
    t.value
    for t in TenantAuditEventType
    if t
    not in {
        TenantAuditEventType.AUTH_LOGOUT,
        TenantAuditEventType.USER_PERMISSION_UPDATE,
        TenantAuditEventType.KB_DOCUMENT_UPDATE,
        TenantAuditEventType.KB_DOCUMENT_PUBLISH,
        TenantAuditEventType.KB_DOCUMENT_READ,
        TenantAuditEventType.AUDIT_LOG_VIEW,
    }
)

RESERVED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        TenantAuditEventType.AUTH_LOGOUT.value,
        TenantAuditEventType.USER_PERMISSION_UPDATE.value,
        TenantAuditEventType.KB_DOCUMENT_UPDATE.value,
        TenantAuditEventType.KB_DOCUMENT_PUBLISH.value,
        TenantAuditEventType.KB_DOCUMENT_READ.value,
        TenantAuditEventType.AUDIT_LOG_VIEW.value,
    }
)