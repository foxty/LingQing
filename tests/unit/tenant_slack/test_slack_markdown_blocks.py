"""Unit tests for GFM Markdown → Slack Block Kit planning."""

from apps.tenant_app_service.agent_ingress.slack.markdown_blocks import (
    MarkdownRenderError,
    RenderRoute,
    SlackMarkdownPolicy,
    _MarkdownWalker,
    plan_slack_markdown,
)


def _table(rows: int) -> str:
    lines = ["| Name | Role |", "| --- | --- |"]
    lines.extend(f"| user{index} | member |" for index in range(rows))
    return "\n".join(lines)


def test_heading_list_code_and_divider_become_sections():
    text = "# Title\n\n- one\n- two\n\nUse `tenant_id`.\n\n---\n\n```python\nprint('hi')\n```"
    plan = plan_slack_markdown(text)

    assert plan.route == RenderRoute.INLINE
    assert plan.blocks[0]["type"] == "section"
    section = plan.blocks[0]["text"]["text"]
    assert section.startswith("*Title*")
    assert "• one" in section
    assert "• two" in section
    assert "`tenant_id`" in section
    assert plan.blocks[1] == {"type": "divider"}
    assert "```python" in plan.blocks[2]["text"]["text"]
    assert "print('hi')" in plan.blocks[2]["text"]["text"]
    assert all(block["type"] != "actions" for block in plan.blocks)


def test_bold_link_emoji_and_quote():
    text = "See **[docs](https://example.com/docs)** :white_check_mark:\n\n> noted"
    plan = plan_slack_markdown(text)
    section = plan.blocks[0]["text"]["text"]
    assert section == "See *<https://example.com/docs|docs>* ✅\n\n> noted"


def test_small_table_and_public_image_keep_source_order():
    text = "Hello\n\n| Name | Role |\n| --- | --- |\n| Ada | Admin |\n\n![Plot](https://cdn.example.com/plot.png)"
    plan = plan_slack_markdown(text)

    assert plan.route == RenderRoute.INLINE
    assert [block["type"] for block in plan.blocks] == ["section", "table", "image"]
    assert plan.blocks[1]["rows"][0][0]["text"] == "Name"
    assert plan.blocks[1]["rows"][1][1]["text"] == "Admin"
    assert plan.blocks[1]["column_settings"][0]["is_wrapped"] is True
    assert plan.blocks[2]["image_url"] == "https://cdn.example.com/plot.png"
    assert plan.blocks[2]["alt_text"] == "Plot"


def test_table_over_row_threshold_uses_canvas_route():
    plan = plan_slack_markdown(_table(11))
    assert plan.route == RenderRoute.CANVAS
    assert plan.table_data_rows == 11


def test_ten_row_table_stays_inline():
    plan = plan_slack_markdown(_table(10))
    assert plan.route == RenderRoute.INLINE
    assert any(block["type"] == "table" for block in plan.blocks)


def test_three_images_use_canvas_route():
    text = "\n\n".join(f"![chart](https://cdn.example.com/{index}.png)" for index in range(3))
    plan = plan_slack_markdown(text)
    assert plan.route == RenderRoute.CANVAS
    assert plan.image_count == 3


def test_two_images_stay_inline():
    text = "\n\n".join(f"![chart](https://cdn.example.com/{index}.png)" for index in range(2))
    plan = plan_slack_markdown(text)
    assert plan.route == RenderRoute.INLINE
    assert [block["type"] for block in plan.blocks] == ["image", "image"]


def test_svg_image_becomes_chart_link_and_still_counts():
    text = "![Daily](http://127.0.0.1:8000/static/chart.svg)"
    plan = plan_slack_markdown(text, api_origin="http://127.0.0.1:8000")
    assert plan.image_count == 1
    assert plan.blocks[0]["type"] == "section"
    assert "chart.svg" in plan.blocks[0]["text"]["text"]
    assert plan.blocks[0]["type"] != "image"


def test_private_owned_image_is_marked_for_upload():
    text = "![Plot](http://127.0.0.1:8000/static/plot.png)"
    plan = plan_slack_markdown(text, api_origin="http://127.0.0.1:8000")
    block = plan.blocks[0]
    assert block["type"] == "_image_upload"
    assert block["source"] == "url"
    assert block["url"] == "http://127.0.0.1:8000/static/plot.png"


def test_document_image_is_marked_for_upload():
    image_name = "a" * 64
    text = f"![Deck page 4](/documents/1/images/{image_name}.png)"
    plan = plan_slack_markdown(text, api_origin="https://api.example.com")
    block = plan.blocks[0]
    assert block["type"] == "_image_upload"
    assert block["source"] == "document"
    assert block["document_id"] == 1
    assert block["filename"] == f"{image_name}.png"
    assert block["url"] == f"https://api.example.com/documents/1/images/{image_name}.png"


def test_untrusted_private_image_is_not_uploaded():
    text = "![Plot](http://10.1.2.3/secret.png)"
    plan = plan_slack_markdown(text, api_origin="https://api.example.com")
    assert plan.blocks[0]["type"] == "section"
    assert "10.1.2.3" in plan.blocks[0]["text"]["text"]


def test_long_cell_is_truncated_and_stays_inline():
    policy = SlackMarkdownPolicy(cell_max_chars=5)
    plan = plan_slack_markdown("| A |\n| --- |\n| hello world |", policy=policy)
    assert plan.route == RenderRoute.INLINE
    assert plan.truncated_cells is True
    assert plan.blocks[0]["rows"][1][0]["text"] == "hell…"


def test_structural_overflow_uses_canvas_route():
    policy = SlackMarkdownPolicy(max_blocks=2)
    text = "hello\n\n---\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"
    plan = plan_slack_markdown(text, policy=policy)
    assert plan.route == RenderRoute.CANVAS


def test_prose_overflow_stays_inline_for_splitting():
    policy = SlackMarkdownPolicy(max_blocks=2)
    text = "one\n\n---\n\ntwo\n\n---\n\nthree"
    plan = plan_slack_markdown(text, policy=policy)
    assert plan.route == RenderRoute.INLINE
    assert len(plan.blocks) == 5


def test_unrecognized_node_degrades(monkeypatch):
    def _boom(self):
        raise MarkdownRenderError("mystery")

    monkeypatch.setattr(_MarkdownWalker, "walk", _boom)
    plan = plan_slack_markdown("Hello")
    assert plan.route == RenderRoute.DEGRADED
    assert plan.degrade_reason == "unrecognized:mystery"
    assert plan.blocks == []
