"""Tests for Slack image reference helpers."""

from apps.tenant_app_service.agent_ingress.slack.slack_image_refs import (
    SlackImageUploadSource,
    parse_document_image_location,
    upload_block_cache_key,
)

HASH = "a" * 64


def test_parse_document_image_location():
    ref = parse_document_image_location(f"/documents/9/images/{HASH}.png")
    assert ref is not None
    assert ref.document_id == 9
    assert ref.filename == f"{HASH}.png"


def test_upload_block_cache_key():
    assert (
        upload_block_cache_key(
            {
                "source": SlackImageUploadSource.CHART_RESOURCE,
                "chart_id": 7,
            }
        )
        == "chart_resource:7"
    )
    name = f"{HASH}.png"
    assert (
        upload_block_cache_key(
            {
                "source": SlackImageUploadSource.DOCUMENT,
                "document_id": 2,
                "filename": name,
            }
        )
        == f"document:2:{name}"
    )
