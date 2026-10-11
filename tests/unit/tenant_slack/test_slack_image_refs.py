"""Tests for Slack document image path parsing."""

from apps.tenant_app_service.agent_ingress.slack.slack_image_refs import (
    iter_markdown_image_refs,
    parse_document_image_location,
)

HASH = "d" * 64


def test_parse_document_image_location():
    ref = parse_document_image_location(f"/documents/9/images/{HASH}.png")
    assert ref is not None
    assert ref.document_id == 9
    assert ref.filename == f"{HASH}.png"


def test_iter_markdown_image_refs_includes_html_img():
    markdown = f'<p>See <img src="/documents/3/images/{HASH}.png" alt="Deck"></p>'
    refs = iter_markdown_image_refs(markdown)
    assert refs == [("", f"/documents/3/images/{HASH}.png")]
