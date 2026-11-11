"""Smoke tests for release body assembly (deploy script)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ASSEMBLE = PROJECT_ROOT / "deploy/scripts/assemble-github-release-body.sh"
NOTES_DIR = PROJECT_ROOT / "docs/release-notes"


def test_assemble_with_product_notes_includes_deploy_footer(tmp_path: Path) -> None:
    version = "v9.9.9-test"
    notes = NOTES_DIR / f"{version}.md"
    notes.write_text(f"# LingQing {version}\n\n## Highlights\n\n- test\n", encoding="utf-8")
    out = tmp_path / "body.md"
    try:
        subprocess.run(
            [
                "bash",
                str(ASSEMBLE),
                version,
                str(out),
                "org/LingQing",
                "ghcr.io/org/lingqing",
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        body = out.read_text(encoding="utf-8")
        assert "## Highlights" in body
        assert "## Deploy on your VM" in body
        assert body.index("## Highlights") < body.index("## Deploy on your VM")
    finally:
        notes.unlink(missing_ok=True)


def test_strict_fails_when_notes_missing(tmp_path: Path) -> None:
    version = "v0.0.0-missing"
    out = tmp_path / "body.md"
    result = subprocess.run(
        [
            "bash",
            str(ASSEMBLE),
            version,
            str(out),
            "org/LingQing",
            "ghcr.io/org/lingqing",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "STRICT_RELEASE_NOTES": "1"},
    )
    assert result.returncode != 0
    assert "requires" in result.stderr.lower() or "missing" in result.stderr.lower()


def test_strict_fails_when_version_not_in_notes_header(tmp_path: Path) -> None:
    version = "v0.0.0-mismatch"
    notes = NOTES_DIR / f"{version}.md"
    notes.write_text("# LingQing v9.9.9-wrong\n\n## Highlights\n\n- oops\n", encoding="utf-8")
    out = tmp_path / "body.md"
    try:
        result = subprocess.run(
            [
                "bash",
                str(ASSEMBLE),
                version,
                str(out),
                "org/LingQing",
                "ghcr.io/org/lingqing",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "STRICT_RELEASE_NOTES": "1"},
        )
        assert result.returncode != 0
        assert "v0.0.0-mismatch" in result.stderr or "do not reference" in result.stderr
    finally:
        notes.unlink(missing_ok=True)


def test_assemble_without_notes_is_deploy_only(tmp_path: Path) -> None:
    version = "v0.0.0-missing"
    out = tmp_path / "body.md"
    subprocess.run(
        [
            "bash",
            str(ASSEMBLE),
            version,
            str(out),
            "org/LingQing",
            "ghcr.io/org/lingqing",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    body = out.read_text(encoding="utf-8")
    assert "## Deploy on your VM" in body
    assert "ghcr.io/org/lingqing/backend-app" in body
    assert "## Highlights" not in body
