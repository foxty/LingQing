"""Architecture regression guard.

Locks the module boundary: the native auth service must NOT depend on the SSO
module. `force_sso` is a tenant property, so native auth reads it off the tenant
row with no SSO import. If this test fails, an SSO import leaked back into
`auth.service` — move the logic to a shared/inner layer instead.
"""

import ast
from pathlib import Path


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                mods.add(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def test_auth_service_does_not_import_sso():
    service_path = Path(__file__).resolve().parents[3] / "apps" / "tenant_app_service" / "auth" / "service.py"
    source = service_path.read_text(encoding="utf-8")
    mods = _imported_modules(source)
    sso_imports = {m for m in mods if "sso" in m.split(".")}
    assert not sso_imports, (
        f"auth.service must not import the sso module (found: {sorted(sso_imports)}). "
        "force_sso is a tenant property; read it off the tenant row instead."
    )


def test_auth_service_uses_native_login_allowed_from_auth_domain():
    """The force-SSO gate must come from auth.domain, not sso.domain."""
    service_path = Path(__file__).resolve().parents[3] / "apps" / "tenant_app_service" / "auth" / "service.py"
    source = service_path.read_text(encoding="utf-8")
    assert "native_login_allowed" in source
    assert "from apps.tenant_app_service.auth.domain" in source
    assert "sso.domain" not in source
