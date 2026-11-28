"""Data plane must not depend on pack catalog or control-plane orchestration."""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA_PLANE_MODULES = (
    _REPO_ROOT / "apps/shared/external_systems/api_connector/execution.py",
    _REPO_ROOT / "apps/shared/external_systems/api_connector/runtime.py",
    _REPO_ROOT / "apps/shared/external_systems/api_connector/operation_catalog.py",
)
_FORBIDDEN_PREFIXES = (
    "apps.shared.external_systems.packs",
    "apps.shared.external_systems.api_connector.schema_parser",
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


def test_data_plane_modules_do_not_import_packs():
    violations: list[str] = []
    for path in _DATA_PLANE_MODULES:
        mods = _imported_modules(path.read_text(encoding="utf-8"))
        for forbidden in _FORBIDDEN_PREFIXES:
            hits = sorted(m for m in mods if m == forbidden or m.startswith(f"{forbidden}."))
            for hit in hits:
                violations.append(f"{path.relative_to(_REPO_ROOT)}: {hit}")
    assert not violations, (
        "Data plane modules must not import integration packs (control plane). Found: " + ", ".join(violations)
    )