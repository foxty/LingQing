"""Helpers for parsing quality fixtures and assertions."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from apps.shared.document.manifest import persist_parse_images, summarize_blocks
from apps.shared.infra.storage.base import FileStorage
from apps.shared.infra.storage.file_storage import LocalFileStorage

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "parsing"
GOLDEN_TENANT_ID = 1
GOLDEN_DOCUMENT_ID = 1
SOURCES_DIR = FIXTURES_DIR / "sources"
BASELINES_DIR = FIXTURES_DIR / "baselines"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"
DOCLING_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "deploy" / "env" / "docling.version"
GOLDEN_BBOX_DECIMALS = 2


def pinned_docling_image() -> str:
    if DOCLING_VERSION_FILE.is_file():
        image = DOCLING_VERSION_FILE.read_text(encoding="utf-8").strip()
        if image:
            return image
    manifest = load_parsing_manifest()
    image = manifest.get("docling_image")
    if isinstance(image, str) and image.strip():
        return image.strip()
    raise ValueError("Pinned Docling image not configured")


def load_parsing_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def list_unit_fixtures() -> list[dict[str, Any]]:
    manifest = load_parsing_manifest()
    fixtures = manifest.get("unit_fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("parsing manifest must contain a unit_fixtures list")
    return fixtures


def list_integration_fixtures() -> list[dict[str, Any]]:
    manifest = load_parsing_manifest()
    fixtures = manifest.get("integration_fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("parsing manifest must contain an integration_fixtures list")
    return fixtures


def integration_source_path(fixture: dict[str, Any]) -> Path:
    return SOURCES_DIR / fixture["source_file"]


def integration_baseline_path(fixture: dict[str, Any]) -> Path:
    relative = fixture.get("baseline")
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError(f"integration fixture {fixture.get('id')} missing baseline path")
    return FIXTURES_DIR / relative


def list_available_integration_sources() -> list[Path]:
    return sorted(
        path
        for path in SOURCES_DIR.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )


def load_golden_blocks(relative_name: str) -> dict[str, Any]:
    with (FIXTURES_DIR / relative_name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_integration_golden(fixture: dict[str, Any]) -> dict[str, Any]:
    with integration_baseline_path(fixture).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_block_bbox(block: dict[str, Any]) -> dict[str, Any]:
    bbox = block.get("bbox")
    if not isinstance(bbox, dict):
        return block
    rounded = {
        key: round(float(value), GOLDEN_BBOX_DECIMALS)
        for key, value in bbox.items()
        if isinstance(value, (int, float))
    }
    if len(rounded) != 4:
        return block
    return {**block, "bbox": rounded}


def normalize_blocks_document(blocks_document: dict[str, Any], *, for_compare: bool = False) -> dict[str, Any]:
    """Return the persisted blocks document shape used for golden comparison."""
    blocks = blocks_document.get("blocks", [])
    if not isinstance(blocks, list):
        blocks = []
    normalized_blocks = [_normalize_block_bbox(block) if for_compare and isinstance(block, dict) else block for block in blocks]
    return {
        "schema_version": blocks_document.get("schema_version", 1),
        "parser": blocks_document.get("parser", "docling"),
        "blocks": normalized_blocks,
    }


def golden_blocks_diff(actual: dict[str, Any], golden: dict[str, Any]) -> str:
    """Build a concise human-readable diff for golden block mismatches."""
    actual_doc = normalize_blocks_document(actual, for_compare=True)
    golden_doc = normalize_blocks_document(golden, for_compare=True)
    actual_blocks = actual_doc["blocks"]
    golden_blocks = golden_doc["blocks"]
    lines = [
        f"block count: actual={len(actual_blocks)} golden={len(golden_blocks)}",
    ]
    max_blocks = max(len(actual_blocks), len(golden_blocks))
    diff_count = 0
    for index in range(max_blocks):
        actual_block = actual_blocks[index] if index < len(actual_blocks) else None
        golden_block = golden_blocks[index] if index < len(golden_blocks) else None
        if actual_block == golden_block:
            continue
        diff_count += 1
        if diff_count > 5:
            continue
        lines.append(f"block[{index}]:")
        if actual_block is None:
            lines.append(f"  missing in actual: {json.dumps(golden_block, ensure_ascii=False)[:240]}")
            continue
        if golden_block is None:
            lines.append(f"  extra in actual: {json.dumps(actual_block, ensure_ascii=False)[:240]}")
            continue
        for key in sorted(set(actual_block) | set(golden_block)):
            actual_value = actual_block.get(key)
            golden_value = golden_block.get(key)
            if actual_value != golden_value:
                lines.append(f"  {key}: actual={actual_value!r} golden={golden_value!r}")
    if diff_count > 5:
        lines.append(f"... and {diff_count - 5} more differing blocks")
    return "\n".join(lines)


def blocks_match_golden(actual: dict[str, Any], golden: dict[str, Any]) -> bool:
    return normalize_blocks_document(actual, for_compare=True) == normalize_blocks_document(golden, for_compare=True)


async def persist_integration_blocks(
    blocks_document: dict[str, Any],
    *,
    file_storage: FileStorage | None = None,
    tenant_id: int = GOLDEN_TENANT_ID,
    document_id: int = GOLDEN_DOCUMENT_ID,
) -> dict[str, Any]:
    """Rewrite parse image URIs the same way production ``_persist_blocks`` does."""
    storage = file_storage or LocalFileStorage()
    blocks = [block for block in blocks_document.get("blocks", []) if isinstance(block, dict)]
    persisted = await persist_parse_images(
        storage,
        tenant_id=tenant_id,
        document_id=document_id,
        blocks=blocks,
    )
    return {**blocks_document, "blocks": persisted}


def block_metrics(blocks_document: dict[str, Any]) -> dict[str, Any]:
    blocks = blocks_document.get("blocks", [])
    if not isinstance(blocks, list):
        return {"block_count": 0, "type_counts": {}, "median_text_chars": 0}

    type_counts = summarize_blocks(blocks)
    text_lengths = [
        len(str(block.get("text", "")).strip())
        for block in blocks
        if isinstance(block, dict) and block.get("type") in {"text", "heading", "table"}
    ]
    median_text_chars = int(statistics.median(text_lengths)) if text_lengths else 0
    return {
        "block_count": len(blocks),
        "type_counts": type_counts,
        "median_text_chars": median_text_chars,
    }


def chunk_metrics(blocks_document: dict[str, Any]) -> dict[str, Any]:
    from apps.shared.document.chunking import segment_blocks

    segments = segment_blocks(blocks_document)
    lengths = [len(segment.text) for segment in segments if segment.text.strip()]
    return {
        "chunk_count": len(segments),
        "median_chunk_chars": int(statistics.median(lengths)) if lengths else 0,
        "min_chunk_chars": min(lengths) if lengths else 0,
        "combined_text": "\n".join(segment.text for segment in segments),
    }


def assert_fixture_quality(blocks_document: dict[str, Any], expectations: dict[str, Any]) -> None:
    block_stats = block_metrics(blocks_document)
    chunk_stats = chunk_metrics(blocks_document)
    type_counts = block_stats["type_counts"]

    if "min_blocks" in expectations:
        assert block_stats["block_count"] >= expectations["min_blocks"]
    if "max_blocks" in expectations:
        assert block_stats["block_count"] <= expectations["max_blocks"]
    if "min_text_blocks" in expectations:
        assert type_counts.get("text", 0) >= expectations["min_text_blocks"]
    if "min_table_blocks" in expectations:
        assert type_counts.get("table", 0) >= expectations["min_table_blocks"]
    if "min_heading_blocks" in expectations:
        assert type_counts.get("heading", 0) >= expectations["min_heading_blocks"]
    if "max_heading_blocks" in expectations:
        assert type_counts.get("heading", 0) <= expectations["max_heading_blocks"]
    if "max_chunks" in expectations:
        assert chunk_stats["chunk_count"] <= expectations["max_chunks"]
    if "min_chunks" in expectations:
        assert chunk_stats["chunk_count"] >= expectations["min_chunks"]
    if "min_median_chunk_chars" in expectations:
        assert chunk_stats["median_chunk_chars"] >= expectations["min_median_chunk_chars"]

    for phrase in expectations.get("must_contain", []):
        assert phrase in chunk_stats["combined_text"], f"missing phrase in chunks: {phrase}"

    for phrase in expectations.get("must_not_contain", []):
        assert phrase not in chunk_stats["combined_text"], f"unexpected phrase in chunks: {phrase}"


def assert_integration_golden(blocks_document: dict[str, Any], fixture: dict[str, Any]) -> None:
    golden = load_integration_golden(fixture)
    if not blocks_match_golden(blocks_document, golden):
        diff = golden_blocks_diff(blocks_document, golden)
        raise AssertionError(f"{fixture['id']} golden mismatch:\n{diff}")
    quality = fixture.get("quality")
    if isinstance(quality, dict) and quality:
        assert_fixture_quality(blocks_document, quality)


def write_blocks_golden(blocks_document: dict[str, Any], fixture: dict[str, Any]) -> Path:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    path = integration_baseline_path(fixture)
    payload = normalize_blocks_document(blocks_document)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
