from apps.tenant_app_service.agents.message_metadata import (
    THINKING_MESSAGE_METADATA_KEYS,
    pop_message_metadata_from_kwargs,
)


def test_pop_message_metadata_moves_thinking_and_general_keys():
    kwargs = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "thinking_content": "chain",
        "reasoning_tokens": 26,
        "thinking_evidence": "usage",
        "provider_only": "stay",
    }
    meta = pop_message_metadata_from_kwargs(kwargs)
    assert meta["thinking_content"] == "chain"
    assert meta["reasoning_tokens"] == 26
    assert kwargs == {"provider_only": "stay"}
    assert set(THINKING_MESSAGE_METADATA_KEYS) >= {
        "thinking_content",
        "reasoning_tokens",
        "thinking_evidence",
    }


def test_pop_message_metadata_maps_legacy_context_resources():
    kwargs = {"context_resources": [{"id": "a"}]}
    meta = pop_message_metadata_from_kwargs(kwargs)
    assert meta["attached_artifacts"] == [{"id": "a"}]
    assert kwargs == {}
