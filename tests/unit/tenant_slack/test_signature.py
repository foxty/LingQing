"""Unit tests for Slack signature verification (pure, no DB, no HTTP)."""

import hashlib
import hmac

from apps.tenant_app_service.slack.domain import (
    describe_ignored_event,
    slack_signature_failure_reason,
    verify_slack_signature,
)

SECRET = "test-signing-secret"
TIMESTAMP = "1700000000"
BODY = '{"type":"event_callback","event":{"type":"message","user":"U123"}}'


def _make_signature(secret: str, timestamp: str, body: str) -> str:
    base = f"v0:{timestamp}:{body}"
    return "v0=" + hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()


def test_valid_signature_passes():
    sig = _make_signature(SECRET, TIMESTAMP, BODY)
    assert verify_slack_signature(
        signing_secret=SECRET,
        timestamp=TIMESTAMP,
        body=BODY,
        signature=sig,
        now=float(TIMESTAMP),
    ) is True


def test_tampered_body_fails():
    sig = _make_signature(SECRET, TIMESTAMP, BODY)
    assert verify_slack_signature(
        signing_secret=SECRET,
        timestamp=TIMESTAMP,
        body=BODY + "tampered",
        signature=sig,
        now=float(TIMESTAMP),
    ) is False


def test_expired_timestamp_fails():
    sig = _make_signature(SECRET, TIMESTAMP, BODY)
    # now is 6 minutes later (>5 min max age)
    later = float(TIMESTAMP) + 360
    assert verify_slack_signature(
        signing_secret=SECRET,
        timestamp=TIMESTAMP,
        body=BODY,
        signature=sig,
        now=later,
    ) is False


def test_missing_headers_fail():
    sig = _make_signature(SECRET, TIMESTAMP, BODY)
    assert verify_slack_signature(signing_secret="", timestamp=TIMESTAMP, body=BODY, signature=sig) is False
    assert verify_slack_signature(signing_secret=SECRET, timestamp="", body=BODY, signature=sig) is False
    assert verify_slack_signature(signing_secret=SECRET, timestamp=TIMESTAMP, body="", signature=sig) is False
    assert verify_slack_signature(signing_secret=SECRET, timestamp=TIMESTAMP, body=BODY, signature="") is False


def test_wrong_signing_secret_fails():
    sig = _make_signature("wrong-secret", TIMESTAMP, BODY)
    assert verify_slack_signature(
        signing_secret=SECRET,
        timestamp=TIMESTAMP,
        body=BODY,
        signature=sig,
        now=float(TIMESTAMP),
    ) is False


def test_invalid_timestamp_fails():
    sig = _make_signature(SECRET, TIMESTAMP, BODY)
    assert verify_slack_signature(
        signing_secret=SECRET,
        timestamp="not-a-number",
        body=BODY,
        signature=sig,
    ) is False


def test_slack_signature_failure_reason_reports_mismatch():
    sig = _make_signature("wrong-secret", TIMESTAMP, BODY)
    reason = slack_signature_failure_reason(
        signing_secret=SECRET,
        timestamp=TIMESTAMP,
        body=BODY,
        signature=sig,
        now=float(TIMESTAMP),
    )
    assert reason == "signature_mismatch"


def test_slack_signature_failure_reason_reports_missing_secret():
    sig = _make_signature(SECRET, TIMESTAMP, BODY)
    reason = slack_signature_failure_reason(
        signing_secret="",
        timestamp=TIMESTAMP,
        body=BODY,
        signature=sig,
        now=float(TIMESTAMP),
    )
    assert reason == "missing_signing_secret"


def test_slack_signature_failure_reason_none_when_valid():
    sig = _make_signature(SECRET, TIMESTAMP, BODY)
    reason = slack_signature_failure_reason(
        signing_secret=SECRET,
        timestamp=TIMESTAMP,
        body=BODY,
        signature=sig,
        now=float(TIMESTAMP),
    )
    assert reason is None


def test_describe_ignored_event_for_non_dm():
    reason = describe_ignored_event(
        {
            "type": "message",
            "user": "U1",
            "channel": "C1",
            "text": "hi",
            "ts": "1.0",
            "channel_type": "channel",
        }
    )
    assert reason == "non_dm_channel_type=channel"
