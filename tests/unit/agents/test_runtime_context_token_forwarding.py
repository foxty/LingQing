from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agents.context import create_agent_runtime_user_context


def test_create_agent_runtime_user_context_accepts_access_token():
    user = UserDTO(
        id=1,
        username="alice",
        role="admin",
        tenant_id=10,
        tenant_name="tenant-a",
        timezone_iana="Asia/Shanghai",
    )

    runtime_user = create_agent_runtime_user_context(user, access_token="jwt-token-123")

    assert runtime_user.user_id == 1
    assert runtime_user.tenant_id == 10
    assert runtime_user.timezone_iana == "Asia/Shanghai"
    assert runtime_user.access_token == "jwt-token-123"


def test_create_agent_runtime_user_context_without_token():
    user = UserDTO(
        id=2,
        username="bob",
        role="analyst",
        tenant_id=20,
        tenant_name="tenant-b",
    )

    runtime_user = create_agent_runtime_user_context(user)

    assert runtime_user.user_id == 2
    assert runtime_user.access_token is None
