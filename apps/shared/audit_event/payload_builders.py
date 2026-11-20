"""Per-event audit payload shapes (call sites use these instead of ad-hoc dicts)."""

from __future__ import annotations

from typing import Any

from apps.shared.audit_event.payload import mask_email


def build_auth_login_success_payload(*, auth_method: str = "password") -> dict[str, Any]:
    return {"auth_method": auth_method}


def build_auth_login_failure_payload(
    *,
    failure_reason: str,
    attempted_identifier_hash: str,
) -> dict[str, Any]:
    return {
        "failure_reason": failure_reason,
        "attempted_identifier_hash": attempted_identifier_hash,
    }


def build_conflict_rejection_payload(*, failure_reason: str, **metadata: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"failure_reason": failure_reason}
    payload.update(metadata)
    return payload


def build_user_create_payload(*, email: str | None, role: str) -> dict[str, Any]:
    return {"email_masked": mask_email(email), "role": role}


def build_user_membership_payload(*, change_summary: str) -> dict[str, Any]:
    return {"change_summary": change_summary}


def build_user_role_update_payload(*, role_before: str, role_after: str) -> dict[str, Any]:
    return {
        "change_summary": "role_updated",
        "role_before": role_before,
        "role_after": role_after,
    }


def build_acl_share_create_payload(*, shared_with_user_id: int, permission: str) -> dict[str, Any]:
    return {"shared_with_user_id": shared_with_user_id, "permission": permission}


def build_acl_share_revoke_payload(*, shared_with_user_id: int) -> dict[str, Any]:
    return {"shared_with_user_id": shared_with_user_id}


def build_datasource_create_payload(
    *,
    name: str,
    connector_type: str,
    credentials_present: bool,
) -> dict[str, Any]:
    return {
        "name": name,
        "connector_type": connector_type,
        "credentials_present": credentials_present,
    }


def build_datasource_update_payload(
    *,
    change_summary: list[str],
    credentials_changed: bool,
    credential_field_names: list[str],
) -> dict[str, Any]:
    return {
        "change_summary": change_summary,
        "credentials_changed": credentials_changed,
        "credential_field_names": credential_field_names,
    }


def build_datasource_delete_payload(*, name_snapshot: str) -> dict[str, Any]:
    return {"name_snapshot": name_snapshot}


def build_agent_create_payload(*, name: str) -> dict[str, Any]:
    return {"name": name}


def build_agent_update_payload(*, change_summary: list[str]) -> dict[str, Any]:
    return {"change_summary": change_summary}


def build_agent_status_update_payload(*, status_before: str, status_after: str) -> dict[str, Any]:
    return {"status_before": status_before, "status_after": status_after}


def build_agent_delete_payload(*, name_snapshot: str | None) -> dict[str, Any]:
    return {"name_snapshot": name_snapshot}


def build_kb_document_create_payload(*, title: str, collection_id: int) -> dict[str, Any]:
    return {"title": title, "collection_id": collection_id}


def build_kb_document_delete_payload(*, title_snapshot: str) -> dict[str, Any]:
    return {"title_snapshot": title_snapshot}


def build_skill_create_payload(*, name: str, scope: str) -> dict[str, Any]:
    return {"name": name, "scope": scope}


def build_skill_delete_payload(*, name_snapshot: str, scope: str) -> dict[str, Any]:
    return {"name_snapshot": name_snapshot, "scope": scope}


def build_skill_status_update_payload(
    *,
    name: str,
    scope: str,
    enabled_before: bool | None,
    enabled_after: bool,
) -> dict[str, Any]:
    return {
        "name": name,
        "scope": scope,
        "enabled_before": enabled_before,
        "enabled_after": enabled_after,
    }


def build_skill_env_vars_payload(*, env_var_keys_changed: list[str]) -> dict[str, Any]:
    return {"env_var_keys_changed": env_var_keys_changed}


def build_slack_agent_ingress_payload(*, agent_id: int) -> dict[str, Any]:
    return {"agent_id": agent_id}


def build_slack_integration_update_payload(*, fields_changed: list[str], agent_id: int) -> dict[str, Any]:
    return {"fields_changed": fields_changed, "agent_id": agent_id}