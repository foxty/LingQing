from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agents.agent_base import AgentBase
from apps.tenant_app_service.agents.context import create_agent_runtime_user_context
from apps.tenant_app_service.agents.domain import AgentRuntimeContext, AgentTenantContext
from apps.tenant_app_service.agents.system_agent_config import load_yaml_agent_config


def _build_runtime(timezone_iana: str | None) -> AgentRuntimeContext:
    user = UserDTO(
        id=1,
        username="alice",
        role="admin",
        tenant_id=100,
        tenant_name="tenant-a",
        timezone_iana=timezone_iana,
    )
    user_ctx = create_agent_runtime_user_context(user)
    return AgentRuntimeContext(
        tenant=AgentTenantContext(tenant_id=100, tenant_name="tenant-a", config={}),
        user=user_ctx,
        agent_id=-1,
        agent_name="Agent One",
        thread_id="100_1_-1",
        session_id="session-1",
    )


def test_prepare_system_messages_includes_runtime_timezone_preference():
    agent = AgentBase(load_yaml_agent_config(-1))
    runtime = _build_runtime("Asia/Shanghai")

    messages = agent._prepare_system_messages(runtime=runtime, loop_count=0, loaded_skills=[])
    contents = [msg.content for msg in messages]

    assert any("Runtime User Preferences" in content for content in contents)
    assert any("timezone_iana: Asia/Shanghai" in content for content in contents)


def test_prepare_system_messages_skips_preference_block_when_timezone_missing():
    agent = AgentBase(load_yaml_agent_config(-1))
    runtime = _build_runtime(None)

    messages = agent._prepare_system_messages(runtime=runtime, loop_count=0, loaded_skills=[])
    contents = [msg.content for msg in messages]

    assert not any("Runtime User Preferences" in content for content in contents)
