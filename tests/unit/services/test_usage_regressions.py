"""Regression tests for tenant usage/statistics services."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.observability.domain import CallStatus, EventType, MetricsContext, MetricsEvent, TokenUsage
from apps.shared.observability.service import ObservabilityService
from apps.tenant_app_service.tenant.service import SingleTenantService


def _make_event(
    *,
    event_type: str,
    status: str,
    session_id: str,
    user_id: int | None,
    thread_id: str | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> MetricsEvent:
    now = datetime.now(timezone.utc)
    return MetricsEvent(
        event_type=event_type,
        status=status,
        context=MetricsContext(
            session_id=session_id,
            thread_id=thread_id,
            user_id=user_id,
        ),
        start_time=now - timedelta(milliseconds=20),
        end_time=now,
        token_usage=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )
        if event_type == EventType.LLM_CALL
        else None,
    )


@pytest.mark.asyncio
async def test_get_tenant_usage_stats_counts_errors_by_status_and_user_id():
    events = [
        _make_event(
            event_type=EventType.LLM_CALL,
            status=CallStatus.SUCCESS,
            session_id="s-1",
            user_id=101,
            thread_id="t-1",
            input_tokens=10,
            output_tokens=20,
        ),
        _make_event(
            event_type=EventType.LLM_CALL,
            status=CallStatus.ERROR,
            session_id="s-2",
            user_id=102,
            thread_id="t-2",
            input_tokens=5,
            output_tokens=15,
        ),
        _make_event(
            event_type=EventType.TOOL_CALL,
            status=CallStatus.ERROR,
            session_id="s-2",
            user_id=102,
            thread_id="t-2",
        ),
        _make_event(
            event_type=EventType.TOOL_CALL,
            status=CallStatus.SUCCESS,
            session_id="s-1",
            user_id=101,
            thread_id="t-1",
        ),
    ]

    repo = SimpleNamespace(get_events_by_filters=AsyncMock(return_value=events))
    service = ObservabilityService(repo)

    start_time = datetime.now(timezone.utc) - timedelta(days=7)
    end_time = datetime.now(timezone.utc)

    stats = await service.get_tenant_usage_stats(tenant_id=1, start_time=start_time, end_time=end_time)

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
