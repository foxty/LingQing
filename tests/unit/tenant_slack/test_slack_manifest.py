"""Unit tests for Slack app manifest generation."""

from apps.tenant_app_service.agent_ingress.slack.domain import (
    SLACK_BOT_EVENTS,
    SLACK_BOT_SCOPES,
    build_slack_app_manifest,
)


def test_build_slack_app_manifest_includes_tenant_events_url():
    url = "https://api.example.com/ingress/abc123/events"
    manifest = build_slack_app_manifest(events_url=url)

    assert manifest["settings"]["event_subscriptions"]["request_url"] == url
    assert manifest["settings"]["event_subscriptions"]["bot_events"] == list(SLACK_BOT_EVENTS)
    assert manifest["oauth_config"]["scopes"]["bot"] == list(SLACK_BOT_SCOPES)
    assert manifest["features"]["app_home"]["messages_tab_enabled"] is True
    assert manifest["settings"]["socket_mode_enabled"] is False


def test_build_slack_app_manifest_includes_channel_events_and_scopes():
    url = "https://api.example.com/ingress/abc123/events"
    manifest = build_slack_app_manifest(events_url=url)

    bot_events = manifest["settings"]["event_subscriptions"]["bot_events"]
    bot_scopes = manifest["oauth_config"]["scopes"]["bot"]
    assert "app_mention" in bot_events
    assert "message.channels" in bot_events
    assert "app_mentions:read" in bot_scopes
    assert "channels:history" in bot_scopes


def test_build_slack_app_manifest_uses_custom_display_names():
    manifest = build_slack_app_manifest(
        events_url="https://api.example.com/ingress/abc123/events",
        app_name="Acme Agent",
        bot_display_name="Acme Bot",
    )

    assert manifest["display_information"]["name"] == "Acme Agent"
    assert manifest["features"]["bot_user"]["display_name"] == "Acme Bot"
