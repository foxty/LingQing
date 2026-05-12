"""Map DoclingDocument JSON exports to blocks.json IR."""

from __future__ import annotations

from typing import Any

from apps.shared.document.parsers.blocks_common import dedupe_consecutive_headings, normalize_block_text
from apps.shared.document.parsers.markdown_blocks import markdown_to_blocks

_HEADING_LABELS = frozenset(
    {
        "title",
        "section_header",
        "heading",
        "subtitle-level-1",
        "subtitle-level-2",
        "page_header",
    }
)
_TABLE_LABELS = frozenset({"table", "document_index"})


def docling_json_to_blocks(json_content: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Convert Docling ``json_content`` to indexable blocks, or None if unsupported."""
    if not isinstance(json_content, dict):
        return None

    texts = json_content.get("texts")
    if not isinstance(texts, list) or not texts:
        return None

    page_heights = _page_heights(json_content)
    blocks: list[dict[str, Any]] = []
    for item in texts:
        block = _text_item_to_block(item, page_heights)
        if block:
            blocks.append(block)

    tables = json_content.get("tables")
    if isinstance(tables, list):
        for table in tables:
            block = _table_item_to_block(table, page_heights)
            if block:
                blocks.append(block)

    pictures = json_content.get("pictures")
    if isinstance(pictures, list):
        for picture in pictures:
            block = _picture_item_to_block(picture, page_heights)
            if block:
                blocks.append(block)

    if not blocks:
        return None
    return dedupe_consecutive_headings(blocks)


def supplement_tables_from_markdown(blocks: list[dict[str, Any]], markdown: str) -> list[dict[str, Any]]:
    """Append markdown table blocks when Docling JSON did not emit any tables."""
    if any(block.get("type") == "table" for block in blocks):
        return blocks
    if not markdown.strip():
        return blocks

    md_tables = [block for block in markdown_to_blocks(markdown) if block.get("type") == "table"]
    if not md_tables:
        return blocks

    existing_text = "\n".join(str(block.get("text", "")) for block in blocks)
    supplemented = list(blocks)
    for table in md_tables:
        table_text = str(table.get("text", "")).strip()
        if table_text and table_text not in existing_text:
            supplemented.append(table)
            existing_text = f"{existing_text}\n{table_text}"
    return dedupe_consecutive_headings(supplemented)


def _text_item_to_block(item: dict[str, Any], page_heights: dict[int, float]) -> dict[str, Any] | None:
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    label = str(item.get("label") or item.get("type") or "paragraph").lower()
    if label in _TABLE_LABELS:
        block_type = "table"
    elif label in _HEADING_LABELS:
        block_type = "heading"
    else:
        block_type = "text"
    block: dict[str, Any] = {
        "type": block_type,
        "text": normalize_block_text(text),
    }
    return _apply_layout(block, item, page_heights)


def _table_item_to_block(item: dict[str, Any], page_heights: dict[int, float]) -> dict[str, Any] | None:
    text = _extract_table_text(item)
    if not text:
        return None
    block: dict[str, Any] = {"type": "table", "text": text}
    return _apply_layout(block, item, page_heights)


def _picture_item_to_block(item: dict[str, Any], page_heights: dict[int, float]) -> dict[str, Any] | None:
    uri = _extract_picture_uri(item)
    if not uri:
        return None
    caption = item.get("caption") or item.get("text")
    block: dict[str, Any] = {
        "type": "image",
        "uri": uri,
        "caption": str(caption).strip() if isinstance(caption, str) and caption.strip() else None,
    }
    return _apply_layout(block, item, page_heights)


def _apply_layout(block: dict[str, Any], item: dict[str, Any], page_heights: dict[int, float]) -> dict[str, Any]:
    page = _extract_page_no(item)
    if page is not None:
        block["page"] = page
    bbox = _extract_bbox(item, page, page_heights)
    if bbox is not None:
        block["bbox"] = bbox
    return block


def _page_heights(json_content: dict[str, Any]) -> dict[int, float]:
    pages = json_content.get("pages")
    heights: dict[int, float] = {}
    entries: list[tuple[Any, Any]]
    if isinstance(pages, dict):
        entries = list(pages.items())
    elif isinstance(pages, list):
        entries = [(None, page) for page in pages]
    else:
        return heights
    for key, page in entries:
        if not isinstance(page, dict):
            continue
        page_no = page.get("page_no")
        if not isinstance(page_no, int) and key is not None:
            try:
                page_no = int(key)
            except (TypeError, ValueError):
                page_no = None
        size = page.get("size")
        height = size.get("height") if isinstance(size, dict) else None
        if isinstance(page_no, int) and isinstance(height, (int, float)) and height > 0:
            heights[page_no] = float(height)
    return heights


def _extract_bbox(
    item: dict[str, Any],
    page_no: int | None,
    page_heights: dict[int, float],
) -> dict[str, float] | None:
    prov = item.get("prov")
    if not isinstance(prov, list):
        return None
    for entry in prov:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("bbox")
        if not isinstance(raw, dict):
            continue
        entry_page = entry.get("page_no") if isinstance(entry.get("page_no"), int) else page_no
        bbox = _normalize_bbox(raw, entry_page, page_heights)
        if bbox is not None:
            return bbox
    return None


def _normalize_bbox(
    raw: dict[str, Any],
    page_no: int | None,
    page_heights: dict[int, float],
) -> dict[str, float] | None:
    try:
        left, top, right, bottom = (float(raw[key]) for key in ("l", "t", "r", "b"))
    except (KeyError, TypeError, ValueError):
        return None
    origin = str(raw.get("coord_origin") or "TOPLEFT").upper()
    if origin == "BOTTOMLEFT":
        height = page_heights.get(page_no) if page_no is not None else None
        if height is None:
            return None
        top, bottom = height - top, height - bottom
    if left > right:
        left, right = right, left
    if top > bottom:
        top, bottom = bottom, top
    if right <= left or bottom <= top:
        return None
    return {"left": left, "top": top, "right": right, "bottom": bottom}


def _extract_page_no(item: dict[str, Any]) -> int | None:
    prov = item.get("prov")
    if not isinstance(prov, list):
        return None
    for entry in prov:
        if not isinstance(entry, dict):
            continue
        page_no = entry.get("page_no")
        if isinstance(page_no, int) and page_no > 0:
            return page_no
    return None


def _extract_table_text(item: dict[str, Any]) -> str:
    for key in ("text", "md", "markdown", "md_content"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_block_text(value)

    data = item.get("data")
    if isinstance(data, dict):
        grid_text = _grid_data_to_markdown(data)
        if grid_text:
            return grid_text
    return ""


def _grid_data_to_markdown(data: dict[str, Any]) -> str:
    grid = _extract_grid(data)
    if not grid:
        return ""
    return _grid_to_markdown_table(grid)


def _extract_grid(data: dict[str, Any]) -> list[list[str]]:
    table_cells = data.get("table_cells")
    if isinstance(table_cells, list) and table_cells:
        num_rows = int(data.get("num_rows") or 0)
        num_cols = int(data.get("num_cols") or 0)
        if num_rows <= 0 or num_cols <= 0:
            num_rows, num_cols = _infer_grid_size(table_cells)
        grid = [["" for _ in range(num_cols)] for _ in range(num_rows)]
        for cell in table_cells:
            if not isinstance(cell, dict):
                continue
            row_idx = int(cell.get("start_row_offset_idx") or cell.get("row") or 0)
            col_idx = int(cell.get("start_col_offset_idx") or cell.get("col") or 0)
            text = str(cell.get("text") or "").strip()
            if 0 <= row_idx < num_rows and 0 <= col_idx < num_cols and text:
                if grid[row_idx][col_idx]:
                    grid[row_idx][col_idx] = f"{grid[row_idx][col_idx]} {text}"
                else:
                    grid[row_idx][col_idx] = text
        return grid

    raw_grid = data.get("grid")
    if isinstance(raw_grid, list):
        return _normalize_grid_rows(raw_grid)
    return []


def _infer_grid_size(table_cells: list[Any]) -> tuple[int, int]:
    max_row = 0
    max_col = 0
    for cell in table_cells:
        if not isinstance(cell, dict):
            continue
        row_idx = int(cell.get("start_row_offset_idx") or cell.get("row") or 0)
        col_idx = int(cell.get("start_col_offset_idx") or cell.get("col") or 0)
        row_span = int(cell.get("row_span") or 1)
        col_span = int(cell.get("col_span") or 1)
        max_row = max(max_row, row_idx + row_span)
        max_col = max(max_col, col_idx + col_span)
    return max(max_row, 1), max(max_col, 1)


def _normalize_grid_rows(raw_grid: list[Any]) -> list[list[str]]:
    grid: list[list[str]] = []
    for row in raw_grid:
        if isinstance(row, list):
            grid.append([str(cell).strip() for cell in row])
        elif isinstance(row, dict):
            text = str(row.get("text") or "").strip()
            grid.append([text] if text else [""])
    return grid


def _grid_to_markdown_table(grid: list[list[str]]) -> str:
    if not grid:
        return ""
    width = max(len(row) for row in grid)
    if width == 0:
        return ""

    normalized_rows: list[list[str]] = []
    for row in grid:
        padded = [str(cell).strip() for cell in row] + [""] * (width - len(row))
        normalized_rows.append(padded[:width])

    non_empty_rows = [row for row in normalized_rows if any(cell for cell in row)]
    if not non_empty_rows:
        return ""

    lines = ["| " + " | ".join(row) + " |" for row in non_empty_rows]
    if len(lines) == 1:
        lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
    else:
        separator = "| " + " | ".join("---" for _ in range(width)) + " |"
        lines.insert(1, separator)
    return normalize_block_text("\n".join(lines))


def _extract_picture_uri(item: dict[str, Any]) -> str | None:
    for key in ("uri", "url", "path"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    image = item.get("image")
    if isinstance(image, dict):
        for key in ("uri", "url", "path"):
            value = image.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None
