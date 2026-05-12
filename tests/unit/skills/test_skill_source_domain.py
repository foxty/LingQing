"""Unit tests for skill import domain parsing."""

from __future__ import annotations

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.skills.domain import SkillSourceKind, parse_skill_source_url


class TestParseSkillSourceUrl:
    def test_skills_sh_full_url(self):
        ref = parse_skill_source_url("https://skills.sh/anthropics/skills/pdf")
        assert ref.kind == SkillSourceKind.SKILLS_SH
        assert ref.owner == "anthropics"
        assert ref.repo == "skills"
        assert ref.slug == "pdf"

    def test_skills_sh_shorthand(self):
        ref = parse_skill_source_url("anthropics/skills/pdf")
        assert ref.kind == SkillSourceKind.SKILLS_SH
        assert ref.slug == "pdf"

    def test_github_repo_url(self):
        ref = parse_skill_source_url("https://github.com/anthropics/skills")
        assert ref.kind == SkillSourceKind.GITHUB
        assert ref.owner == "anthropics"
        assert ref.repo == "skills"
        assert ref.ref is None

    def test_github_shorthand(self):
        ref = parse_skill_source_url("anthropics/skills")
        assert ref.kind == SkillSourceKind.GITHUB
        assert ref.owner == "anthropics"
        assert ref.repo == "skills"

    def test_github_tree_url(self):
        ref = parse_skill_source_url(
            "https://github.com/anthropics/skills/tree/main/skills/pdf"
        )
        assert ref.kind == SkillSourceKind.GITHUB
        assert ref.ref == "main"
        assert ref.path == "skills/pdf"

    def test_github_blob_skill_md_url(self):
        ref = parse_skill_source_url(
            "https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md"
        )
        assert ref.kind == SkillSourceKind.GITHUB
        assert ref.ref == "main"
        assert ref.path == "skills/pdf"

    def test_rejects_http(self):
        with pytest.raises(ValidationError, match="HTTPS"):
            parse_skill_source_url("http://skills.sh/owner/repo/slug")

    def test_rejects_localhost(self):
        with pytest.raises(ValidationError, match="Unsupported host"):
            parse_skill_source_url("https://localhost/skills/test")

    def test_rejects_empty(self):
        with pytest.raises(ValidationError, match="empty"):
            parse_skill_source_url("   ")

    def test_rejects_invalid_skills_sh_path(self):
        with pytest.raises(ValidationError, match="skills.sh"):
            parse_skill_source_url("https://skills.sh/only-two")
