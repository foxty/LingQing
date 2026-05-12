"""Skill ZIP validation logic.

Validates uploaded skill ZIP files against business rules:
- Size limits
- Required SKILL.md file
- Valid YAML frontmatter (name, description)
- Skill name format constraints

Lives in the service layer because it enforces business rules for
skill uploads, not data access.
"""

from __future__ import annotations

import os
import re
import tempfile
import zipfile
from typing import BinaryIO

import yaml

from apps.shared.core.exceptions import ValidationError
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

SKILL_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
MAX_SKILL_SIZE_BYTES = 10 * 1024 * 1024


class SkillZipValidator:
    """Validates uploaded skill ZIP files.

    Enforces business rules for skill uploads (size, structure, naming).
    """

    def validate_zip(self, zip_file: BinaryIO, expected_name: str | None = None) -> dict:
        zip_file.seek(0)
        raw = zip_file.read()
        if len(raw) > MAX_SKILL_SIZE_BYTES:
            raise ValidationError(f"ZIP size exceeds 10MB limit ({len(raw)} bytes)")

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = os.path.join(tmpdir, "upload.zip")
                with open(zip_path, "wb") as f:
                    f.write(raw)

                with zipfile.ZipFile(zip_path, "r") as zf:
                    members = zf.namelist()
                    skill_md_path = self._find_skill_md(members)
                    if not skill_md_path:
                        raise ValidationError("ZIP must contain a SKILL.md file")

                    zf.extractall(tmpdir)

                skill_dir = os.path.dirname(os.path.join(tmpdir, skill_md_path))
                skill_md_full = os.path.join(tmpdir, skill_md_path)
                frontmatter = self._validate_skill_md(skill_md_full)

                name = frontmatter.get("name", "")
                if not name:
                    raise ValidationError("SKILL.md frontmatter must define 'name'")

                if expected_name and name != expected_name:
                    raise ValidationError(
                        f"Skill name in SKILL.md ('{name}') does not match expected name ('{expected_name}')"
                    )

                description = frontmatter.get("description", "")
                if not description:
                    raise ValidationError("SKILL.md frontmatter must define 'description'")

                has_requirements = "requirements.txt" in [os.path.basename(m) for m in members]

                return {
                    "name": name,
                    "description": description,
                    "has_requirements": has_requirements,
                    "extract_dir": skill_dir,
                }
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Failed to process ZIP file: {e}") from e

    def _find_skill_md(self, members: list[str]) -> str | None:
        for member in members:
            if member.endswith("SKILL.md") and not member.startswith("__") and not member.startswith("."):
                return member
        return None

    def _validate_skill_md(self, path: str) -> dict:
        with open(path, encoding="utf-8") as f:
            content = f.read()

        lines = content.splitlines()
        start = 0
        while start < len(lines) and not lines[start].strip():
            start += 1

        if start >= len(lines) or lines[start].strip() != "---":
            raise ValidationError("SKILL.md must start with YAML frontmatter '---'")

        end = None
        for i in range(start + 1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break

        if end is None:
            raise ValidationError("SKILL.md has unclosed YAML frontmatter")

        frontmatter_text = "\n".join(lines[start + 1 : end])
        try:
            frontmatter = yaml.safe_load(frontmatter_text) if frontmatter_text.strip() else {}
        except yaml.YAMLError as e:
            raise ValidationError(f"Invalid YAML frontmatter: {e}") from e

        if not isinstance(frontmatter, dict):
            raise ValidationError("Frontmatter must be a YAML object")

        name = frontmatter.get("name", "")
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("Frontmatter must define non-empty 'name'")
        name = name.strip()
        if not SKILL_NAME_RE.match(name) or "--" in name:
            raise ValidationError("Skill name must contain only lowercase letters, digits, and single hyphens")

        description = frontmatter.get("description", "")
        if not isinstance(description, str) or not description.strip():
            raise ValidationError("Frontmatter must define non-empty 'description'")

        return frontmatter

    def validate_skill_name(self, name: str) -> str:
        name = name.strip().lower()
        if not name:
            raise ValidationError("Skill name must not be empty")
        if len(name) > 64:
            raise ValidationError("Skill name must be <= 64 characters")
        if "--" in name or not SKILL_NAME_RE.match(name):
            raise ValidationError("Skill name must contain only lowercase letters, digits, and single hyphens")
        return name
