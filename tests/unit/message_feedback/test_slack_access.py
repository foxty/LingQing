"""Tests for shared Slack access helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.db.models import AgentIngressEndpoint
from apps.shared.external_identity import BindAction, IdentityBindingResult
from apps.tenant_app_service.agent_ingress.slack.access import (
    is_eligible_slack_identity,
    resolve_eligible_slack_user_id,
    user_has_chat_access,
)


def test_is_eligible_slack_identity_rejects_pending_and_deny():
    assert is_eligible_slack_identity(None) is False
    assert (
        is_eligible_slack_identity(
            IdentityBindingResult(action=BindAction.PENDING, user_id=1, reason="pending")
        )
        is False
    )
    assert (
        is_eligible_slack_identity(
            IdentityBindingResult(action=BindAction.DENY, user_id=1, reason="deny")
        )
        is False
    )


def test_is_eligible_slack_identity_accepts_bound_user():
    assert (
        is_eligible_slack_identity(
            IdentityBindingResult(action=BindAction.LOGIN, user_id=7, reason="ok")
        )
        is True
    )


@pytest.mark.asyncio
async def test_user_has_chat_access_requires_active_membership(monkeypatch):
    db = AsyncMock()
    user_repo = MagicMock()
    user_repo.get_user_membership = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.access.UserRepository",
        lambda _db: user_repo,
    )

    assert await user_has_chat_access(db, tenant_id=1, user_id=9) is False


@pytest.mark.asyncio
async def test_resolve_eligible_slack_user_id_returns_none_for_ineligible_identity():
    db = AsyncMock()
    identity_service = MagicMock()
    identity_service.resolve_slack_user = AsyncMock(
        return_value=IdentityBindingResult(action=BindAction.PENDING, user_id=1, reason="pending")
    )
    endpoint = AgentIngressEndpoint(
        id=1,
        tenant_id=1,
        agent_id=2,
        endpoint_key="ep_test",
        credentials_encrypted={},
        enabled=True,
    )

    user_id = await resolve_eligible_slack_user_id(
        db,
        tenant_id=1,
        slack_user_id="U1",
        endpoint=endpoint,
        identity_service=identity_service,
    )

    assert user_id is None
