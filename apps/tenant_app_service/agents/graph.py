"""Create agent graph for langgraph studio debugging."""

from apps.tenant_app_service.agents.agent_base import AgentBase

# LangGraph Studio requires a synchronous 'agent' export
agent = AgentBase(
    {
        "agent_id": 0,
        "name": "DebugAgent",
        "system_prompt": "You are a helpful assistant.",
    }
).compile()
