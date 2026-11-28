"""Pack catalog lib must not depend on connector application services."""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PACK_LIB_MODULES = (
    _REPO_ROOT / "apps/shared/external_systems/packs/loader.py",
    _REPO_ROOT / "apps/shared/external_systems/packs/versioning.py",
    _REPO_ROOT / "apps/shared/external_systems/packs/schemas.py",
    _REPO_ROOT / "apps/shared/external_systems/packs/__init__.py",
    _REPO_ROOT / "apps/shared/external_systems/packs/catalog.py",
)
_FORBIDDEN = (
    "apps.shared.external_systems.api_connector.service",
    "apps.shared.db.models",
)


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                mods.add(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def test_pack_lib_modules_do_not_import_connector_control_plane():
    violations: list[str] = []
    for path in _PACK_LIB_MODULES:
        if not path.exists():
            continue
        mods = _imported_modules(path.read_text(encoding="utf-8"))
        for forbidden in _FORBIDDEN:
            hits = sorted(m for m in mods if m == forbidden or m.startswith(f"{forbidden}."))
            for hit in hits:
                violations.append(f"{path.relative_to(_REPO_ROOT)}: {hit}")
    assert not violations, "Pack lib must not import connector services or ORM. Found: " + ", ".join(violations)