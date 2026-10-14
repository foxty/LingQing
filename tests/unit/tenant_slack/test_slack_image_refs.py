"""Tests for Slack document image path parsing."""

from apps.tenant_app_service.agent_ingress.slack.slack_image_refs import (
    SlackImageUploadSource,
    iter_markdown_image_refs,
    parse_document_image_location,
    upload_block_cache_key,
)

HASH = "d" * 64


def test_parse_document_image_location():
    ref = parse_document_image_location(f"/documents/9/images/{HASH}.png")
    assert ref is not None
    assert ref.document_id == 9
    assert ref.filename == f"{HASH}.png"


def test_upload_block_cache_key_chart():
    name = "chart_1_daily_ab12cd34.png"
    assert upload_block_cache_key({"source": SlackImageUploadSource.CHART, "filename": name}) == f"chart:{name}"


def test_iter_markdown_image_refs_includes_html_img():
    markdown = f'<p>See <img src="/documents/3/images/{HASH}.png" alt="Deck"></p>'
    refs = iter_markdown_image_refs(markdown)
    assert refs == [("", f"/documents/3/images/{HASH}.png")]
