"""Unit tests for Slack forwarded message ingress assembly."""

from apps.tenant_app_service.agent_ingress.slack.domain import (
    is_processable_message_event,
    parse_message_event,
)
from apps.tenant_app_service.agent_ingress.slack.inbound_message_context import (
    assemble_slack_inbound_message,
)


def _forward_attachment(**overrides) -> dict:
    base = {
        "is_share": True,
        "is_msg_unfurl": True,
        "author_id": "U_ORIG",
        "author_name": "Pat Example",
        "channel_id": "C_SRC",
        "channel_team": "T_WORK",
        "ts": "1733497200.423469",
        "from_url": "https://example.slack.com/archives/C_SRC/p1733497200423469",
        "text": "original body",
        "footer": "Slack Conversation",
    }
    base.update(overrides)
    return base


def test_accepts_dm_with_forwarded_attachment_and_empty_text():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [_forward_attachment()],
    }
    assert is_processable_message_event(event) is True
    parsed = parse_message_event(event, event_id="EvF1")
    assert parsed is not None
    assert "original body" in parsed.text
    assert "Pat Example" in parsed.text
    assert "C_SRC" in parsed.text
    assert parsed.incomplete_forward_context is False


def test_forward_plus_user_comment():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "what does this mean?",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [_forward_attachment(text="see this URL https://example.com/docs")],
    }
    assembly = assemble_slack_inbound_message(event)
    assert assembly.is_processable is True
    assert assembly.content.startswith("what does this mean?")
    assert "https://example.com/docs" in assembly.content


def test_multiple_forwards_preserve_order():
    first = _forward_attachment(text="first", ts="1.0", author_name="A One")
    second = _forward_attachment(text="second", ts="2.0", author_name="B Two")
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [first, second],
    }
    assembly = assemble_slack_inbound_message(event)
    first_idx = assembly.content.index("first")
    second_idx = assembly.content.index("second")
    assert first_idx < second_idx
    assert "A One" in assembly.content
    assert "B Two" in assembly.content


def test_rich_text_from_message_blocks():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [
            _forward_attachment(
                text="",
                message_blocks=[
                    {
                        "channel": "C_SRC",
                        "ts": "1733497200.423469",
                        "message": {
                            "blocks": [
                                {
                                    "type": "rich_text",
                                    "elements": [
                                        {
                                            "type": "rich_text_section",
                                            "elements": [{"type": "text", "text": "from blocks"}],
                                        }
                                    ],
                                }
                            ]
                        },
                    }
                ],
            )
        ],
    }
    assembly = assemble_slack_inbound_message(event)
    assert "from blocks" in assembly.content


def test_file_only_forward_marks_incomplete():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [_forward_attachment(text="", files=[{"id": "F1", "name": "diagram.png"}])],
    }
    parsed = parse_message_event(event, event_id="EvFile")
    assert parsed is not None
    assert parsed.incomplete_forward_context is True
    assert "file/image content is not included" in parsed.text


def test_plain_file_upload_dm_is_not_treated_as_forward():
    """Direct file upload to DM (top-level files) must stay pre-PR behavior: ignored."""
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "files": [{"id": "F9", "name": "report.pdf"}],
    }
    assert is_processable_message_event(event) is False
    assert assemble_slack_inbound_message(event).is_processable is False
    assert parse_message_event(event, event_id="EvUpload") is None


def test_fallback_marks_incomplete_but_still_processable():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [
            _forward_attachment(
                text="",
                author_name=None,
                author_id=None,
                channel_id=None,
                ts=None,
                fallback="[missing] partial transcript",
            )
        ],
    }
    assembly = assemble_slack_inbound_message(event)
    assert assembly.is_processable is True
    assert assembly.incomplete_context is True
    assert "partial transcript" in assembly.content


def test_plain_link_preview_is_not_treated_as_forward():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "check https://news.example.com",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [
            {
                "original_url": "https://news.example.com",
                "title": "News",
                "text": "Homepage",
            }
        ],
    }
    assembly = assemble_slack_inbound_message(event)
    assert assembly.content == "check https://news.example.com"
    assert "[Forwarded message]" not in assembly.content


def test_skips_bot_authored_forward_attachment():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "follow up",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [_forward_attachment(author_id="UBOT", text="my prior reply")],
    }
    assembly = assemble_slack_inbound_message(event, bot_user_id="UBOT")
    assert assembly.content == "follow up"
    assert "my prior reply" not in assembly.content


def test_parse_message_event_passes_bot_user_id_to_skip_self_unfurl():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "please summarize",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [_forward_attachment(author_id="UBOT", text="prior bot answer")],
    }
    parsed = parse_message_event(event, event_id="EvBot", bot_user_id="UBOT")
    assert parsed is not None
    assert parsed.text == "please summarize"
    assert "prior bot answer" not in parsed.text
    assert parsed.bot_user_id == "UBOT"


def test_forward_metadata_only_without_body_marks_incomplete_case_a():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "summarize",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [
            _forward_attachment(
                text="",
                author_name="Pat",
                author_id="U_A",
                channel_id="C_S",
                message_blocks=None,
            )
        ],
    }
    assembly = assemble_slack_inbound_message(event)
    assert assembly.incomplete_context is True
    assert "summarize" in assembly.content
    assert "Pat" in assembly.content
    assert "original body" not in assembly.content


def test_forward_image_url_without_body_marks_incomplete_case_b():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [
            _forward_attachment(
                text="",
                image_url="https://files.slack.com/foo.png",
                message_blocks=None,
            )
        ],
    }
    assembly = assemble_slack_inbound_message(event)
    assert assembly.incomplete_context is True
    assert "file/image content is not included" in assembly.content


def test_forward_message_text_fallback_when_blocks_missing_case_c():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [
            _forward_attachment(
                text="",
                message_blocks=[
                    {
                        "channel": "C_SRC",
                        "ts": "1.0",
                        "message": {"text": "body from message.text"},
                    }
                ],
            )
        ],
    }
    assembly = assemble_slack_inbound_message(event)
    assert assembly.incomplete_context is False
    assert "body from message.text" in assembly.content


def test_forward_with_body_text_stays_complete():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "what is this?",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "attachments": [_forward_attachment(text="clear forwarded body")],
    }
    assembly = assemble_slack_inbound_message(event)
    assert assembly.incomplete_context is False
    assert "clear forwarded body" in assembly.content


def test_plain_dm_unchanged():
    event = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "hello",
        "ts": "1700000000.000100",
        "channel_type": "im",
    }
    parsed = parse_message_event(event, event_id="EvPlain")
    assert parsed is not None
    assert parsed.text == "hello"
    assert parsed.incomplete_forward_context is False