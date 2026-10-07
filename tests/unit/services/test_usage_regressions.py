"""Regression tests for tenant usage/statistics services."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.observability.service import ObservabilityService
from apps.tenant_app_service.tenant.service import SingleTenantService


@pytest.mark.asyncio
async def test_get_tenant_usage_stats_counts_errors_by_status_and_user_id():
    aggregate = (2, 1, 2, 1, 15, 35, 2, 2, 2, 120.5, 80.0)
    repo = SimpleNamespace(aggregate_usage_stats=AsyncMock(return_value=aggregate))
    service = ObservabilityService(repo)

    start_time = datetime.now(timezone.utc) - timedelta(days=7)
    end_time = datetime.now(timezone.utc)

    stats = await service.get_tenant_usage_stats(tenant_id=1, start_time=start_time, end_time=end_time)

    repo.aggregate_usage_stats.assert_awaited_once_with(
        tenant_id=1,
        start_time=start_time,
        end_time=end_time,
        user_id=None,
        agent_id=None,
    )
    assert stats.total_llm_calls == 2
    assert stats.total_llm_errors == 1
    assert stats.total_tool_calls == 2
    assert stats.total_tool_errors == 1
    assert stats.total_input_tokens == 15
    assert stats.total_output_tokens == 35
    assert stats.total_tokens == 50
    assert stats.unique_sessions == 2
    assert stats.unique_threads == 2
    assert stats.unique_users == 2
    assert stats.avg_llm_duration_ms == 120.5
    assert stats.avg_tool_duration_ms == 80.0


@pytest.mark.asyncio
async def test_get_tenant_token_daily_usage_uses_sql_aggregate():
    day = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [(day, 100, 200, 5, 1)]
    repo = SimpleNamespace(aggregate_daily_token_usage=AsyncMock(return_value=rows))
    service = ObservabilityService(repo)

    start_time = datetime.now(timezone.utc) - timedelta(days=7)
    end_time = datetime.now(timezone.utc)

    daily = await service.get_tenant_token_daily_usage(
        tenant_id=1,
        start_time=start_time,
        end_time=end_time,
        user_id=9,
        agent_id=42,
    )

    repo.aggregate_daily_token_usage.assert_awaited_once_with(
        tenant_id=1,
        start_time=start_time,
        end_time=end_time,
        user_id=9,
        agent_id=42,
    )
    assert daily == [
        {
            "date": "2026-01-01",
            "total_input_tokens": 100,
            "total_output_tokens": 200,
            "total_tokens": 300,
            "llm_calls": 5,
            "llm_errors": 1,
        }
    ]


@pytest.mark.asyncio
async def test_get_agent_usage_stats_returns_tenant_usage_dto():
    aggregate = (12, 1, 34, 2, 1000, 2500, 5, 4, 3, 250.0, 90.0)
    repo = SimpleNamespace(aggregate_usage_stats=AsyncMock(return_value=aggregate))
    service = ObservabilityService(repo)

    start_time = datetime.now(timezone.utc) - timedelta(days=30)
    end_time = datetime.now(timezone.utc)

    stats = await service.get_agent_usage_stats(
        tenant_id=1,
        agent_id=42,
        start_time=start_time,
        end_time=end_time,
        user_id=7,
    )

    repo.aggregate_usage_stats.assert_awaited_once_with(
        tenant_id=1,
        start_time=start_time,
        end_time=end_time,
        user_id=7,
        agent_id=42,
    )
    assert stats.tenant_id == 1
    assert stats.total_llm_calls == 12
    assert stats.total_llm_errors == 1
    assert stats.total_tool_calls == 34
    assert stats.total_tool_errors == 2
    assert stats.total_tokens == 3500
    assert stats.unique_threads == 4
    assert stats.unique_users == 3


@pytest.mark.asyncio
async def test_single_tenant_get_stats_returns_document_count_and_storage_bytes():
    tenant_repo = SimpleNamespace()
    agent_repo = SimpleNamespace(count_active=AsyncMock(return_value=3))
    document_repo = SimpleNamespace(get_document_stats=AsyncMock(return_value=(12, 3456)))
    asset_repo = SimpleNamespace(count_by_tenant=AsyncMock(return_value=7))
    service = SingleTenantService(
        tenant_id=1,
        tenant_repo=tenant_repo,
        agent_repo=agent_repo,
        document_repo=document_repo,
        asset_repo=asset_repo,
    )

    stats = await service.get_stats()

    assert stats.total_documents == 12
    assert stats.total_storage_bytes == 3456
    assert stats.total_assets == 7
    assert stats.total_agents == 3
