"""Unit tests for markdown → Slack mrkdwn formatting."""

from apps.tenant_app_service.agent_ingress.slack.domain import format_reply_for_slack

PORTAL = "https://app.example.com"
API = "https://api.example.com"


def test_converts_bold_and_link():
    text = "See **[docs](https://example.com/docs)** for details."
    assert format_reply_for_slack(text) == "See *<https://example.com/docs|docs>* for details."


def test_converts_heading():
    text = "## Summary\n\nDone."
    assert format_reply_for_slack(text) == "*Summary*\n\nDone."


def test_preserves_code_block():
    text = "Run:\n```python\nprint('hi')\n```"
    assert format_reply_for_slack(text) == text


def test_preserves_inline_code():
    text = "Use `tenant_id` in the query."
    assert format_reply_for_slack(text) == text


def test_simplifies_markdown_table():
    text = "| Name | Role |\n| --- | --- |\n| Ada | Admin |"
    assert format_reply_for_slack(text) == "• Name · Role\n• Ada · Admin"


def test_plain_text_unchanged():
    text = "Hello from LingQing."
    assert format_reply_for_slack(text) == text


def test_empty_string():
    assert format_reply_for_slack("") == ""
    assert format_reply_for_slack("   ") == "   "


def test_converts_markdown_image_to_chart_link():
    text = "![Daily Sales](http://localhost:8000/static/charts/chart_1.svg)"
    result = format_reply_for_slack(text, api_origin=API)
    assert result == f"📊 <{API}/static/charts/chart_1.svg|Daily Sales>"


def test_fixes_broken_image_link_from_prior_conversion():
    text = "!</api/static/charts/chart_1.svg|Daily Sales Trend>"
    result = format_reply_for_slack(text, api_origin=API)
    assert result == f"📊 <{API}/static/charts/chart_1.svg|Daily Sales Trend>"

    text_with_angle = "!<http://localhost:8000/static/charts/chart_1.svg|Daily Sales Trend>"
    result = format_reply_for_slack(text_with_angle, api_origin=API)
    assert result == f"📊 <{API}/static/charts/chart_1.svg|Daily Sales Trend>"


def test_resolves_relative_report_link():
    text = "Report: </reports/2|Weekly Sales Report>"
    result = format_reply_for_slack(text, portal_origin=PORTAL)
    assert result == f"Report: <{PORTAL}/reports/2|Weekly Sales Report>"


def test_converts_markdown_report_link():
    text = "Full report: [Weekly Sales](/reports/2)"
    result = format_reply_for_slack(text, portal_origin=PORTAL)
    assert result == f"Full report: <{PORTAL}/reports/2|Weekly Sales>"


def test_replaces_common_emoji_shortcodes():
    text = "Done :white_check_mark: with :chart_with_downwards_trend:"
    assert format_reply_for_slack(text) == "Done ✅ with 📉"
