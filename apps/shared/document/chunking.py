"""Block-aware segmentation for vector indexing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_text_splitters import RecursiveCharacterTextSplitter

from apps.shared.document.manifest import INDEXABLE_BLOCK_TYPES
from apps.shared.document.types import BLOCK_TYPE_HEADING, BLOCK_TYPE_IMAGE, BLOCK_TYPE_TABLE, BLOCK_TYPE_TEXT

DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
DEFAULT_MIN_CHARS = 80
DEFAULT_TABLE_MAX_CHARS = 3000
DEFAULT_SHORT_TEXT_THRESHOLD = 120
_MAX_NEARBY_LABELS = 3

SegmentKind = Literal["text", "table", "mixed"]


@dataclass
class BlockUnit:
    """Buffered block content before text splitting."""

    text: str
    block_types: list[str]
    page: int | None = None
    uri: str | None = None
    caption: str | None = None


@dataclass
class ContentSegment:
    """Domain segment produced from parsed document blocks."""

    kind: SegmentKind
    text: str
    block_types: list[str] = field(default_factory=list)
    page: int | None = None
    uri: str | None = None
    caption: str | None = None


def segment_blocks(
    blocks_document: dict[str, Any],
    *,
    max_chars: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    min_chars: int = DEFAULT_MIN_CHARS,
    table_max_chars: int = DEFAULT_TABLE_MAX_CHARS,
) -> list[ContentSegment]:
    """Merge parsed blocks into embedding-sized segments.

    Headings prefix the following content instead of becoming standalone segments.
    Consecutive blocks are buffered up to ``max_chars`` before splitting.
    """
    blocks = blocks_document.get("blocks", [])
    if not isinstance(blocks, list) or not blocks:
        return []

    blocks = _coalesce_short_text_blocks(
        blocks,
        max_chars=max_chars,
        short_threshold=DEFAULT_SHORT_TEXT_THRESHOLD,
    )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chars,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "？", "！", " ", ""],
    )

    merged_buffers = _merge_block_units(blocks, max_chars=max_chars)
    segments: list[ContentSegment] = []
    for unit in merged_buffers:
        if unit.uri:
            segments.append(
                ContentSegment(
                    kind="text",
                    text=unit.text.strip(),
                    block_types=["image"],
                    page=unit.page,
                    uri=unit.uri,
                    caption=unit.caption,
                )
            )
            continue
        split_texts = _split_buffer_text(
            unit.text,
            unit.block_types,
            max_chars=max_chars,
            table_max_chars=table_max_chars,
            min_chars=min_chars,
            splitter=splitter,
        )
        kind = _segment_kind(unit.block_types)
        for text in split_texts:
            if text.strip():
                segments.append(
                    ContentSegment(
                        kind=kind,
                        text=text.strip(),
                        block_types=list(unit.block_types),
                        page=unit.page,
                    )
                )

    if min_chars <= 1 or len(segments) <= 1:
        return segments
    return _merge_small_segments(segments, max_chars=max_chars, min_chars=min_chars)


def _coalesce_short_text_blocks(
    blocks: list[Any],
    *,
    max_chars: int,
    short_threshold: int,
) -> list[Any]:
    """Merge consecutive short text blocks before buffer assembly."""
    coalesced: list[Any] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if not isinstance(block, dict) or block.get("type") != "text" or _layout_box(block.get("bbox")):
            coalesced.append(block)
            index += 1
            continue

        merged_text = str(block.get("text", "")).strip()
        merged_page = block.get("page") if isinstance(block.get("page"), int) else None
        next_index = index + 1
        while next_index < len(blocks):
            candidate_block = blocks[next_index]
            if (
                not isinstance(candidate_block, dict)
                or candidate_block.get("type") != "text"
                or _layout_box(candidate_block.get("bbox"))
            ):
                break

            candidate_text = str(candidate_block.get("text", "")).strip()
            if not candidate_text:
                next_index += 1
                continue

            if len(merged_text) > short_threshold and len(candidate_text) > short_threshold:
                break

            combined = f"{merged_text}\n\n{candidate_text}".strip()
            if len(combined) > max_chars:
                break

            merged_text = combined
            next_index += 1

        if merged_text:
            merged_block: dict[str, Any] = {"type": "text", "text": merged_text}
            if merged_page is not None:
                merged_block["page"] = merged_page
            coalesced.append(merged_block)
        index = next_index

    return coalesced


def _split_buffer_text(
    buffer_text: str,
    block_types: list[str],
    *,
    max_chars: int,
    table_max_chars: int,
    min_chars: int,
    splitter: RecursiveCharacterTextSplitter,
) -> list[str]:
    text = buffer_text.strip()
    if not text:
        return []

    unique_types = set(block_types)
    if unique_types == {"table"}:
        if len(text) <= table_max_chars:
            return [text]
        return _split_markdown_table(text, max_chars=max_chars)

    split_texts = splitter.split_text(text)
    if min_chars <= 1:
        return [part.strip() for part in split_texts if part.strip()]
    return _repair_split_fragments(split_texts, max_chars=max_chars, min_chars=min_chars)


def _split_markdown_table(text: str, *, max_chars: int) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= 2:
        return [text.strip()]

    header_lines = lines[:2]
    data_lines = lines[2:]
    if not data_lines:
        return [text.strip()]

    prefix = "\n".join(header_lines)
    chunks: list[str] = []
    current_rows: list[str] = []
    current_len = len(prefix) + 1

    for row in data_lines:
        row_len = len(row) + 1
        if current_rows and current_len + row_len > max_chars:
            chunks.append("\n".join([prefix, *current_rows]))
            current_rows = []
            current_len = len(prefix) + 1
        current_rows.append(row)
        current_len += row_len

    if current_rows:
        chunks.append("\n".join([prefix, *current_rows]))
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _repair_split_fragments(
    split_texts: list[str],
    *,
    max_chars: int,
    min_chars: int,
) -> list[str]:
    repaired: list[str] = []
    pending = ""

    for part in split_texts:
        text = part.strip()
        if not text:
            continue

        if pending:
            combined = f"{pending}\n\n{text}".strip()
            if len(combined) <= max_chars:
                pending = combined
                continue
            if len(pending) >= min_chars:
                repaired.append(pending)
                pending = text
                continue
            if repaired:
                merged = f"{repaired[-1]}\n\n{pending}".strip()
                if len(merged) <= max_chars:
                    repaired[-1] = merged
                    pending = text
                    continue
            repaired.append(pending)
            pending = text
            continue

        if len(text) < min_chars:
            pending = text
            continue

        repaired.append(text)

    if pending:
        if repaired and len(f"{repaired[-1]}\n\n{pending}".strip()) <= max_chars:
            repaired[-1] = f"{repaired[-1]}\n\n{pending}".strip()
        elif len(pending) >= min_chars or not repaired:
            repaired.append(pending)
        else:
            repaired[-1] = f"{repaired[-1]}\n\n{pending}".strip()

    return repaired


@dataclass(frozen=True)
class _LayoutBox:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


def _labels_by_page(blocks: list[Any]) -> dict[int, list[tuple[str, _LayoutBox]]]:
    labels: dict[int, list[tuple[str, _LayoutBox]]] = {}
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") not in {BLOCK_TYPE_TEXT, BLOCK_TYPE_HEADING}:
            continue
        page = block.get("page")
        text = block.get("text")
        box = _layout_box(block.get("bbox"))
        if not isinstance(page, int) or not isinstance(text, str) or not text.strip() or box is None:
            continue
        labels.setdefault(page, []).append((text.strip(), box))
    return labels


def _layout_box(raw: Any) -> _LayoutBox | None:
    if not isinstance(raw, dict):
        return None
    try:
        box = _LayoutBox(float(raw["left"]), float(raw["top"]), float(raw["right"]), float(raw["bottom"]))
    except (KeyError, TypeError, ValueError):
        return None
    if box.width <= 0 or box.height <= 0:
        return None
    return box


def _nearby_label(block: dict[str, Any], labels: list[tuple[str, _LayoutBox]]) -> str:
    image_box = _layout_box(block.get("bbox"))
    if image_box is None or not labels:
        return ""
    max_gap = min(image_box.width, image_box.height)
    image_area = image_box.width * image_box.height
    nearby: list[tuple[float, float, float, str]] = []
    for text, box in labels:
        if box.width * box.height > image_area * 8:
            continue
        gap = _box_gap(image_box, box)
        if gap is None or gap > max_gap:
            continue
        nearby.append((gap, box.top, box.left, text))
    chosen = sorted(nearby)[:_MAX_NEARBY_LABELS]
    ordered = sorted(chosen, key=lambda item: (item[1], item[2]))
    return "\n\n".join(item[3] for item in ordered)


def _box_gap(image: _LayoutBox, text: _LayoutBox) -> float | None:
    horizontal_overlap = min(image.right, text.right) - max(image.left, text.left)
    vertical_overlap = min(image.bottom, text.bottom) - max(image.top, text.top)
    gaps: list[float] = []
    if horizontal_overlap > 0:
        if text.bottom <= image.top:
            gaps.append(image.top - text.bottom)
        elif text.top >= image.bottom:
            gaps.append(text.top - image.bottom)
        else:
            gaps.append(0.0)
    if vertical_overlap > 0:
        if text.right <= image.left:
            gaps.append(image.left - text.right)
        elif text.left >= image.right:
            gaps.append(text.left - image.right)
        elif horizontal_overlap <= 0:
            gaps.append(0.0)
    if not gaps:
        return None
    return min(gaps)


def _merge_block_units(
    blocks: list[Any],
    *,
    max_chars: int,
) -> list[BlockUnit]:
    buffers: list[BlockUnit] = []
    labels_by_page = _labels_by_page(blocks)
    pending_heading: str | None = None
    buffer_text = ""
    buffer_types: list[str] = []
    buffer_page: int | None = None

    def flush_buffer() -> None:
        nonlocal buffer_text, buffer_types, buffer_page
        if not buffer_text.strip():
            return
        buffers.append(BlockUnit(buffer_text.strip(), list(buffer_types), buffer_page))
        buffer_text = ""
        buffer_types = []
        buffer_page = None

    def append_unit(unit_text: str, block_type: str, page: int | None) -> None:
        nonlocal buffer_text, buffer_types, buffer_page
        candidate = f"{buffer_text}\n\n{unit_text}".strip() if buffer_text else unit_text.strip()
        if buffer_text and len(candidate) > max_chars:
            flush_buffer()
            candidate = unit_text.strip()
        buffer_text = candidate
        buffer_types.append(block_type)
        if buffer_page is None and page is not None:
            buffer_page = page

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "text")
        if block_type not in INDEXABLE_BLOCK_TYPES:
            continue

        page = block.get("page") if isinstance(block.get("page"), int) else None

        if block_type == BLOCK_TYPE_IMAGE:
            caption = block.get("caption")
            caption_text = caption.strip() if isinstance(caption, str) else ""
            nearby = _nearby_label(block, labels_by_page.get(page, []) if page is not None else [])
            heading = pending_heading or ""
            label = caption_text or nearby or heading
            uri = block.get("uri")
            if not label or not isinstance(uri, str) or not uri.strip():
                continue
            flush_buffer()
            buffers.append(BlockUnit(label, ["image"], page, uri.strip(), caption_text or nearby or None))
            continue

        text = block.get("text")
        if block_type in {BLOCK_TYPE_TEXT, BLOCK_TYPE_TABLE, BLOCK_TYPE_HEADING}:
            if not isinstance(text, str) or not text.strip():
                continue
        else:
            continue

        if block_type == BLOCK_TYPE_HEADING:
            pending_heading = text.strip()
            continue

        unit_text = text.strip()
        if pending_heading:
            unit_text = f"{pending_heading}\n\n{unit_text}"
            pending_heading = None

        append_unit(unit_text, block_type, page)

    if pending_heading:
        append_unit(pending_heading, "heading", None)

    flush_buffer()
    return buffers


def _segment_kind(block_types: list[str]) -> SegmentKind:
    if not block_types:
        return "text"
    unique = set(block_types)
    if unique == {"table"}:
        return "table"
    if len(unique) == 1:
        return "text"
    return "mixed"


def _merge_small_segments(
    segments: list[ContentSegment],
    *,
    max_chars: int,
    min_chars: int,
) -> list[ContentSegment]:
    merged: list[ContentSegment] = []
    index = 0
    while index < len(segments):
        current = segments[index]
        if len(current.text) >= min_chars or index + 1 >= len(segments):
            merged.append(current)
            index += 1
            continue

        nxt = segments[index + 1]
        if current.uri or nxt.uri:
            merged.append(current)
            index += 1
            continue
        combined = f"{current.text}\n\n{nxt.text}".strip()
        if len(combined) > max_chars:
            merged.append(current)
            index += 1
            continue

        merged.append(
            ContentSegment(
                kind=_segment_kind(current.block_types + nxt.block_types),
                text=combined,
                block_types=current.block_types + nxt.block_types,
                page=current.page if current.page is not None else nxt.page,
            )
        )
        index += 2

    return merged
