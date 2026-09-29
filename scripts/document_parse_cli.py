#!/usr/bin/env python3
"""CLI for document parse operations."""

# ruff: noqa: T201

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.config import get_file_storage
from apps.shared.db.session import app_db_session
from apps.shared.document.parse_pipeline import DocumentParsePipeline
from apps.shared.document.types import ParseIssueRow, ParseStatusSnapshot
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.tenant.repository import TenantRepository

logger = get_logger(__name__)


async def _resolve_tenant_ids(tenant_id: int | None) -> list[int]:
    if tenant_id is not None:
        return [tenant_id]
    async with app_db_session() as session:
        tenants = await TenantRepository(session).get_active_tenants()
        return [tenant.id for tenant in tenants]


async def handle_parse(args) -> int:
    tenant_ids = await _resolve_tenant_ids(args.tenant_id)
    if not tenant_ids:
        print("No tenants found")
        return 0

    total = 0
    file_storage = get_file_storage()
    for tenant_id in tenant_ids:
        async with app_db_session() as session:
            processing = DocumentParsePipeline(tenant_id, session, file_storage)
            doc_ids = await processing.list_parse_target_ids(
                document_id=args.document_id,
                collection_id=getattr(args, "collection_id", None),
                failed_only=bool(getattr(args, "failed_only", False)),
            )
            for doc_id in doc_ids:
                if args.reparse:
                    await processing.queue_document_reparse(doc_id, triggered_by="cli")
                outcome = await processing.process_document_by_id(doc_id, triggered_by="cli")
                if outcome is None:
                    raise ValueError(f"Document not found: {doc_id}")
                total += 1

    print(f"Processed parse/reparse for {total} document(s)")
    return 0


async def handle_reparse(args) -> int:
    args.reparse = True
    args.failed_only = args.failed_only or False
    if args.all:
        args.failed_only = False
    return await handle_parse(args)


def _print_status_table(payload: ParseStatusSnapshot, *, tenant_id: int | None) -> None:
    doc_rows = payload["documents"]
    parse_rows = payload["parse_index"]
    vector_rows = payload["vector_index"]

    tenant_label = f"Tenant {tenant_id}" if tenant_id else "All tenants"
    print(f"\n📄 Document Parse Status ({tenant_label})\n")

    if not doc_rows and not parse_rows:
        print("No documents found.")
        return

    print("documents.status (business lifecycle)")
    print(f"{'Tenant':>8} | {'Status':>12} | {'Count':>7}")
    print("-" * 34)
    for row in sorted(doc_rows, key=lambda item: (item["tenant_id"], item["status"])):
        print(f"{row['tenant_id']:>8} | {row['status']:>12} | {row['count']:>7}")

    print("\nresource_index parse pipeline")
    print(f"{'Tenant':>8} | {'Total':>7} | {'Parsed':>7} | {'Async':>7} | {'Errors':>7} | {'Last Parsed':>19}")
    print("-" * 68)
    if parse_rows:
        for row in parse_rows:
            last_parsed = row["last_parsed_at"].strftime("%Y-%m-%d %H:%M:%S") if row["last_parsed_at"] else "-"
            print(
                f"{row['tenant_id']:>8} | {row['total']:>7} | {row['parsed']:>7} | "
                f"{row['async_pending']:>7} | {row['parse_errors']:>7} | {last_parsed:>19}"
            )
    else:
        print("   (no resource_index rows)")

    print("\nresource_index.vector_status (index lifecycle)")
    print(f"{'Tenant':>8} | {'Vector Status':>16} | {'Count':>7}")
    print("-" * 38)
    for row in sorted(vector_rows, key=lambda item: (item["tenant_id"], item["vector_status"])):
        print(f"{row['tenant_id']:>8} | {row['vector_status']:>16} | {row['count']:>7}")

    print("\n💡 Async = MinerU/external jobs still in flight. Use --format json for automation.")
    print("💡 Use --show-issues --limit 20 to list stuck/failed documents.")


def _print_issue_table(rows: list[ParseIssueRow]) -> None:
    if not rows:
        print("\n✅ No stuck or failed documents found.")
        return

    print(f"\n⚠️  Documents needing attention ({len(rows)} shown):\n")
    print(f"{'ID':>8} | {'Status':>12} | {'Vector':>10} | {'Parse Job':>12} | {'Filename'}")
    print("-" * 90)
    for row in rows:
        job = (row["parse_job_id"] or "-")[:12]
        filename = row["filename"]
        name = filename if len(filename) <= 40 else f"{filename[:37]}..."
        flag = " !" if row["parse_error"] else ""
        print(f"{row['document_id']:>8} | {row['status']:>12} | {row['vector_status']:>10} | {job:>12} | {name}{flag}")


def _merge_status_snapshots(snapshots: list[ParseStatusSnapshot]) -> ParseStatusSnapshot:
    return {
        "documents": [row for snapshot in snapshots for row in snapshot["documents"]],
        "parse_index": [row for snapshot in snapshots for row in snapshot["parse_index"]],
        "vector_index": [row for snapshot in snapshots for row in snapshot["vector_index"]],
    }


async def handle_status(args) -> int:
    tenant_ids = await _resolve_tenant_ids(args.tenant_id)
    snapshots: list[ParseStatusSnapshot] = []
    issue_rows: list[ParseIssueRow] = []
    file_storage = get_file_storage()
    for tenant_id in tenant_ids:
        async with app_db_session() as session:
            processing = DocumentParsePipeline(tenant_id, session, file_storage)
            snapshots.append(await processing.parse_status_snapshot())
            if args.show_issues:
                issue_rows.extend(await processing.list_parse_issues(limit=args.limit))

    payload = _merge_status_snapshots(snapshots)

    if args.format == "json":
        json_payload = {
            "documents_by_status": payload["documents"],
            "parse_index": [
                {
                    **row,
                    "last_parsed_at": row["last_parsed_at"].isoformat() if row["last_parsed_at"] else None,
                }
                for row in payload["parse_index"]
            ],
            "vector_index_by_status": payload["vector_index"],
        }
        print(json.dumps(json_payload, indent=2))
    else:
        _print_status_table(payload, tenant_id=args.tenant_id)

    if args.show_issues:
        _print_issue_table(issue_rows[: args.limit])

    return 0


async def handle_observability(args) -> int:
    return await handle_status(args)


def main() -> int:
    parser = argparse.ArgumentParser(description="Document parse CLI")
    subparsers = parser.add_subparsers(dest="command")

    parse_parser = subparsers.add_parser("parse", help="Parse pending/failed documents")
    parse_parser.add_argument("--tenant-id", type=int)
    parse_parser.add_argument("--document-id", type=int)
    parse_parser.add_argument("--collection-id", type=int)
    parse_parser.add_argument("--failed-only", action="store_true")
    parse_parser.add_argument("--reparse", action="store_true", help="Clear existing parse artifacts first")

    reparse_parser = subparsers.add_parser("reparse", help="Force reparse documents")
    reparse_parser.add_argument("--tenant-id", type=int)
    reparse_parser.add_argument("--document-id", type=int)
    reparse_parser.add_argument("--collection-id", type=int)
    reparse_parser.add_argument("--failed-only", action="store_true")
    reparse_parser.add_argument("--all", action="store_true")

    status_parser = subparsers.add_parser("status", help="Show parse status")
    status_parser.add_argument("--tenant-id", type=int)
    status_parser.add_argument("--format", choices=["table", "json"], default="table")
    status_parser.add_argument(
        "--show-issues",
        action="store_true",
        help="List stuck/failed documents (use --limit to cap rows)",
    )
    status_parser.add_argument("--limit", type=int, default=20, help="Max issue rows when --show-issues (default: 20)")

    observability_parser = subparsers.add_parser("observability", help="Parse observability metrics")
    observability_parser.add_argument("--tenant-id", type=int)
    observability_parser.add_argument("--format", choices=["table", "json"], default="table")
    observability_parser.add_argument("--show-issues", action="store_true")
    observability_parser.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "parse":
            return asyncio.run(handle_parse(args))
        if args.command == "reparse":
            return asyncio.run(handle_reparse(args))
        if args.command == "status":
            return asyncio.run(handle_status(args))
        if args.command == "observability":
            return asyncio.run(handle_observability(args))
        parser.print_help()
        return 1
    except Exception as exc:
        logger.error("document_parse_cli failed: %s", exc, exc_info=True)
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
