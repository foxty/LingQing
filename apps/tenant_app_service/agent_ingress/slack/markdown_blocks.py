"""Convert GFM Markdown into Slack Block Kit blocks.

The walker is pure: it does not call Slack. Image uploads and Canvas writes
happen in the delivery layer. Size limits live on ``SlackMarkdownPolicy``.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from markdown_it import MarkdownIt

from apps.tenant_app_service.agent_ingress.slack.domain import (
    _chart_slack_link,
    _replace_emoji_shortcodes,
    _resolve_url,
)
from apps.shared.chart.paths import chart_png_url_for_svg_url, chart_static_png_filename
from apps.tenant_app_service.agent_ingress.slack.slack_image_refs import (
    SlackImageUploadSource,
    parse_document_image_location,
)

SLACK_TABLE_MAX_COLUMNS = 20
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif")
_SVG_EXTENSION = ".svg"
_PARSER = MarkdownIt("commonmark").enable(["table", "strikethrough"])
_OPEN_MARKERS = {"strong_open": "*", "em_open": "_", "s_open": "~"}
_CLOSE_FOR_OPEN = {"strong_open": "strong_close", "em_open": "em_close", "s_open": "s_close"}
_FILENAME_CLEAN = re.compile(r"[^A-Za-z0-9._-]")


class MarkdownRenderError(Exception):
    """Raised when a Markdown token cannot be mapped to a Slack block."""


class RenderRoute(StrEnum):
    """How a rendered reply should be delivered."""

    INLINE = "inline"
    CANVAS = "canvas"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class SlackMarkdownPolicy:
    """Product thresholds and Slack API limits for one render.

    Production uses the defaults. Tests pass a smaller policy to force the
    Canvas route, a split, or cell truncation. These values are not environment
    variables.
    """

    table_row_threshold: int = 10
    image_threshold: int = 2
    max_blocks: int = 49
    section_max_chars: int = 3000
    cell_max_chars: int = 500
    table_max_chars: int = 10_000


@dataclass(frozen=True)
class SlackMarkdownPlan:
    """Render decision plus the blocks to post when the route is inline."""

    route: RenderRoute
    blocks: list[dict[str, Any]]
    summary_heading: str
    summary_body: str
    summary_title: str
    table_data_rows: int
    image_count: int
    truncated_cells: bool
    degrade_reason: str | None
    node_counts: dict[str, int]
    markdown: str


@dataclass(frozen=True)
class _TextPiece:
    text: str
    kind: str


@dataclass(frozen=True)
class _DividerPiece:
    pass


@dataclass(frozen=True)
class _TablePiece:
    block: dict[str, Any]


@dataclass(frozen=True)
class _ImagePiece:
    alt: str
    raw_url: str
    resolved_url: str


def plan_slack_markdown(
    markdown: str,
    *,
    policy: SlackMarkdownPolicy | None = None,
    portal_origin: str | None = None,
    api_origin: str | None = None,
) -> SlackMarkdownPlan:
    """Parse GFM and choose an inline, Canvas, or mrkdwn-fallback route."""
    active = policy or SlackMarkdownPolicy()
    try:
        tokens = _PARSER.parse(markdown or "")
        walker = _MarkdownWalker(
            tokens,
            policy=active,
            portal_origin=portal_origin,
            api_origin=api_origin,
        )
        pieces = walker.walk()
    except MarkdownRenderError as exc:
        return _degraded_plan(markdown, f"unrecognized:{exc}")
    except Exception as exc:
        return _degraded_plan(markdown, f"parse:{type(exc).__name__}")

    if not pieces:
        return _degraded_plan(markdown, "empty")

    summary_heading, summary_body = _summary_text(pieces)
    blocks = _pack_blocks(pieces, active, portal_origin, api_origin)
    if not blocks:
        return _degraded_plan(markdown, "empty", node_counts=dict(walker.counts))

    extra_blocks = 1 if walker.truncated_cells else 0
    content_len = len(blocks) + extra_blocks
    over_size = (
        walker.max_table_rows > active.table_row_threshold
        or walker.image_count > active.image_threshold
        or walker.table_chars > active.table_max_chars
    )
    structural = walker.has_table or walker.image_count > 0
    if over_size or (content_len > active.max_blocks and structural):
        route = RenderRoute.CANVAS
    else:
        route = RenderRoute.INLINE

    return SlackMarkdownPlan(
        route=route,
        blocks=blocks,
        summary_heading=summary_heading,
        summary_body=summary_body,
        summary_title=walker.summary_title,
        table_data_rows=walker.table_data_rows,
        image_count=walker.image_count,
        truncated_cells=walker.truncated_cells and route == RenderRoute.INLINE,
        degrade_reason=None,
        node_counts=dict(walker.counts),
        markdown=markdown,
    )


def canvas_summary_blocks(
    plan: SlackMarkdownPlan,
    canvas_url: str,
    policy: SlackMarkdownPolicy | None = None,
) -> list[dict[str, Any]]:
    """Build the short channel message that points at a Canvas."""
    active = policy or SlackMarkdownPolicy()
    parts = [part for part in (plan.summary_heading, plan.summary_body) if part]
    summary = _trim("\n\n".join(parts) or "Full answer", active.section_max_chars)
    note = f"Full answer ({plan.table_data_rows} table rows, {plan.image_count} images): <{canvas_url}|Open in Canvas>"
    return [_section(summary), _section(_trim(note, active.section_max_chars))]


def canvas_truncation_context(canvas_url: str) -> dict[str, Any]:
    """Context line used when an inline table cell was shortened."""
    return {
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"Some table cells were shortened. <{canvas_url}|See Canvas>",
            }
        ],
    }


def split_blocks(blocks: list[dict[str, Any]], max_blocks: int) -> list[list[dict[str, Any]]]:
    """Split content blocks into Slack-sized groups."""
    limit = max(1, max_blocks)
    if len(blocks) <= limit:
        return [blocks] if blocks else []
    return [blocks[index : index + limit] for index in range(0, len(blocks), limit)]


def message_text(blocks: list[dict[str, Any]], *, limit: int = 3000) -> str:
    """Plain notification fallback required alongside blocks."""
    parts: list[str] = []
    for block in blocks:
        if block.get("type") == "section":
            parts.append(str((block.get("text") or {}).get("text") or ""))
        elif block.get("type") == "context":
            for element in block.get("elements") or []:
                if element.get("text"):
                    parts.append(str(element["text"]))
        elif block.get("type") == "image":
            parts.append(str(block.get("alt_text") or ""))
    text = "\n".join(part for part in parts if part).strip()
    return _trim(text, limit) if text else ""


class _MarkdownWalker:
    def __init__(
        self,
        tokens: list[Any],
        *,
        policy: SlackMarkdownPolicy,
        portal_origin: str | None,
        api_origin: str | None,
    ):
        self.tokens = tokens
        self.policy = policy
        self.portal_origin = portal_origin
        self.api_origin = api_origin
        self.index = 0
        self.counts: dict[str, int] = {}
        self.image_count = 0
        self.max_table_rows = 0
        self.table_data_rows = 0
        self.table_chars = 0
        self.truncated_cells = False
        self.has_table = False
        self.summary_title = ""

    def walk(self) -> list[Any]:
        pieces: list[Any] = []
        while self.index < len(self.tokens):
            kind = self.tokens[self.index].type
            if kind == "heading_open":
                pieces.extend(self._heading())
            elif kind == "paragraph_open":
                pieces.extend(self._paragraph())
            elif kind == "bullet_list_open":
                self._append_text(pieces, self._list(ordered=False, depth=0), "list")
            elif kind == "ordered_list_open":
                self._append_text(pieces, self._list(ordered=True, depth=0), "list")
            elif kind == "hr":
                self.index += 1
                pieces.append(_DividerPiece())
                self._bump("thematic_break")
            elif kind in {"fence", "code_block"}:
                self._append_text(pieces, self._fence_text(self.tokens[self.index]), "code")
                self.index += 1
            elif kind == "blockquote_open":
                self._append_text(pieces, self._blockquote(), "quote")
            elif kind == "table_open":
                table = self._table()
                if table is not None:
                    pieces.append(table)
            elif kind == "html_block":
                text = self._escape_text(self.tokens[self.index].content.strip())
                self.index += 1
                self._append_text(pieces, text, "paragraph")
            else:
                raise MarkdownRenderError(kind)
        return pieces

    def _append_text(self, pieces: list[Any], text: str, kind: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        pieces.append(_TextPiece(cleaned, kind))
        self._bump(kind)

    def _bump(self, kind: str) -> None:
        self.counts[kind] = self.counts.get(kind, 0) + 1

    def _peek(self) -> Any:
        if self.index >= len(self.tokens):
            raise MarkdownRenderError("truncated")
        return self.tokens[self.index]

    def _consume(self, expected: str) -> Any:
        token = self._peek()
        if token.type != expected:
            raise MarkdownRenderError(f"expected {expected}, got {token.type}")
        self.index += 1
        return token

    def _heading(self) -> list[_TextPiece]:
        self._consume("heading_open")
        inline = self._consume("inline")
        self._consume("heading_close")
        children = inline.children or []
        plain = self._inline_mrkdwn(children, plain=True, count_images=False)
        text = self._inline_mrkdwn(children, count_images=True)
        if plain and not self.summary_title:
            self.summary_title = plain
        if not text:
            return []
        self._bump("heading")
        return [_TextPiece(f"*{text}*", "heading")]

    def _paragraph(self) -> list[Any]:
        self._consume("paragraph_open")
        inline = self._consume("inline")
        self._consume("paragraph_close")
        pieces = self._inline_segments(inline.children or [])
        for piece in pieces:
            if isinstance(piece, _TextPiece):
                self._bump("paragraph")
        return pieces

    def _inline_segments(self, children: list[Any]) -> list[Any]:
        pieces: list[Any] = []
        start = 0
        for index, child in enumerate(children):
            if child.type != "image":
                continue
            if start < index:
                text = self._inline_mrkdwn(children[start:index])
                if text:
                    pieces.append(_TextPiece(text, "paragraph"))
            pieces.append(self._image_piece(child))
            start = index + 1
        if start < len(children):
            text = self._inline_mrkdwn(children[start:])
            if text:
                pieces.append(_TextPiece(text, "paragraph"))
        return pieces

    def _image_piece(self, token: Any) -> _ImagePiece:
        self.image_count += 1
        self._bump("image")
        alt = (token.content or "image").strip() or "image"
        raw_url = str((token.attrs or {}).get("src") or "")
        resolved = _resolve_url(raw_url, self.portal_origin, self.api_origin)
        return _ImagePiece(alt=alt, raw_url=raw_url, resolved_url=resolved)

    def _list(self, *, ordered: bool, depth: int) -> str:
        close = "ordered_list_close" if ordered else "bullet_list_close"
        self.index += 1
        lines: list[str] = []
        number = 1
        while self._peek().type != close:
            if self._peek().type != "list_item_open":
                raise MarkdownRenderError(self._peek().type)
            marker = self._peek().info or str(number)
            self.index += 1
            item_lines = self._list_item_lines(depth)
            self._consume("list_item_close")
            prefix = f"{marker}." if ordered else "•"
            indent = "    " * depth
            if not item_lines:
                lines.append(f"{indent}{prefix}")
            else:
                first, *rest = item_lines
                lines.append(f"{indent}{prefix} {first}")
                pad = " " * (len(indent) + len(prefix) + 1)
                lines.extend(f"{pad}{extra}" for extra in rest)
            number += 1
        self._consume(close)
        return "\n".join(lines)

    def _list_item_lines(self, depth: int) -> list[str]:
        lines: list[str] = []
        while self._peek().type != "list_item_close":
            token = self._peek()
            if token.type == "paragraph_open":
                self.index += 1
                inline = self._consume("inline")
                self._consume("paragraph_close")
                text = self._inline_mrkdwn(inline.children or [])
                if text:
                    lines.extend(text.split("\n"))
            elif token.type in {"bullet_list_open", "ordered_list_open"}:
                nested = self._list(ordered=token.type == "ordered_list_open", depth=depth + 1)
                if nested:
                    lines.extend(nested.split("\n"))
            elif token.type in {"fence", "code_block"}:
                lines.extend(self._fence_text(token).split("\n"))
                self.index += 1
            else:
                raise MarkdownRenderError(token.type)
        return lines

    def _blockquote(self) -> str:
        self._consume("blockquote_open")
        lines: list[str] = []
        while self._peek().type != "blockquote_close":
            token = self._peek()
            if token.type == "paragraph_open":
                self.index += 1
                inline = self._consume("inline")
                self._consume("paragraph_close")
                text = self._inline_mrkdwn(inline.children or [])
                if text:
                    lines.append(f"> {text}")
            elif token.type in {"bullet_list_open", "ordered_list_open"}:
                rendered = self._list(ordered=token.type == "ordered_list_open", depth=0)
                lines.extend(f"> {line}" if line else ">" for line in rendered.split("\n"))
            elif token.type == "blockquote_open":
                inner = self._blockquote()
                lines.extend(f"> {line}" for line in inner.split("\n"))
            else:
                raise MarkdownRenderError(token.type)
        self._consume("blockquote_close")
        return "\n".join(lines)

    def _fence_text(self, token: Any) -> str:
        lang = (token.info or "").strip()
        body = self._escape_text(token.content.removesuffix("\n"), emoji=False)
        fence = "````" if "```" in body else "```"
        return f"{fence}{lang}\n{body}\n{fence}"

    def _table(self) -> _TablePiece | None:
        self._consume("table_open")
        rows: list[list[str]] = []
        while self._peek().type != "table_close":
            kind = self._peek().type
            if kind in {"thead_open", "tbody_open", "thead_close", "tbody_close"}:
                self.index += 1
                continue
            if kind == "tr_open":
                rows.append(self._table_row())
                continue
            raise MarkdownRenderError(kind)
        self._consume("table_close")
        if not rows:
            return None
        width = min(SLACK_TABLE_MAX_COLUMNS, max(len(row) for row in rows))
        if width == 0:
            return None

        self.has_table = True
        self._bump("table")
        self.table_chars += sum(len(cell) for row in rows for cell in row)
        data_rows = max(0, len(rows) - 1)
        self.table_data_rows += data_rows
        self.max_table_rows = max(self.max_table_rows, data_rows)
        if any(len(row) > SLACK_TABLE_MAX_COLUMNS for row in rows):
            self.truncated_cells = True

        rendered_rows: list[list[dict[str, str]]] = []
        for row in rows:
            cells: list[dict[str, str]] = []
            for cell in row[:SLACK_TABLE_MAX_COLUMNS]:
                shown, cut = _truncate_cell(cell.strip() or " ", self.policy.cell_max_chars)
                if cut:
                    self.truncated_cells = True
                cells.append({"type": "raw_text", "text": shown})
            while len(cells) < width:
                cells.append({"type": "raw_text", "text": " "})
            rendered_rows.append(cells)

        return _TablePiece(
            block={
                "type": "table",
                "column_settings": [{"is_wrapped": True} for _ in range(width)],
                "rows": rendered_rows,
            }
        )

    def _table_row(self) -> list[str]:
        self._consume("tr_open")
        cells: list[str] = []
        while self._peek().type != "tr_close":
            kind = self._peek().type
            if kind not in {"th_open", "td_open"}:
                raise MarkdownRenderError(kind)
            self.index += 1
            inline = self._consume("inline")
            cells.append(self._inline_mrkdwn(inline.children or [], plain=True))
            self._consume("th_close" if kind == "th_open" else "td_close")
        self._consume("tr_close")
        return cells

    def _inline_mrkdwn(
        self,
        children: list[Any],
        *,
        plain: bool = False,
        count_images: bool = True,
    ) -> str:
        parts: list[str] = []
        index = 0
        while index < len(children):
            piece, index = self._render_inline_at(children, index, plain=plain, count_images=count_images)
            parts.append(piece)
        return "".join(parts).strip()

    def _render_inline_at(
        self,
        children: list[Any],
        index: int,
        *,
        plain: bool,
        count_images: bool,
    ) -> tuple[str, int]:
        token = children[index]
        kind = token.type
        if kind == "text":
            content = token.content if plain else self._escape_text(token.content)
            return content, index + 1
        if kind in {"softbreak", "hardbreak"}:
            return "\n", index + 1
        if kind == "code_inline":
            if plain:
                return token.content, index + 1
            return f"`{self._escape_text(token.content, emoji=False)}`", index + 1
        if kind in _CLOSE_FOR_OPEN:
            inner, nxt = self._render_until(
                children,
                index + 1,
                _CLOSE_FOR_OPEN[kind],
                plain=plain,
                count_images=count_images,
            )
            if plain:
                return inner, nxt
            marker = _OPEN_MARKERS[kind]
            return f"{marker}{inner}{marker}", nxt
        if kind == "link_open":
            href = str((token.attrs or {}).get("href") or "")
            inner, nxt = self._render_until(
                children,
                index + 1,
                "link_close",
                plain=plain,
                count_images=count_images,
            )
            if plain:
                return inner, nxt
            url = _resolve_url(href, self.portal_origin, self.api_origin)
            label = inner.strip().replace("|", "/") or url
            if not url:
                return label, nxt
            return f"<{url}|{label}>", nxt
        if kind == "image":
            if count_images:
                self.image_count += 1
                self._bump("image")
            alt = (token.content or "image").strip() or "image"
            if plain:
                return alt, index + 1
            raw_url = str((token.attrs or {}).get("src") or "")
            return _chart_slack_link(raw_url, alt, self.portal_origin, self.api_origin), index + 1
        if kind == "html_inline":
            return (token.content if plain else self._escape_text(token.content)), index + 1
        if kind.endswith("_close"):
            return "", index + 1
        raise MarkdownRenderError(kind)

    def _render_until(
        self,
        children: list[Any],
        index: int,
        close_type: str,
        *,
        plain: bool,
        count_images: bool,
    ) -> tuple[str, int]:
        parts: list[str] = []
        while index < len(children):
            if children[index].type == close_type:
                return "".join(parts), index + 1
            piece, index = self._render_inline_at(
                children,
                index,
                plain=plain,
                count_images=count_images,
            )
            parts.append(piece)
        raise MarkdownRenderError(f"unclosed {close_type}")

    def _escape_text(self, text: str, *, emoji: bool = True) -> str:
        if emoji:
            text = _replace_emoji_shortcodes(text)
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _summary_text(pieces: list[Any]) -> tuple[str, str]:
    heading = ""
    body = ""
    for piece in pieces:
        if not isinstance(piece, _TextPiece):
            continue
        if piece.kind == "heading" and not heading:
            heading = piece.text
        elif piece.kind in {"paragraph", "list", "quote", "code"} and not body:
            body = piece.text
    return heading, body


def _pack_blocks(
    pieces: list[Any],
    policy: SlackMarkdownPolicy,
    portal_origin: str | None,
    api_origin: str | None,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        text = "\n\n".join(buffer).strip()
        buffer.clear()
        if not text:
            return
        for chunk in _split_mrkdwn(text, policy.section_max_chars):
            blocks.append(_section(chunk))

    for piece in pieces:
        if isinstance(piece, _TextPiece):
            buffer.append(piece.text)
        elif isinstance(piece, _DividerPiece):
            flush()
            blocks.append({"type": "divider"})
        elif isinstance(piece, _TablePiece):
            flush()
            blocks.append(piece.block)
        elif isinstance(piece, _ImagePiece):
            flush()
            blocks.append(_image_block(piece, portal_origin=portal_origin, api_origin=api_origin))
    flush()
    return blocks


def image_upload_block_for_src(
    raw_url: str,
    alt: str,
    *,
    portal_origin: str | None,
    api_origin: str | None,
) -> dict[str, Any] | None:
    """Build an ``_image_upload`` placeholder when Slack needs to host the bytes."""
    piece = _ImagePiece(
        alt=alt or "image",
        raw_url=raw_url,
        resolved_url=_resolve_url(raw_url, portal_origin, api_origin),
    )
    block = _image_block(piece, portal_origin=portal_origin, api_origin=api_origin)
    return block if block.get("type") == "_image_upload" else None


def _image_block(
    piece: _ImagePiece,
    *,
    portal_origin: str | None,
    api_origin: str | None,
) -> dict[str, Any]:
    alt = piece.alt.replace("\n", " ")[:2000] or "image"
    fallback = _chart_slack_link(piece.raw_url, alt, portal_origin, api_origin)
    extension = _image_extension(piece.resolved_url)
    if extension == "" and not _is_svg_url(piece.resolved_url):
        return _section(fallback)
    document = parse_document_image_location(piece.raw_url) or parse_document_image_location(piece.resolved_url)
    if document is not None:
        return {
            "type": "_image_upload",
            "source": SlackImageUploadSource.DOCUMENT,
            "document_id": document.document_id,
            "filename": document.filename,
            "alt_text": alt,
            "url": piece.resolved_url,
            "upload_filename": document.filename,
            "fallback_mrkdwn": fallback,
        }
    chart_png = chart_static_png_filename(piece.resolved_url) or chart_static_png_filename(
        chart_png_url_for_svg_url(piece.resolved_url)
    )
    if chart_png and _is_owned_origin(piece.resolved_url, portal_origin, api_origin):
        return _chart_upload_block(alt, chart_png, piece.resolved_url, fallback)
    if extension == _SVG_EXTENSION or _is_svg_url(piece.resolved_url):
        return _section(fallback)
    if _is_public_https(piece.resolved_url):
        return {"type": "image", "image_url": piece.resolved_url, "alt_text": alt}
    if _is_owned_origin(piece.resolved_url, portal_origin, api_origin):
        return {
            "type": "_image_upload",
            "source": SlackImageUploadSource.URL,
            "alt_text": alt,
            "url": piece.resolved_url,
            "upload_filename": _upload_filename(piece.resolved_url),
            "fallback_mrkdwn": fallback,
        }
    return _section(fallback)


def _image_extension(url: str) -> str:
    path = urlparse(url).path.lower()
    for extension in _IMAGE_EXTENSIONS:
        if path.endswith(extension):
            return extension
    return ""


def _is_svg_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(_SVG_EXTENSION)


def _chart_upload_block(
    alt: str,
    png_filename: str,
    resolved_url: str,
    fallback: str,
) -> dict[str, Any]:
    return {
        "type": "_image_upload",
        "source": SlackImageUploadSource.CHART,
        "filename": png_filename,
        "alt_text": alt,
        "url": resolved_url,
        "upload_filename": png_filename,
        "fallback_mrkdwn": fallback,
    }


def _upload_filename(url: str, *, force_png: bool = False) -> str:
    extension = ".png" if force_png else (_image_extension(url) or ".png")
    stem = Path(urlparse(url).path).stem or "image"
    name = f"{stem}.png" if force_png else Path(urlparse(url).path).name
    cleaned = _FILENAME_CLEAN.sub("_", name).strip("._")[:80]
    if not cleaned.lower().endswith(_IMAGE_EXTENSIONS):
        cleaned = f"{cleaned or 'image'}{extension}"
    return cleaned


def _is_public_https(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith((".local", ".internal")):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )


def _is_owned_origin(url: str, portal_origin: str | None, api_origin: str | None) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    for origin in (portal_origin, api_origin):
        if not origin:
            continue
        origin_host = (urlparse(origin).hostname or "").lower()
        if origin_host and origin_host == host:
            return True
    return False


def _truncate_cell(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text or " ", False
    if limit <= 1:
        return (text[:limit] or " "), True
    return text[: limit - 1] + "…", True


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "…"


def _split_mrkdwn(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = line
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _degraded_plan(
    markdown: str,
    reason: str,
    *,
    node_counts: dict[str, int] | None = None,
) -> SlackMarkdownPlan:
    return SlackMarkdownPlan(
        route=RenderRoute.DEGRADED,
        blocks=[],
        summary_heading="",
        summary_body="",
        summary_title="",
        table_data_rows=0,
        image_count=0,
        truncated_cells=False,
        degrade_reason=reason,
        node_counts=node_counts or {},
        markdown=markdown,
    )
