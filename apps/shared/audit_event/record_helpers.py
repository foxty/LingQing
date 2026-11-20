"""Audit record helpers: typed payloads + recorder wiring."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.audit_event.context import AuditRequestContext
from apps.shared.audit_event.event_types import TenantAuditEventType
from apps.shared.audit_event.payload_builders import (
    build_acl_share_create_payload,
    build_acl_share_revoke_payload,
    build_agent_create_payload,
    build_agent_delete_payload,
    build_agent_status_update_payload,
    build_agent_update_payload,
    build_auth_login_failure_payload,
    build_auth_login_success_payload,
    build_conflict_rejection_payload,
    build_datasource_create_payload,
    build_datasource_delete_payload,
    build_datasource_update_payload,
    build_kb_document_create_payload,
    build_kb_document_delete_payload,
    build_skill_create_payload,
    build_skill_delete_payload,
    build_skill_env_vars_payload,
    build_skill_status_update_payload,
    build_slack_agent_ingress_payload,
    build_slack_integration_update_payload,
    build_user_create_payload,
    build_user_membership_payload,
    build_user_role_update_payload,
)
from apps.shared.audit_event.recorder import (
    ACTOR_TYPE_ANONYMOUS,
    ACTOR_TYPE_USER,
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    TenantAuditRecorder,
)
from apps.shared.db.session import app_db_session


def identifier_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def record_conflict_rejection_audit(
    *,
    tenant_id: int,
    event_type: str,
    actor_user_id: int,
    resource_type: str,
    resource_id: str | None,
    failure_reason: str,
    request_context: AuditRequestContext | None = None,
    **metadata: Any,
) -> None:
    """Failure audit in a committed side transaction (survives request rollback)."""
    async with app_db_session() as db:
        recorder = TenantAuditRecorder(db, tenant_id=tenant_id, request_context=request_context)
        await recorder.record(
            event_type=event_type,
            outcome=OUTCOME_FAILURE,
            actor_user_id=actor_user_id,
            actor_type=ACTOR_TYPE_USER,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=build_conflict_rejection_payload(failure_reason=failure_reason, **metadata),
        )


async def record_auth_login_success(
    recorder: TenantAuditRecorder,
    *,
    user_id: int,
    auth_method: str = "password",
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.AUTH_LOGIN_SUCCESS.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="user",
        resource_id=str(user_id),
        payload=build_auth_login_success_payload(auth_method=auth_method),
    )


async def record_auth_login_failure(
    recorder: TenantAuditRecorder,
    *,
    attempted_identifier: str,
    failure_reason: str,
    tenant_id: int,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.AUTH_LOGIN_FAILURE.value,
        outcome=OUTCOME_FAILURE,
        actor_user_id=None,
        actor_type=ACTOR_TYPE_ANONYMOUS,
        payload=build_auth_login_failure_payload(
            failure_reason=failure_reason,
            attempted_identifier_hash=identifier_hash(f"{attempted_identifier}@{tenant_id}"),
        ),
    )


async def record_user_create(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    user_id: int,
    email: str | None,
    role: str,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.USER_CREATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="user",
        resource_id=str(user_id),
        payload=build_user_create_payload(email=email, role=role),
    )


async def record_user_membership_deactivate(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    user_id: int,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.USER_MEMBERSHIP_DEACTIVATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="user",
        resource_id=str(user_id),
        payload=build_user_membership_payload(change_summary="membership_deactivated"),
    )


async def record_user_membership_reactivate(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    user_id: int,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.USER_MEMBERSHIP_REACTIVATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="user",
        resource_id=str(user_id),
        payload=build_user_membership_payload(change_summary="membership_reactivated"),
    )


async def record_user_role_update(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    user_id: int,
    role_before: str,
    role_after: str,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.USER_ROLE_UPDATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="user",
        resource_id=str(user_id),
        payload=build_user_role_update_payload(role_before=role_before, role_after=role_after),
    )


async def record_acl_share_create(
    db: AsyncSession,
    *,
    tenant_id: int,
    actor_user_id: int,
    resource_type: str,
    resource_id: int,
    shared_with_user_id: int,
    permission: str,
    request_context: AuditRequestContext | None = None,
) -> None:
    recorder = TenantAuditRecorder(db, tenant_id=tenant_id, request_context=request_context)
    await recorder.record(
        event_type=TenantAuditEventType.ACL_SHARE_CREATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type=resource_type,
        resource_id=str(resource_id),
        payload=build_acl_share_create_payload(
            shared_with_user_id=shared_with_user_id,
            permission=permission,
        ),
    )


async def record_acl_share_revoke(
    db: AsyncSession,
    *,
    tenant_id: int,
    actor_user_id: int,
    resource_type: str,
    resource_id: int,
    shared_with_user_id: int,
    request_context: AuditRequestContext | None = None,
) -> None:
    recorder = TenantAuditRecorder(db, tenant_id=tenant_id, request_context=request_context)
    await recorder.record(
        event_type=TenantAuditEventType.ACL_SHARE_REVOKE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type=resource_type,
        resource_id=str(resource_id),
        payload=build_acl_share_revoke_payload(shared_with_user_id=shared_with_user_id),
    )


async def record_datasource_create(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    data_source_id: int,
    name: str,
    connector_type: str,
    config_has_secrets: bool,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.DATASOURCE_CREATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="datasource",
        resource_id=str(data_source_id),
        payload=build_datasource_create_payload(
            name=name,
            connector_type=connector_type,
            config_has_secrets=config_has_secrets,
        ),
    )


async def record_datasource_update(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    data_source_id: int,
    change_summary: list[str],
    secret_config_changed: bool,
    secret_config_keys: list[str],
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.DATASOURCE_UPDATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="datasource",
        resource_id=str(data_source_id),
        payload=build_datasource_update_payload(
            change_summary=change_summary,
            secret_config_changed=secret_config_changed,
            secret_config_keys=secret_config_keys,
        ),
    )


async def record_datasource_delete(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    data_source_id: int,
    name_snapshot: str,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.DATASOURCE_DELETE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="datasource",
        resource_id=str(data_source_id),
        payload=build_datasource_delete_payload(name_snapshot=name_snapshot),
    )


async def record_agent_create(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    agent_id: int,
    name: str,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.AGENT_CREATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="agent",
        resource_id=str(agent_id),
        payload=build_agent_create_payload(name=name),
    )


async def record_agent_update(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    agent_id: int,
    change_summary: list[str],
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.AGENT_UPDATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="agent",
        resource_id=str(agent_id),
        payload=build_agent_update_payload(change_summary=change_summary),
    )


async def record_agent_status_update(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    agent_id: int,
    status_before: str,
    status_after: str,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.AGENT_STATUS_UPDATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="agent",
        resource_id=str(agent_id),
        payload=build_agent_status_update_payload(status_before=status_before, status_after=status_after),
    )


async def record_agent_delete(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    agent_id: int,
    name_snapshot: str | None,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.AGENT_DELETE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="agent",
        resource_id=str(agent_id),
        payload=build_agent_delete_payload(name_snapshot=name_snapshot),
    )


async def record_kb_document_create(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    document_id: int,
    title: str,
    collection_id: int,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.KB_DOCUMENT_CREATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="document",
        resource_id=str(document_id),
        payload=build_kb_document_create_payload(title=title, collection_id=collection_id),
    )


async def record_kb_document_delete(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    document_id: int,
    title_snapshot: str,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.KB_DOCUMENT_DELETE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="document",
        resource_id=str(document_id),
        payload=build_kb_document_delete_payload(title_snapshot=title_snapshot),
    )


async def record_skill_create(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    name: str,
    scope: str,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.SKILL_CREATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="skill",
        resource_id=name,
        payload=build_skill_create_payload(name=name, scope=scope),
    )


async def record_skill_delete(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    name: str,
    scope: str,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.SKILL_DELETE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="skill",
        resource_id=name,
        payload=build_skill_delete_payload(name_snapshot=name, scope=scope),
    )


async def record_skill_status_update(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    name: str,
    scope: str,
    enabled_before: bool | None,
    enabled_after: bool,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.SKILL_STATUS_UPDATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="skill",
        resource_id=name,
        payload=build_skill_status_update_payload(
            name=name,
            scope=scope,
            enabled_before=enabled_before,
            enabled_after=enabled_after,
        ),
    )


async def record_skill_env_vars_update(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    name: str,
    env_var_keys_changed: list[str],
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.SKILL_ENV_VARS_UPDATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="skill",
        resource_id=name,
        payload=build_skill_env_vars_payload(env_var_keys_changed=env_var_keys_changed),
    )


async def record_slack_agent_ingress_create(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    endpoint_id: int,
    agent_id: int,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.SLACK_AGENT_INGRESS_ENDPOINT_CREATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="agent_ingress_endpoint",
        resource_id=str(endpoint_id),
        payload=build_slack_agent_ingress_payload(agent_id=agent_id),
    )


async def record_slack_agent_ingress_delete(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    endpoint_id: int,
    agent_id: int,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.SLACK_AGENT_INGRESS_ENDPOINT_DELETE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="agent_ingress_endpoint",
        resource_id=str(endpoint_id),
        payload=build_slack_agent_ingress_payload(agent_id=agent_id),
    )


async def record_slack_integration_update(
    recorder: TenantAuditRecorder,
    *,
    actor_user_id: int,
    endpoint_id: int,
    agent_id: int,
    fields_changed: list[str],
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.SLACK_INTEGRATION_UPDATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="agent_ingress_endpoint",
        resource_id=str(endpoint_id),
        payload=build_slack_integration_update_payload(fields_changed=fields_changed, agent_id=agent_id),
    )