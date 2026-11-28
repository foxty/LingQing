"""Control vs data plane import boundaries for API connectors."""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                mods.add(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def test_control_plane_service_does_not_import_execution():
    path = _REPO_ROOT / "apps/shared/external_systems/api_connector/service.py"
    mods = _imported_modules(path)
    violations = sorted(m for m in mods if m == "apps.shared.external_systems.api_connector.execution" or m.endswith(".execution"))
    assert not violations, f"control service must not import execution: {violations}"


def test_data_plane_execution_does_not_import_schema_parser():
    path = _REPO_ROOT / "apps/shared/external_systems/api_connector/execution.py"
    mods = _imported_modules(path)
    violations = sorted(m for m in mods if "schema_parser" in m)
    assert not violations, f"execution must not import schema_parser: {violations}"


def test_data_plane_runtime_does_not_import_schema_parser():
    path = _REPO_ROOT / "apps/shared/external_systems/api_connector/runtime.py"
    mods = _imported_modules(path)
    violations = sorted(m for m in mods if "schema_parser" in m)
    assert not violations, f"runtime must not import schema_parser: {violations}"