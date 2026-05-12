#!/usr/bin/env python
"""RBAC Endpoint Scanner: Identify unprotected endpoints and generate permission matrix.

Usage:
    uv run python scripts/rbac_scanner.py              # Show unprotected endpoints
    uv run python scripts/rbac_scanner.py --report     # Generate CSV report
    uv run python scripts/rbac_scanner.py --check      # Exit with error if issues found
"""

import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from apps.shared.authz.rbac import DEFAULT_ROLE_PERMISSIONS  # noqa: E402
from apps.shared.authz.ta_permissions import TenantAppPermissions  # noqa: E402

_CONSTANT_TO_VALUE: dict[str, str] = {
    attr: getattr(TenantAppPermissions, attr)
    for attr in dir(TenantAppPermissions)
    if not attr.startswith("_") and isinstance(getattr(TenantAppPermissions, attr), str)
}


@dataclass
class Endpoint:
    """Represents a detected API endpoint."""

    file: str
    function_name: str
    http_method: str
    path: str
    has_permission_check: bool
    permission_required: str | None = None

    def is_protected(self) -> bool:
        """Check if endpoint is properly protected."""
        # Public endpoints that don't need protection
        PUBLIC_ENDPOINTS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}

        if self.path in PUBLIC_ENDPOINTS:
            return True

        return self.has_permission_check


def scan_routers() -> list[Endpoint]:
    """Scan all router files and extract endpoint information."""
    router_dir = project_root / "apps" / "tenant_app_service" / "routers"
    endpoints: list[Endpoint] = []

    # Pattern to match @router.{method}(...) decorators
    decorator_pattern = r"@router\.(get|post|put|patch|delete)\([\"']([^\"']+)[\"']"
    # Pattern to find function definitions following decorators
    function_pattern = r"async def (\w+)\("
    # Pattern to find require_permission in dependencies
    permission_pattern = r"require_permission\(([^)]+)\)"

    for router_file in sorted(router_dir.glob("*.py")):
        if router_file.name.startswith("_"):
            continue

        content = router_file.read_text()
        lines = content.split("\n")

        # Find all decorator positions
        for i, line in enumerate(lines):
            decorator_match = re.search(decorator_pattern, line)
            if not decorator_match:
                continue

            method = decorator_match.group(1).upper()
            path = decorator_match.group(2)

            # Find function name (should be within next few lines)
            func_name = None
            has_permission = False
            permission_required = None

            for j in range(i, min(i + 20, len(lines))):
                # Check for permission check in this and surrounding lines
                if "require_permission" in lines[j]:
                    has_permission = True
                    # Try to extract permission name
                    perm_match = re.search(permission_pattern, lines[j])
                    if perm_match:
                        permission_required = perm_match.group(1).strip()

                # Find function definition
                func_match = re.search(function_pattern, lines[j])
                if func_match:
                    func_name = func_match.group(1)
                    # Don't break yet - continue searching for require_permission in the parameters
                    # which may span multiple lines

            endpoint = Endpoint(
                file=router_file.name,
                function_name=func_name or f"unknown_{len(endpoints)}",
                http_method=method,
                path=path,
                has_permission_check=has_permission,
                permission_required=permission_required,
            )
            endpoints.append(endpoint)

    return endpoints


def print_summary(endpoints: list[Endpoint]):
    """Print a summary of endpoint protection status."""
    total = len(endpoints)
    protected = sum(1 for e in endpoints if e.is_protected())
    unprotected = total - protected

    print("\n" + "=" * 80)
    print("RBAC ENDPOINT SCANNER REPORT")
    print("=" * 80)
    print(f"\nTotal endpoints scanned: {total}")
    print(f"Protected endpoints:    {protected} ({protected / total * 100:.1f}%)")
    print(f"Unprotected endpoints:  {unprotected} ({unprotected / total * 100:.1f}%)")

    if unprotected > 0:
        print("\n⚠️  UNPROTECTED ENDPOINTS:")
        print("-" * 80)
        for endpoint in endpoints:
            if not endpoint.is_protected():
                print(f"  {endpoint.http_method:6} {endpoint.path:40} ({endpoint.file}::{endpoint.function_name})")

    # Print endpoints with permission checks
    print("\n✓ PROTECTED ENDPOINTS (sample):")
    print("-" * 80)
    protected_endpoints = [e for e in endpoints if e.is_protected()][:10]
    for endpoint in protected_endpoints:
        perm_str = endpoint.permission_required or "?"
        print(f"  {endpoint.http_method:6} {endpoint.path:40} requires: {perm_str}")

    if len(protected_endpoints) < len([e for e in endpoints if e.is_protected()]):
        print(f"  ... and {len([e for e in endpoints if e.is_protected()]) - 10} more")

    print("\n" + "=" * 80)


def generate_permission_matrix(endpoints: list[Endpoint]):
    """Generate a CSV permission matrix."""
    import csv

    output_file = project_root / "rbac_permission_matrix.csv"

    rows = []
    for endpoint in endpoints:
        if not endpoint.is_protected():
            continue

        # Determine which roles have this permission
        allowed_roles = []
        if endpoint.permission_required:
            # Extract permission names (e.g., "Permissions.DATA_SOURCES_WRITE")
            perms = [p.strip() for p in endpoint.permission_required.split(",")]
            required_perms = []

            for perm in perms:
                if "Permissions." in perm:
                    perm_name = perm.split("Permissions.")[-1]
                    perm_value = _CONSTANT_TO_VALUE.get(perm_name, perm_name)
                    required_perms.append(perm_value)
                else:
                    required_perms.append(perm.strip("[]\"'"))

            for role, role_perms in DEFAULT_ROLE_PERMISSIONS.items():
                has_admin = "tenant.admin" in role_perms
                if has_admin or any(perm in role_perms for perm in required_perms):
                    allowed_roles.append(role)
        else:
            allowed_roles = ["public"]

        rows.append(
            {
                "method": endpoint.http_method,
                "path": endpoint.path,
                "file": endpoint.file,
                "function": endpoint.function_name,
                "permission": endpoint.permission_required or "N/A",
                "allowed_roles": ",".join(allowed_roles),
            }
        )

    # Write CSV
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["method", "path", "file", "function", "permission", "allowed_roles"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n📊 Permission matrix written to: {output_file.relative_to(project_root)}")
    return output_file


def check_consistency(endpoints: list[Endpoint]) -> bool:
    """Check for consistency issues in RBAC setup.

    Returns:
        True if all checks pass, False if issues found.
    """
    issues = []

    # Check 1: No endpoints should be unprotected (except public ones)
    public_paths = {"/", "/health", "/docs", "/openapi.json", "/redoc"}
    unprotected = [e for e in endpoints if not e.is_protected() and e.path not in public_paths]

    if unprotected:
        issues.append(f"Found {len(unprotected)} unprotected endpoints:")
        for e in unprotected:
            issues.append(f"  - {e.http_method} {e.path}")

    # Check 2: Verify common permissions are defined
    required_perms = {
        "data_sources.read",
        "data_sources.write",
        "dashboards.write",
        "chat.access",
        "documents.read",
        "documents.write",
        "artifacts.manage",
        "reports.write",
        "scheduled_tasks.write",
    }

    all_perms = set()
    for role_perms in DEFAULT_ROLE_PERMISSIONS.values():
        all_perms.update(role_perms)

    missing_perms = required_perms - all_perms
    if missing_perms:
        issues.append(f"Missing required permissions: {missing_perms}")

    # Check 3: Verify role hierarchy (tenant.admin superuser bypass means
    # admin effectively has all permissions, so we check viewer ⊂ member
    # and member ⊂ admin's explicit set)
    viewer_perms = DEFAULT_ROLE_PERMISSIONS.get("viewer", set())
    member_perms = DEFAULT_ROLE_PERMISSIONS.get("member", set())
    admin_perms = DEFAULT_ROLE_PERMISSIONS.get("admin", set())

    if not viewer_perms.issubset(member_perms):
        diff = viewer_perms - member_perms
        issues.append(f"Viewer permissions should be subset of member permissions (extra: {diff})")

    if not member_perms.issubset(admin_perms):
        diff = member_perms - admin_perms
        issues.append(f"Member permissions should be subset of admin permissions (extra: {diff})")

    if issues:
        print("\n❌ CONSISTENCY ISSUES FOUND:\n")
        for issue in issues:
            print(f"  {issue}")
        return False

    print("\n✅ All RBAC consistency checks passed!")
    return True


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Scan routers for RBAC protection")
    parser.add_argument("--report", action="store_true", help="Generate CSV permission matrix")
    parser.add_argument("--check", action="store_true", help="Check for consistency issues")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    print("🔍 Scanning routers for endpoints...\n")
    endpoints = scan_routers()

    if args.json:
        import json

        data = [asdict(e) for e in endpoints]
        print(json.dumps(data, indent=2))
    else:
        print_summary(endpoints)

    if args.report:
        generate_permission_matrix(endpoints)

    if args.check:
        success = check_consistency(endpoints)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
