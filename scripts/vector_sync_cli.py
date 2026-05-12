#!/usr/bin/env python3
"""Command-line tool for Vector DB sync operations.

Usage:
    # Incremental sync for all resolved tenants (both documents and assets)
    uv run scripts/vector_sync_cli.py sync --mode incremental

    # Incremental sync for specific source
    uv run scripts/vector_sync_cli.py sync --source documents --mode incremental
    uv run scripts/vector_sync_cli.py sync --source assets --mode incremental

    # Full sync for specific tenant (WARNING: drops all vectors)
    uv run scripts/vector_sync_cli.py sync --source documents --mode full --tenant-id 1
    uv run scripts/vector_sync_cli.py sync --source assets --mode full --tenant-id 1

    # Cleanup orphaned vectors for all resolved tenants (dry run)
    uv run scripts/vector_sync_cli.py cleanup --dry-run

    # Cleanup orphaned vectors for all resolved tenants (actual deletion)
    uv run scripts/vector_sync_cli.py cleanup

    # Cleanup for specific tenant
    uv run scripts/vector_sync_cli.py cleanup --tenant-id 1

    # Check sync status
    uv run scripts/vector_sync_cli.py status
    uv run scripts/vector_sync_cli.py status --tenant-id 1

    # On-demand per-tenant observability (no scheduled task)
    uv run scripts/vector_sync_cli.py observability
    uv run scripts/vector_sync_cli.py observability --tenant-id 1 --format json
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import chromadb

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import case, func, select

from apps.config import EnvConfig
from apps.shared.db.models import AssetMetadata, DataSource, Document, ResourceIndex, TaskRun
from apps.shared.db.session import app_db_session
from apps.shared.domain.types import RESOURCE_TYPE_ASSET, RESOURCE_TYPE_DOCUMENT
from apps.shared.tasks.system.handler_result import SystemTaskHandlerResult
from apps.shared.tasks.system.jobs.vector_sync import cleanup_orphaned_vectors, sync_to_vector_db
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


async def _fetch_resource_index_stats(session, tenant_id: int, resource_type: str) -> dict:
    """Aggregate vector sync stats from resource_index for one tenant and type."""
    total, last_sync, error_count, indexed_count = (
        await session.execute(
            select(
                func.count(ResourceIndex.id),
                func.max(ResourceIndex.vector_synced_at),
                func.sum(case((ResourceIndex.vector_sync_error.isnot(None), 1), else_=0)),
                func.sum(case((ResourceIndex.vector_status == "indexed", 1), else_=0)),
            ).where(
                ResourceIndex.tenant_id == tenant_id,
                ResourceIndex.resource_type == resource_type,
            )
        )
    ).one()
    return {
        "item_count": int(total or 0),
        "last_sync": last_sync,
        "error_count": int(error_count or 0),
        "indexed_count": int(indexed_count or 0),
    }


async def _fetch_resource_index_stats_by_tenant(session) -> dict[int, dict[str, dict]]:
    """Aggregate vector sync stats grouped by tenant and resource type."""
    rows = (
        await session.execute(
            select(
                ResourceIndex.tenant_id,
                ResourceIndex.resource_type,
                func.max(ResourceIndex.vector_synced_at).label("last_sync"),
                func.sum(case((ResourceIndex.vector_sync_error.isnot(None), 1), else_=0)).label("error_count"),
                func.count(ResourceIndex.id).label("item_count"),
            )
            .group_by(ResourceIndex.tenant_id, ResourceIndex.resource_type)
            .order_by(ResourceIndex.tenant_id, ResourceIndex.resource_type)
        )
    ).all()

    stats: dict[int, dict[str, dict]] = {}
    for row in rows:
        tenant_stats = stats.setdefault(
            row.tenant_id,
            {
                RESOURCE_TYPE_DOCUMENT: {"last_sync": None, "error_count": 0, "item_count": 0},
                RESOURCE_TYPE_ASSET: {"last_sync": None, "error_count": 0, "item_count": 0},
            },
        )
        tenant_stats[row.resource_type] = {
            "last_sync": row.last_sync,
            "error_count": int(row.error_count or 0),
            "item_count": int(row.item_count or 0),
        }
    return stats


def _result_payload(result: SystemTaskHandlerResult | dict) -> dict:
    """Flatten handler result for CLI aggregation and JSON output."""
    if isinstance(result, SystemTaskHandlerResult):
        return result.to_payload()
    return result if isinstance(result, dict) else {}


def _result_succeeded(result: SystemTaskHandlerResult | dict) -> bool:
    if isinstance(result, SystemTaskHandlerResult):
        return result.outcome in {"success", "partial"}
    return result.get("status") == "completed"


async def _resolve_target_tenant_ids(tenant_id: int | None) -> list[int]:
    """Resolve tenant ids for CLI operations.

    If tenant_id is provided, return it as a singleton list; otherwise resolve
    all active tenants from main DB.
    """
    if tenant_id is not None:
        return [tenant_id]

    async with app_db_session() as session:
        result = await session.execute(
            select(DataSource.tenant_id)
            .distinct()
            .order_by(DataSource.tenant_id)
        )
        return [row[0] for row in result.all()]


async def handle_sync(args):
    """Handle sync command."""
    source = args.source
    mode = args.mode
    tenant_id = args.tenant_id

    # Validate: full sync requires tenant_id
    if mode == "full" and not tenant_id:
        print("❌ Error: Full sync requires --tenant-id (safety measure)")
        print("   Full sync drops all vectors - must specify single tenant")
        return 1

    tenant_ids = await _resolve_target_tenant_ids(tenant_id)

    if not tenant_ids:
        print("\nℹ️ No tenants found for sync")
        return 0

    # Display warning for full sync
    if mode == "full":
        print(f"⚠️  WARNING: Full sync will DROP all {source} vectors for tenant {tenant_id}!")
        print("   This is a destructive operation. Press Ctrl+C to cancel...")
        await asyncio.sleep(3)

    # Execute sync per tenant using strict task_context contract
    print(f"\n🔄 Starting {mode} sync: source={source}, tenant_ids={tenant_ids}")
    details: list[dict] = []
    total_synced = 0
    total_errors = 0
    success_count = 0

    for tid in tenant_ids:
        tenant_result = await sync_to_vector_db(
            source=source,
            mode=mode,
            task_context={"task_id": 0, "tenant_id": tid, "user_id": None, "input_params": {}},
        )
        payload = _result_payload(tenant_result)
        details.append({"tenant_id": tid, "result": payload})
        total_synced += int(payload.get("total_synced", 0) or 0)
        total_errors += int(payload.get("total_failed", 0) or 0)
        if _result_succeeded(tenant_result):
            success_count += 1

    result = {
        "status": "completed" if success_count == len(tenant_ids) else "partial_failed",
        "mode": mode,
        "source": source,
        "total_tenants": len(tenant_ids),
        "successful_operations": success_count,
        "total_synced": total_synced,
        "total_errors": total_errors,
        "details": details,
    }

    # Display results
    print("\n" + "=" * 60)
    if result.get("status") == "completed":
        print("✅ Sync completed successfully")
        print(f"   Mode: {result.get('mode')}")
        print(f"   Source: {result.get('source')}")
        print(f"   Tenants processed: {result.get('total_tenants')}")
        print(f"   Successful operations: {result.get('successful_operations')}")
        print(f"   Total synced: {result.get('total_synced')}")
        print(f"   Total errors: {result.get('total_errors')}")
    else:
        print("❌ Sync failed")

    print("\n📋 Detailed results:")
    print(json.dumps(result, indent=2, default=str))

    return 0 if result.get("status") in {"completed", "partial_failed"} else 1


async def handle_cleanup(args):
    """Handle cleanup command."""
    tenant_id = args.tenant_id
    dry_run = args.dry_run

    tenant_ids = await _resolve_target_tenant_ids(tenant_id)

    if not tenant_ids:
        print("\nℹ️ No tenants found for cleanup")
        return 0

    if dry_run:
        print(f"\n🔍 [DRY RUN] Checking for orphaned vectors: tenant_ids={tenant_ids}")
    else:
        print(f"\n🧹 Cleaning up orphaned vectors: tenant_ids={tenant_ids}")
        print("   This will delete vectors without corresponding DB records")

    details: list[dict] = []
    total_orphaned = 0
    total_cleaned = 0
    success_count = 0

    for tid in tenant_ids:
        tenant_result = await cleanup_orphaned_vectors(
            dry_run=dry_run,
            task_context={"task_id": 0, "tenant_id": tid, "user_id": None, "input_params": {}},
        )
        payload = _result_payload(tenant_result)
        details.append({"tenant_id": tid, "result": payload})
        total_orphaned += int(payload.get("total_orphaned", 0) or 0)
        total_cleaned += int(payload.get("total_cleaned", 0) or 0)
        if _result_succeeded(tenant_result):
            success_count += 1

    result = {
        "status": "completed" if success_count == len(tenant_ids) else "partial_failed",
        "total_tenants": len(tenant_ids),
        "total_orphaned": total_orphaned,
        "total_cleaned": total_cleaned,
        "dry_run": dry_run,
        "details": details,
    }

    # Display results
    print("\n" + "=" * 60)
    if result.get("status") == "completed":
        print("✅ Cleanup completed" + (" [DRY RUN]" if dry_run else ""))
        print(f"   Tenants processed: {result.get('total_tenants')}")
        print(f"   Orphaned vectors found: {result.get('total_orphaned')}")
        print(f"   Vectors cleaned: {result.get('total_cleaned')}")

        if dry_run and result.get("total_orphaned") > 0:
            print("\n💡 Tip: Run without --dry-run to actually delete orphaned vectors")
    else:
        print("❌ Cleanup failed")

    print("\n📋 Detailed results:")
    print(json.dumps(result, indent=2, default=str))

    return 0 if result.get("status") in {"completed", "partial_failed"} else 1


async def handle_status(args):
    """Handle status command."""
    tenant_id = args.tenant_id

    async with app_db_session() as session:
        latest_runs_result = await session.execute(
            select(TaskRun)
            .where(TaskRun.task_type.in_(["vector_sync", "vector_cleanup_orphaned"]))
            .order_by(TaskRun.started_at.desc())
            .limit(10)
        )
        latest_runs = latest_runs_result.scalars().all()

        if latest_runs:
            print("\n🕒 Latest Vector Task Runs:\n")
            print(f"{'ID':>6} | {'Type':>23} | {'Status':>8} | {'Started':>19} | {'Duration(ms)':>11}")
            print("-" * 82)
            for run in latest_runs:
                started = run.started_at.strftime("%Y-%m-%d %H:%M:%S") if run.started_at else "-"
                duration = str(run.duration_ms) if run.duration_ms is not None else "-"
                print(f"{run.id:>6} | {run.task_type:>23} | {run.status:>8} | {started:>19} | {duration:>11}")
        else:
            print("\n🕒 No vector task runs found yet")

        if tenant_id:
            doc_stats = await _fetch_resource_index_stats(session, tenant_id, RESOURCE_TYPE_DOCUMENT)
            asset_stats = await _fetch_resource_index_stats(session, tenant_id, RESOURCE_TYPE_ASSET)

            print(f"\n📊 Sync Status for Tenant {tenant_id}:\n")
            print("📁 DOCUMENTS")
            print(f"   Index Rows:    {doc_stats['item_count']}")
            print(f"   Indexed:       {doc_stats['indexed_count']}")
            print(f"   Last Sync:     {doc_stats['last_sync'] or 'Never'}")
            print(f"   Error Items:   {doc_stats['error_count']}")
            print()
            print("📁 ASSETS")
            print(f"   Index Rows:    {asset_stats['item_count']}")
            print(f"   Indexed:       {asset_stats['indexed_count']}")
            print(f"   Last Sync:     {asset_stats['last_sync'] or 'Never'}")
            print(f"   Error Items:   {asset_stats['error_count']}")
            print()
        else:
            stats_by_tenant = await _fetch_resource_index_stats_by_tenant(session)
            tenant_ids = sorted(stats_by_tenant.keys())

            if not tenant_ids:
                print("\n📊 No resource_index vector sync signals found")
                print("   Run a sync first to populate resource_index.vector_synced_at")
                return 0

            print(f"\n📊 Sync Status Summary ({len(tenant_ids)} tenants):\n")
            print(
                f"{'Tenant':>8} | {'Doc Last Sync':>19} | {'Doc Err':>7} | {'Asset Last Sync':>19} | {'Asset Err':>9}"
            )
            print("-" * 82)

            for tid in tenant_ids:
                doc_info = stats_by_tenant[tid].get(
                    RESOURCE_TYPE_DOCUMENT, {"last_sync": None, "error_count": 0}
                )
                asset_info = stats_by_tenant[tid].get(
                    RESOURCE_TYPE_ASSET, {"last_sync": None, "error_count": 0}
                )
                doc_last_sync = doc_info["last_sync"].strftime("%Y-%m-%d %H:%M:%S") if doc_info["last_sync"] else "-"
                asset_last_sync = (
                    asset_info["last_sync"].strftime("%Y-%m-%d %H:%M:%S") if asset_info["last_sync"] else "-"
                )
                print(
                    f"{tid:>8} | {doc_last_sync:>19} | {doc_info['error_count']:>7} | "
                    f"{asset_last_sync:>19} | {asset_info['error_count']:>9}"
                )

            print("\n💡 Use --tenant-id to see item counts and detailed status for one tenant")

    return 0


def _extract_tenant_id_from_collection_name(collection_name: str, prefix: str) -> int | None:
    """Extract tenant id from a collection name like tenant_123."""
    if not collection_name.startswith(prefix):
        return None
    suffix = collection_name[len(prefix) :]
    return int(suffix) if suffix.isdigit() else None


async def _load_chroma_tenant_stats() -> tuple[dict[int, dict], str | None]:
    """Load per-tenant collection stats from Chroma."""

    def _load_sync() -> dict[int, dict]:
        client = chromadb.HttpClient(**EnvConfig.chroma_http_client_kwargs())
        prefix = EnvConfig.CHROMA_COLLECTION_PREFIX
        results: dict[int, dict] = {}

        for item in client.list_collections():
            name = item.name if hasattr(item, "name") else str(item)
            tenant_id = _extract_tenant_id_from_collection_name(name, prefix)
            if tenant_id is None:
                continue

            collection = client.get_collection(name=name)
            results[tenant_id] = {
                "collection_name": name,
                "chroma_collection_exists": True,
                "chroma_vector_count": int(collection.count()),
            }

        return results

    try:
        stats = await asyncio.to_thread(_load_sync)
        return stats, None
    except Exception as e:
        return {}, str(e)


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


async def handle_observability(args):
    """Show on-demand per-tenant DB and Chroma observability metrics."""
    tenant_id_filter = args.tenant_id
    output_format = args.format

    async with app_db_session() as session:
        docs_by_tenant_result = await session.execute(
            select(
                Document.tenant_id,
                func.count(Document.id).label("doc_count"),
            )
            .group_by(Document.tenant_id)
            .order_by(Document.tenant_id)
        )

        docs_by_tenant = {
            row.tenant_id: {"doc_count": int(row.doc_count or 0)}
            for row in docs_by_tenant_result
        }

        assets_by_tenant_result = await session.execute(
            select(
                DataSource.tenant_id,
                func.count(AssetMetadata.id).label("asset_count"),
            )
            .join(DataSource, AssetMetadata.data_source_id == DataSource.id)
            .group_by(DataSource.tenant_id)
            .order_by(DataSource.tenant_id)
        )

        assets_by_tenant = {
            row.tenant_id: {"asset_count": int(row.asset_count or 0)}
            for row in assets_by_tenant_result
        }

        index_stats_by_tenant = await _fetch_resource_index_stats_by_tenant(session)
        for tid, type_stats in index_stats_by_tenant.items():
            doc_index = type_stats.get(RESOURCE_TYPE_DOCUMENT, {})
            asset_index = type_stats.get(RESOURCE_TYPE_ASSET, {})
            docs_by_tenant.setdefault(tid, {})
            assets_by_tenant.setdefault(tid, {})
            docs_by_tenant[tid].update(
                {
                    "doc_error_count": doc_index.get("error_count", 0),
                    "doc_last_sync": doc_index.get("last_sync"),
                    "doc_ref_count": doc_index.get("item_count", 0),
                }
            )
            assets_by_tenant[tid].update(
                {
                    "asset_error_count": asset_index.get("error_count", 0),
                    "asset_last_sync": asset_index.get("last_sync"),
                    "asset_ref_count": asset_index.get("item_count", 0),
                }
            )

    chroma_by_tenant, chroma_error = await _load_chroma_tenant_stats()

    tenant_ids = sorted(set(docs_by_tenant.keys()) | set(assets_by_tenant.keys()) | set(chroma_by_tenant.keys()))
    if tenant_id_filter is not None:
        tenant_ids = [tid for tid in tenant_ids if tid == tenant_id_filter]

    if not tenant_ids and tenant_id_filter is not None:
        tenant_ids = [tenant_id_filter]

    rows: list[dict] = []

    for tid in tenant_ids:
        doc_info = docs_by_tenant.get(tid, {})
        asset_info = assets_by_tenant.get(tid, {})
        chroma_info = chroma_by_tenant.get(tid, {})

        doc_last_sync = _to_utc(doc_info.get("doc_last_sync"))
        asset_last_sync = _to_utc(asset_info.get("asset_last_sync"))
        db_vector_refs_count = int(doc_info.get("doc_ref_count", 0)) + int(asset_info.get("asset_ref_count", 0))
        chroma_vector_count = int(chroma_info.get("chroma_vector_count", 0))

        rows.append(
            {
                "tenant_id": tid,
                "doc_count": int(doc_info.get("doc_count", 0)),
                "asset_count": int(asset_info.get("asset_count", 0)),
                "doc_error_count": int(doc_info.get("doc_error_count", 0)),
                "asset_error_count": int(asset_info.get("asset_error_count", 0)),
                "doc_last_sync": doc_last_sync.isoformat() if doc_last_sync else None,
                "asset_last_sync": asset_last_sync.isoformat() if asset_last_sync else None,
                "db_vector_refs_count": db_vector_refs_count,
                "collection_name": chroma_info.get("collection_name"),
                "chroma_collection_exists": bool(chroma_info.get("chroma_collection_exists", False)),
                "chroma_vector_count": chroma_vector_count,
            }
        )

    if output_format == "json":
        print(
            json.dumps(
                {
                    "chroma_error": chroma_error,
                    "tenant_count": len(rows),
                    "rows": rows,
                },
                indent=2,
                default=str,
            )
        )
        return 0

    print("\n📈 Vector Observability (On-demand)\n")
    if chroma_error:
        print(f"⚠️  Chroma stats unavailable: {chroma_error}")
        print("   DB metrics are still shown below.\n")

    if not rows:
        print("No tenant observability rows found")
        return 0

    print(
        f"{'Tenant':>8} | {'Docs':>6} | {'Assets':>6} | {'DocErr':>6} | {'AstErr':>6} | "
        f"{'DBRefs':>6} | {'ChromaVec':>9} | {'Collection':<24}"
    )
    print("-" * 96)

    for row in rows:
        collection_name = (row["collection_name"] or "-")[:24]
        print(
            f"{row['tenant_id']:>8} | {row['doc_count']:>6} | {row['asset_count']:>6} | "
            f"{row['doc_error_count']:>6} | {row['asset_error_count']:>6} | "
            f"{row['db_vector_refs_count']:>6} | {row['chroma_vector_count']:>9} | "
            f"{collection_name:<24}"
        )

    print("\n💡 Use '--format json' for machine-readable output")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Vector DB sync operations CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Sync documents or assets to Vector DB")
    sync_parser.add_argument(
        "--source",
        choices=["documents", "assets", "all"],
        default="all",
        help="Data source to sync (default: all)",
    )
    sync_parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="Sync mode: incremental (repair) or full (rebuild, requires --tenant-id)",
    )
    sync_parser.add_argument(
        "--tenant-id",
        type=int,
        help="Sync specific tenant only (required for full mode)",
    )

    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Cleanup orphaned vectors")
    cleanup_parser.add_argument(
        "--tenant-id",
        type=int,
        help="Cleanup specific tenant only",
    )
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only check for orphans without deleting (safe mode)",
    )

    # Status command
    status_parser = subparsers.add_parser("status", help="Show sync status")
    status_parser.add_argument(
        "--tenant-id",
        type=int,
        help="Show status for specific tenant",
    )
    status_parser.add_argument(
        "tenant_id_positional",
        nargs="?",
        type=int,
        help="Optional tenant id shorthand (equivalent to --tenant-id)",
    )

    # Observability command (on-demand only; no scheduler changes)
    observability_parser = subparsers.add_parser(
        "observability",
        help="Show per-tenant DB and Chroma observability metrics",
    )
    observability_parser.add_argument(
        "--tenant-id",
        type=int,
        help="Show observability for specific tenant",
    )
    observability_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    args = parser.parse_args()

    if args.command == "status":
        positional_tid = getattr(args, "tenant_id_positional", None)
        if args.tenant_id is None and positional_tid is not None:
            args.tenant_id = positional_tid
        elif args.tenant_id is not None and positional_tid is not None and args.tenant_id != positional_tid:
            parser.error("Conflicting tenant values: use either --tenant-id or positional tenant id, not both")

    if not args.command:
        parser.print_help()
        return 1

    # Run command
    try:
        if args.command == "sync":
            exit_code = asyncio.run(handle_sync(args))
        elif args.command == "cleanup":
            exit_code = asyncio.run(handle_cleanup(args))
        elif args.command == "status":
            exit_code = asyncio.run(handle_status(args))
        elif args.command == "observability":
            exit_code = asyncio.run(handle_observability(args))
        else:
            parser.print_help()
            exit_code = 1

        return exit_code

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
