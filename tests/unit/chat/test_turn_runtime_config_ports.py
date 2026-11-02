"""ChatTurnService wires agent harness ports when a run_id is present."""

from unittest.mock import MagicMock
from uuid import uuid4

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.agent_run_port_adapter import ChatAgentRunPort
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from apps.tenant_app_service.chat.turn_service import ChatTurnService
from apps.tenant_app_service.tenant.domain import TenantConfig, TenantDomain


def _minimal_turn_inputs(*, run_id: str | None = None):
    db = MagicMock()
    service = ChatTurnService(tenant_id=42, db=db)
    tenant = TenantDomain(
        id=42,
        name="T",
        slug="t",
        description=None,
        config=TenantConfig(),
        status="active",
    )
    user = UserDTO(id=7, username="u", role="admin", tenant_id=42, tenant_name="T")
    request = ChatRequest(
        tenant_id=42,
        agent_id=3,
        message=SimpleMessage(role="human", content="hi"),
        thread_id="42_7_3_abc",
    )
    return service, tenant, user, request, db, run_id


def test_build_runtime_config_without_run_id_omits_harness_ports():
    service, tenant, user, request, db, _ = _minimal_turn_inputs(run_id=None)
    config = service._build_runtime_config(
        tenant,
        user,
        request,
        agent_id=3,
        agent_name="agent",
        session_id=str(uuid4()),
        db_session=db,
        run_id=None,
    )
    configurable = config["configurable"]
    assert "run_id" not in configurable
    assert "agent_run_port" not in configurable


def test_build_runtime_config_with_run_id_injects_chat_adapters():
    run_id = str(uuid4())
    service, tenant, user, request, db, _ = _minimal_turn_inputs(run_id=run_id)
    config = service._build_runtime_config(
        tenant,
        user,
        request,
        agent_id=3,
        agent_name="agent",
        session_id=str(uuid4()),
        db_session=db,
        run_id=run_id,
        trigger_message_id="human-1",
    )
    configurable = config["configurable"]
    assert configurable["run_id"] == run_id
    assert configurable["trigger_message_id"] == "human-1"
    assert isinstance(configurable["agent_run_port"], ChatAgentRunPort)
    assert configurable["thread_id"] == run_id


def test_build_runtime_config_skip_load_history_flag():
    service, tenant, user, request, db, _ = _minimal_turn_inputs()
    run_id = str(uuid4())
    config = service._build_runtime_config(
        tenant,
        user,
        request,
        agent_id=3,
        agent_name="agent",
        session_id=str(uuid4()),
        db_session=db,
        run_id=run_id,
        skip_load_history=True,
    )
    assert config["configurable"]["skip_load_history"] is True
    assert "agent_run_port" in config["configurable"]
