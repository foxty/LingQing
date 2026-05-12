"""Unit tests for centralized Slack user message catalog."""

from apps.tenant_app_service.agent_ingress.slack.messages import (
    DEFAULT_LOCALE,
    SlackMessageKey,
    _CATALOG,
    slack_user_message,
)


def test_all_message_keys_have_default_locale_copy():
    en = _CATALOG[DEFAULT_LOCALE]
    for key in SlackMessageKey:
        assert key in en
        assert en[key].strip()


def test_unknown_locale_falls_back_to_english():
    msg = slack_user_message(SlackMessageKey.CHAT_GENERIC_FAILURE, locale="zh")
    assert msg == _CATALOG[DEFAULT_LOCALE][SlackMessageKey.CHAT_GENERIC_FAILURE]
