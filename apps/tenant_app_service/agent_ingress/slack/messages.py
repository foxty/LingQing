"""User-facing Slack message catalog.

All copy shown to Slack users lives here so locales can be added later
without touching ingress orchestration code.
"""

from __future__ import annotations

import enum

DEFAULT_LOCALE = "en"


class SlackMessageKey(enum.StrEnum):
    """Stable keys for Slack user-visible strings."""

    INTEGRATION_DISABLED = "integration_disabled"
    SLACK_VERIFY_FAILED = "slack_verify_failed"
    CHAT_PERMISSION_DENIED = "chat_permission_denied"
    EMPTY_MENTION_MESSAGE = "empty_mention_message"
    LINKED_ACCOUNT_NOT_FOUND = "linked_account_not_found"
    IDENTITY_PENDING = "identity_pending"
    IDENTITY_DENIAL_GENERIC = "identity_denial_generic"
    IDENTITY_MISSING_EMAIL = "identity_missing_email"
    IDENTITY_DOMAIN_NOT_ALLOWED = "identity_domain_not_allowed"
    IDENTITY_REJECT_UNKNOWN = "identity_reject_unknown"
    IDENTITY_EMAIL_COLLISION = "identity_email_collision"
    IDENTITY_SUBJECT_REJECTED = "identity_subject_rejected"
    CHAT_AGENT_ACCESS_DENIED = "chat_agent_access_denied"
    CHAT_AUTHORIZATION_DENIED = "chat_authorization_denied"
    CHAT_AGENT_NOT_FOUND = "chat_agent_not_found"
    CHAT_RESOURCE_NOT_FOUND = "chat_resource_not_found"
    CHAT_VALIDATION_FAILED = "chat_validation_failed"
    CHAT_GENERIC_FAILURE = "chat_generic_failure"
    THINKING_PLACEHOLDER = "thinking_placeholder"
    EMPTY_REPLY_FALLBACK = "empty_reply_fallback"


_CATALOG: dict[str, dict[SlackMessageKey, str]] = {
    "en": {
        SlackMessageKey.INTEGRATION_DISABLED: (
            "This agent's Slack integration is currently disabled. "
            "Contact your admin to re-enable it in LingQing."
        ),
        SlackMessageKey.SLACK_VERIFY_FAILED: (
            "Could not reach Slack to verify your account. Please try again."
        ),
        SlackMessageKey.CHAT_PERMISSION_DENIED: (
            "You don't have permission to chat with the agent."
        ),
        SlackMessageKey.EMPTY_MENTION_MESSAGE: (
            "Please include a message after mentioning the bot."
        ),
        SlackMessageKey.LINKED_ACCOUNT_NOT_FOUND: (
            "Your linked account could not be found."
        ),
        SlackMessageKey.IDENTITY_PENDING: (
            "Your Slack account is pending admin approval. "
            "You'll be able to chat once an admin links it."
        ),
        SlackMessageKey.IDENTITY_DENIAL_GENERIC: (
            "Your Slack account cannot be linked. Contact your admin."
        ),
        SlackMessageKey.IDENTITY_MISSING_EMAIL: (
            "We could not read an email address from your Slack profile. "
            "Contact your admin."
        ),
        SlackMessageKey.IDENTITY_DOMAIN_NOT_ALLOWED: (
            "Your Slack email domain is not allowed for this workspace. "
            "Contact your admin."
        ),
        SlackMessageKey.IDENTITY_REJECT_UNKNOWN: (
            "No LingQing account matches your Slack email. "
            "Ask your admin to invite you with the same email address."
        ),
        SlackMessageKey.IDENTITY_EMAIL_COLLISION: (
            "Your Slack email matches multiple LingQing accounts. "
            "Contact your admin."
        ),
        SlackMessageKey.IDENTITY_SUBJECT_REJECTED: (
            "Your Slack account was previously rejected. Contact your admin."
        ),
        SlackMessageKey.CHAT_AGENT_ACCESS_DENIED: (
            "You don't have permission to use this agent in LingQing. "
            "Ask your admin to grant you access to this agent."
        ),
        SlackMessageKey.CHAT_AUTHORIZATION_DENIED: (
            "You don't have permission to complete this request. "
            "Contact your admin if you believe this is a mistake."
        ),
        SlackMessageKey.CHAT_AGENT_NOT_FOUND: (
            "This agent is no longer available. "
            "Ask your admin to check the Slack integration configuration."
        ),
        SlackMessageKey.CHAT_RESOURCE_NOT_FOUND: (
            "The requested resource could not be found. Contact your admin."
        ),
        SlackMessageKey.CHAT_VALIDATION_FAILED: (
            "Your request could not be processed. "
            "Please check your message and try again, or contact your admin."
        ),
        SlackMessageKey.CHAT_GENERIC_FAILURE: (
            "Sorry, I couldn't process that request. Please try again."
        ),
        SlackMessageKey.THINKING_PLACEHOLDER: "🤔 …",
        SlackMessageKey.EMPTY_REPLY_FALLBACK: (
            "The model returned no visible text. Please try again."
        ),
    },
}

_AGENT_ACCESS_DENIED_MESSAGES = frozenset({"无权访问该智能体"})


def slack_user_message(key: SlackMessageKey, *, locale: str = DEFAULT_LOCALE) -> str:
    """Resolve a catalog message for the given locale, falling back to English."""
    table = _CATALOG.get(locale) or _CATALOG[DEFAULT_LOCALE]
    return table[key]


def slack_identity_user_message(*, action: str, reason: str | None = None, locale: str = DEFAULT_LOCALE) -> str:
    """User-facing copy for identity bind outcomes."""
    from apps.shared.external_identity import BindAction

    if action == BindAction.PENDING:
        return slack_user_message(SlackMessageKey.IDENTITY_PENDING, locale=locale)
    if action != BindAction.DENY:
        return slack_user_message(SlackMessageKey.IDENTITY_DENIAL_GENERIC, locale=locale)

    reason_to_key = {
        "missing_email": SlackMessageKey.IDENTITY_MISSING_EMAIL,
        "domain_not_allowed": SlackMessageKey.IDENTITY_DOMAIN_NOT_ALLOWED,
        "policy_reject_unknown": SlackMessageKey.IDENTITY_REJECT_UNKNOWN,
        "email_collision": SlackMessageKey.IDENTITY_EMAIL_COLLISION,
        "subject_rejected": SlackMessageKey.IDENTITY_SUBJECT_REJECTED,
    }
    key = reason_to_key.get(reason or "", SlackMessageKey.IDENTITY_DENIAL_GENERIC)
    return slack_user_message(key, locale=locale)


def slack_chat_error_message(exc: Exception, *, locale: str = DEFAULT_LOCALE) -> str:
    """User-facing copy when chat invocation fails."""
    from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError, ValidationError

    if isinstance(exc, AuthorizationError):
        if exc.message in _AGENT_ACCESS_DENIED_MESSAGES:
            return slack_user_message(SlackMessageKey.CHAT_AGENT_ACCESS_DENIED, locale=locale)
        return slack_user_message(SlackMessageKey.CHAT_AUTHORIZATION_DENIED, locale=locale)

    if isinstance(exc, ResourceNotFoundError):
        if exc.message.startswith("Agent ") and "not found" in exc.message:
            return slack_user_message(SlackMessageKey.CHAT_AGENT_NOT_FOUND, locale=locale)
        return slack_user_message(SlackMessageKey.CHAT_RESOURCE_NOT_FOUND, locale=locale)

    if isinstance(exc, ValidationError):
        return slack_user_message(SlackMessageKey.CHAT_VALIDATION_FAILED, locale=locale)

    return slack_user_message(SlackMessageKey.CHAT_GENERIC_FAILURE, locale=locale)


SLACK_INTEGRATION_DISABLED_MESSAGE = slack_user_message(SlackMessageKey.INTEGRATION_DISABLED)
SLACK_SCHEDULED_FAILURE_MESSAGE = slack_user_message(SlackMessageKey.CHAT_GENERIC_FAILURE)
SLACK_THINKING_PLACEHOLDER = slack_user_message(SlackMessageKey.THINKING_PLACEHOLDER)
SLACK_EMPTY_REPLY_FALLBACK = slack_user_message(SlackMessageKey.EMPTY_REPLY_FALLBACK)
