"""Unit tests for Slack adapters and conversation key (pure, no DB)."""

from apps.tenant_app_service.agent_ingress.slack.domain import (
    conversation_key,
    split_long_text,
)


def test_conversation_key_composite_is_stable():
    key = conversation_key(tenant_id=42, slack_channel_id="D456", slack_thread_ts="")
    assert key.composite() == (42, "D456", "")
    assert key.tenant_id == 42
    assert key.slack_channel_id == "D456"
    assert key.slack_thread_ts == ""


def test_conversation_key_supports_channel_thread():
    key = conversation_key(tenant_id=1, slack_channel_id="C123", slack_thread_ts="100.001")
    assert key.composite() == (1, "C123", "100.001")


def test_conversation_key_is_frozen():
    key = conversation_key(1, "D1")
    import dataclasses

    assert dataclasses.is_dataclass(key)
    # frozen dataclass raises on setattr
    try:
        key.tenant_id = 2  # type: ignore
        raised = False
    except Exception:
        raised = True
    assert raised is True


def test_split_long_text_short_text_returns_single_chunk():
    assert split_long_text("hello", max_length=4000) == ["hello"]


def test_split_long_text_splits_on_newlines():
    text = "line1\nline2\nline3"
    chunks = split_long_text(text, max_length=10)
    assert all(len(c) <= 10 for c in chunks)
    # re-glued chunks should reconstruct the original content
    assert "\n".join(chunks) == text or "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_split_long_text_hard_splits_long_line():
    long_line = "x" * 5000
    chunks = split_long_text(long_line, max_length=4000)
    assert all(len(c) <= 4000 for c in chunks)
    assert "".join(chunks) == long_line


def test_split_long_text_preserves_content():
    text = "a" * 3000 + "\n" + "b" * 3000
    chunks = split_long_text(text, max_length=4000)
    assert all(len(c) <= 4000 for c in chunks)
    # content preserved
    assert "".join(c for c in chunks).replace("\n", "") == "a" * 3000 + "b" * 3000
