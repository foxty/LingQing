"""Unit tests for AbacPolicyService."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.schemas import (
    AbacPolicySimulateRequest,
    AbacPolicyValidateRequest,
    AbacPolicyValidateResponse,
)
from apps.shared.authz.service import AbacPolicyService
from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.db.models import AbacPolicy


def _make_db_policy(**kwargs) -> AbacPolicy:
    defaults = {
        "id": 1,
        "tenant_id": 1,
        "name": "Test Policy",
        "description": None,
        "resource_type": "document",
        "expression": ':user.role equals "admin"',
        "status": "disabled",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "created_by": None,
        "updated_by": None,
    }
    defaults.update(kwargs)
    policy = MagicMock(spec=AbacPolicy)
    for k, v in defaults.items():
        setattr(policy, k, v)
    return policy


def _make_service(policy: AbacPolicy | None = None) -> AbacPolicyService:
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.info = {}
    repo = AsyncMock()
    repo.db = mock_session
    repo.get_by_id_and_tenant.return_value = policy
    repo.update.side_effect = lambda p: p  # return same object
    service = AbacPolicyService(tenant_id=1, policy_repo=repo)
    return service


@pytest.mark.asyncio
async def test_enable_policy_sets_status_active():
    policy = _make_db_policy(status="disabled")
    service = _make_service(policy)
    result = await service.enable_policy(policy_id=1, updated_by=42)
    assert policy.status == "active"
    assert policy.updated_by == 42


@pytest.mark.asyncio
async def test_disable_then_enable_roundtrip():
    policy = _make_db_policy(status="active")
    service = _make_service(policy)

    await service.disable_policy(policy_id=1, updated_by=1)
    assert policy.status == "disabled"

    await service.enable_policy(policy_id=1, updated_by=1)
    assert policy.status == "active"


@pytest.mark.asyncio
async def test_enable_policy_raises_when_not_found():
    service = _make_service(policy=None)
    with pytest.raises(ResourceNotFoundError):
        await service.enable_policy(policy_id=999, updated_by=1)


def test_validate_request_schema_accepts_valid_expression():
    req = AbacPolicyValidateRequest(expression=':user.role equals "admin"')
    assert req.expression == ':user.role equals "admin"'


def test_simulate_request_schema_validates_resource_type():
    req = AbacPolicySimulateRequest(
        expression=':user.role equals "admin"',
        resource_type="document",
        user_id=1,
        resource_id=2,
        user_role="admin",
    )
    assert req.resource_type == "document"
    assert req.user_role == "admin"


def test_validate_response_schema():
    resp = AbacPolicyValidateResponse(
        valid=True,
        errors=[],
        human_readable="user.role equals 'admin'",
    )
    assert resp.valid is True
    assert resp.human_readable == "user.role equals 'admin'"
