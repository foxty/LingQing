from datetime import UTC, datetime

from apps.tenant_app_service.agents.domain import AgentRuntimeContext, AgentTenantContext, AgentUserContext
from apps.tenant_app_service.agents.runtime_environment import (
    build_runtime_environment_message,
    resolve_effective_timezone,
)


def test_resolve_effective_timezone_defaults_and_validates():
    assert resolve_effective_timezone(None) == "UTC"
    assert resolve_effective_timezone("Asia/Shanghai") == "Asia/Shanghai"
    assert resolve_effective_timezone("Not/AZone") == "UTC"


def test_build_runtime_environment_message_uses_user_timezone_for_local_date():
    runtime = AgentRuntimeContext(
        tenant=AgentTenantContext(tenant_id=100, tenant_name="tenant-a", config={}),
        user=AgentUserContext(
            user_id=1,
            username="alice",
            role="admin",
            tenant_id=100,
            tenant_name="tenant-a",
            timezone_iana="Asia/Shanghai",
        ),
        agent_id=-1,
        agent_name="Agent One",
        thread_id="100_1_-1",
        session_id="session-1",
    )
    # 2026-11-27 13:59:00 UTC == 2026-11-27 21:59:00+08:00
    fixed = datetime(2026, 11, 27, 13, 59, 0, tzinfo=UTC)
    message = build_runtime_environment_message(runtime, now=fixed)

    assert "timezone_iana: Asia/Shanghai" in message
    assert "local_calendar_date: 2026-11-27" in message
    assert "user: alice (id=1, role=admin)" in message
    assert "tenant: tenant-a (id=100)" in message


def test_build_runtime_environment_message_falls_back_to_utc_when_timezone_missing():
    runtime = AgentRuntimeContext(
        tenant=AgentTenantContext(tenant_id=1, tenant_name="t", config={}),
        user=AgentUserContext(
            user_id=2,
            username="bob",
            role="member",
            tenant_id=1,
            tenant_name="t",
        ),
        agent_id=-1,
        agent_name="Agent One",
        thread_id="1_2_-1",
        session_id="s",
    )
    fixed = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    message = build_runtime_environment_message(runtime, now=fixed)

    assert "timezone_iana: UTC" in message
    assert "local_calendar_date: 2026-01-01" in message