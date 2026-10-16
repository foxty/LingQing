"""Thinking evidence extraction for LLM metrics."""

from langchain_core.messages import AIMessage

from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import _extract_thinking_evidence


def test_extract_thinking_evidence_from_content_blocks():
    response = AIMessage(
        content=[
            {"type": "thinking", "thinking": "internal"},
            {"type": "text", "text": "Hello"},
        ]
    )
    evidence = _extract_thinking_evidence(response)
    assert evidence["thinking_content_blocks"] == 1
    assert evidence["thinking_evidence"] == "content_blocks"


def test_extract_thinking_evidence_none_when_absent():
    response = AIMessage(content="plain")
    evidence = _extract_thinking_evidence(response)
    assert evidence["thinking_evidence"] == "none"
