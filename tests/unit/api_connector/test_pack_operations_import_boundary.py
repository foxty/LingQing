"""Pack operation helpers must not import ORM models directly."""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACK_OPS = _REPO_ROOT / "apps/shared/external_systems/api_connector/pack_operations.py"


def test_pack_operations_does_not_import_db_models():
    tree = ast.parse(_PACK_OPS.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                mods.add(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    assert "apps.shared.db.models" not in mods