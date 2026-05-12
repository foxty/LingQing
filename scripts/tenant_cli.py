#!/usr/bin/env python3
"""Tenant manager CLI tool.

This tool provides commands to manage tenants:

Commands:
    create            Create a new tenant with default agent and admin user
    list              List all tenants
    show              Show tenant info with user count
    seed-tags         Seed default tags for a tenant

Usage:
    python tenant_cli.py create --name "My Company" --slug "my-company"
    python tenant_cli.py list
    python tenant_cli.py show --slug demo
"""
# ruff: noqa: T201

import argparse
import asyncio
import os
import sys
import traceback
from typing import Any

# Add project root to path FIRST
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from apps.shared.core.tag_seed import seed_default_tags  # noqa: E402
from apps.shared.data_source import (  # noqa: E402
    AssetMetadataRepository,
    DataSourceRepository,
    DataSourceService,
)
from apps.shared.data_source.schemas import DataSourceCreate  # noqa: E402
from apps.shared.db.session import app_db_session  # noqa: E402
from apps.tenant_app_service.tenant import (  # noqa: E402
    PostgreSQLProvisioningExecutor,
    TenantProvisioningService,
    TenantUserManagementService,
)

DEFAULT_TENANT_CONFIG: dict[str, Any] = {"max_concurrent_requests": 10}


# ============================================================================
# Functions
# ============================================================================


async def create_tenant_with_defaults(
    tenant_name: str,
    tenant_slug: str,
    description: str,
    db_session,
) -> int:
    """Create a tenant with default agent and admin user.

    Args:
        tenant_name: Tenant display name (can be Chinese)
        tenant_slug: Tenant URL identifier (English, lowercase)
        description: Tenant description
        db_session: Database session

    Returns:
        Database ID of created tenant
    """
    # Initialize provisioning service
    postgres_executor = PostgreSQLProvisioningExecutor()
    provisioning_service = TenantProvisioningService(db_session, postgres_executor)

    # Check if tenant slug already exists
    existing_tenant = await provisioning_service.get_tenant_by_slug(tenant_slug)
    if existing_tenant:
        print(f"⏭️  Tenant with slug '{tenant_slug}' already exists (ID: {existing_tenant['id']}), skipping")
        return existing_tenant["id"]

    print(f"📦 Creating tenant: {tenant_name} ({tenant_slug})")

    # Create tenant
    tenant_result = await provisioning_service.provision_tenant(
        name=tenant_name,
        slug=tenant_slug,
        description=description,
        config=DEFAULT_TENANT_CONFIG,
    )
    tenant_id = tenant_result["id"]
    print(f"   ✓ Tenant created (ID: {tenant_id})")

    user_service = TenantUserManagementService(tenant_id=tenant_id, db=db_session)

    # Create admin user (username: admin, password: admin)
    print("   👤 Creating admin user")
    admin_user = await user_service.create_user(username="admin", password="admin", role="admin")
    print("      ✓ Admin user created (username: admin, password: admin)")

    # Provision analytics database and store connection info in DataSource
    print("\n   💾 Provisioning analytics database")
    db_info = await provisioning_service.provision_analytics_db(tenant_id)
    print(f"      ✓ Analytics database created: {db_info.database}")

    # Store analytics DB connection info in DataSource
    print("   📝 Registering analytics database as DataSource")
    data_source_data = DataSourceCreate(
        name="Analytics DB (PostgreSQL)",
        type="postgres",
        managed=True,
        description="Platform-managed PostgreSQL database for analytics and reporting",
        config=db_info.to_dict(),  # Store connection details
    )

    data_source_service = DataSourceService(
        tenant_id=tenant_id,
        data_source_repo=DataSourceRepository(db_session),
        asset_repo=AssetMetadataRepository(db_session),
    )
    await data_source_service.create_data_source(data_source_data, owner_id=admin_user.id)
    print("      ✓ Analytics database registered as DataSource")

    return tenant_id


async def create_tenant(tenant_name: str, tenant_slug: str, description: str = ""):
    """Create a tenant with default agent and admin user.

    Args:
        tenant_name: Tenant display name
        tenant_slug: Tenant URL identifier
        description: Tenant description (optional)
    """
    print("\n" + "=" * 70)
    print("🚀 Creating Tenant")
    print("=" * 70 + "\n")

    async with app_db_session() as session:
        try:
            await create_tenant_with_defaults(tenant_name, tenant_slug, description, session)

            # Commit all changes
            await session.commit()
            print("\n" + "=" * 70)
            print("✅ Tenant creation completed successfully!")
            print("=" * 70 + "\n")

            print("📝 Default Admin Credentials:")
            print(f"   Tenant: {tenant_name} ({tenant_slug})")
            print(f"   Username: admin@{tenant_slug}")
            print("   Password: admin")
            print("")
            print("⚠️  Security Notes:")
            print("   • Password is hashed in database using bcrypt")
            print("   • Please change password after first login")
            print("")

        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error creating tenant: {e}", file=sys.stderr)
            traceback.print_exc()
            raise


async def list_tenants():
    """List all tenants."""
    print("\n" + "=" * 70)
    print("📋 Tenants")
    print("=" * 70 + "\n")

    async with app_db_session() as session:
        postgres_executor = PostgreSQLProvisioningExecutor()
        provisioning_service = TenantProvisioningService(session, postgres_executor)

        tenants = await provisioning_service.get_all_tenants()

        if not tenants:
            print("No tenants found.")
            return

        print(f"{'ID':<5} {'Name':<20} {'Slug':<20} {'Status':<10}")
        print("-" * 70)
        for tenant in tenants:
            print(f"{tenant['id']:<5} {tenant['name']:<20} {tenant['slug'] or 'N/A':<20} {tenant['status']:<10}")

        print(f"\nTotal: {len(tenants)} tenant(s)")


async def show_tenant(tenant_slug: str):
    """Show tenant information with user count."""
    print("\n" + "=" * 70)
    print(f"📦 Tenant Details: {tenant_slug}")
    print("=" * 70 + "\n")

    async with app_db_session() as session:
        postgres_executor = PostgreSQLProvisioningExecutor()
        provisioning_service = TenantProvisioningService(session, postgres_executor)

        tenant = await provisioning_service.get_tenant_with_user_count(tenant_slug)
        if not tenant:
            print(f"❌ Tenant '{tenant_slug}' not found")
            sys.exit(1)

        print(f"ID: {tenant['id']}")
        print(f"Name: {tenant['name']}")
        print(f"Slug: {tenant['slug']}")
        print(f"Description: {tenant['description'] or 'N/A'}")
        print(f"Status: {tenant['status']}")
        print(f"Users: {tenant['user_count']}")


async def seed_tags_for_tenant(tenant_slug: str) -> None:
    """Seed default tags for a tenant."""
    print("\n" + "=" * 70)
    print(f"🏷️  Seeding tags for tenant: {tenant_slug}")
    print("=" * 70 + "\n")

    async with app_db_session() as session:
        try:
            postgres_executor = PostgreSQLProvisioningExecutor()
            provisioning_service = TenantProvisioningService(session, postgres_executor)

            tenant = await provisioning_service.get_tenant_by_slug(tenant_slug)
            if not tenant:
                print(f"❌ Error: Tenant '{tenant_slug}' not found", file=sys.stderr)
                sys.exit(1)

            await seed_default_tags(session, tenant["id"])
            await session.commit()

            print("✅ Tag seed completed")
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error: {e}", file=sys.stderr)
            traceback.print_exc()
            raise


def validate_slug(slug: str) -> bool:
    """Validate tenant slug format.

    Args:
        slug: Tenant slug to validate

    Returns:
        True if valid, False otherwise
    """
    import re

    # Allow lowercase letters, numbers, and hyphens
    # Must start with a letter, end with letter or number
    pattern = r"^[a-z][a-z0-9-]*[a-z0-9]$"
    return bool(re.match(pattern, slug)) and len(slug) >= 2


def main():
    """Run the tenant manager CLI tool."""
    parser = argparse.ArgumentParser(
        description="Tenant manager CLI tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a new tenant
  python tenant_cli.py create --name "Demo" --slug "demo"
  python tenant_cli.py create --name "My Company" --slug "my-company" --description "Enterprise"

  # List all tenants
  python tenant_cli.py list

  # Show tenant details (with user count)
  python tenant_cli.py show --slug demo

Slug Requirements:
  - Lowercase letters, numbers, and hyphens only
  - Must start with a letter
  - Must end with a letter or number
  - At least 2 characters long
  - Examples: demo, my-company, acme-001

""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new tenant")
    create_parser.add_argument("--name", type=str, required=True, help="Tenant display name (can be Chinese)")
    create_parser.add_argument("--slug", type=str, required=True, help="Tenant URL identifier (e.g., 'demo')")
    create_parser.add_argument("--description", type=str, default="", help="Tenant description (optional)")

    # List command
    subparsers.add_parser("list", help="List all tenants")

    # Show command
    show_parser = subparsers.add_parser("show", help="Show tenant details")
    show_parser.add_argument("--slug", type=str, required=True, help="Tenant slug")

    # Seed tags command
    seed_tags_parser = subparsers.add_parser("seed-tags", help="Seed default tags for a tenant")
    seed_tags_parser.add_argument("--tenant", type=str, required=True, help="Tenant slug")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    if args.command == "create":
        # Validate slug
        if not validate_slug(args.slug):
            print("❌ Error: Invalid tenant slug format", file=sys.stderr)
            print("   Slug must:", file=sys.stderr)
            print("   • Use lowercase letters, numbers, and hyphens only", file=sys.stderr)
            print("   • Start with a letter", file=sys.stderr)
            print("   • End with a letter or number", file=sys.stderr)
            print("   • Be at least 2 characters long", file=sys.stderr)
            sys.exit(1)

        asyncio.run(create_tenant(args.name, args.slug, args.description))

    elif args.command == "list":
        asyncio.run(list_tenants())

    elif args.command == "show":
        asyncio.run(show_tenant(args.slug))

    elif args.command == "seed-tags":
        asyncio.run(seed_tags_for_tenant(args.tenant))


if __name__ == "__main__":
    main()
