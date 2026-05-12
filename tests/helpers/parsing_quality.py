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


def normalize_blocks_document(blocks_document: dict[str, Any]) -> dict[str, Any]:
    """Return the persisted blocks document shape used for golden comparison."""
    blocks = blocks_document.get("blocks", [])
    if not isinstance(blocks, list):
        blocks = []
    return {
        "schema_version": blocks_document.get("schema_version", 1),
        "parser": blocks_document.get("parser", "docling"),
        "blocks": blocks,
    }


def blocks_match_golden(actual: dict[str, Any], golden: dict[str, Any]) -> bool:
    return normalize_blocks_document(actual) == normalize_blocks_document(golden)


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
    assert blocks_match_golden(blocks_document, golden), fixture["id"]
    quality = fixture.get("quality")
    if isinstance(quality, dict) and quality:
        assert_fixture_quality(blocks_document, quality)


def write_blocks_golden(blocks_document: dict[str, Any], fixture: dict[str, Any]) -> Path:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    path = integration_baseline_path(fixture)
    payload = normalize_blocks_document(blocks_document)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
