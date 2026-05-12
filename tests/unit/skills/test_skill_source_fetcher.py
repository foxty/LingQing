"""Unit tests for skill source fetcher infra adapter."""

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock

import httpx
import pytest

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.skills.domain import SkillSourceKind, SkillSourceRef, parse_skill_source_url
from apps.tenant_app_service.skills.skill_source_fetcher import SkillSourceFetcher


def _make_github_archive_zip(skill_name: str, extra_skill: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        prefix = f"repo-main/skills/{skill_name}"
        zf.writestr(
            f"{prefix}/SKILL.md",
            f"---\nname: {skill_name}\ndescription: {skill_name} desc\n---\n\nBody",
        )
        if extra_skill:
            extra_prefix = f"repo-main/skills/{extra_skill}"
            zf.writestr(
                f"{extra_prefix}/SKILL.md",
                f"---\nname: {extra_skill}\ndescription: {extra_skill} desc\n---\n\nBody",
            )
    return buf.getvalue()


class TestSkillSourceFetcher:
    def test_fetch_skills_sh_builds_zip(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "files": [
                {
                    "path": "SKILL.md",
                    "contents": "---\nname: test-skill\ndescription: Test\n---\n\nBody",
                }
            ],
            "hash": "abc123",
        }
        mock_client.get.return_value = mock_resp

        ref = parse_skill_source_url("anthropics/skills/test-skill")
        fetcher = SkillSourceFetcher(client=mock_client)
        result = fetcher.fetch_as_zip(ref)

        assert isinstance(result, io.BytesIO)
        with zipfile.ZipFile(result, "r") as zf:
            assert "SKILL.md" in zf.namelist()
            content = zf.read("SKILL.md").decode()
            assert "name: test-skill" in content

        mock_client.get.assert_called_once_with(
            "https://skills.sh/api/download/anthropics/skills/test-skill"
        )

    def test_fetch_skills_sh_no_files_raises(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"files": []}
        mock_client.get.return_value = mock_resp

        ref = SkillSourceRef(kind=SkillSourceKind.SKILLS_SH, owner="owner", repo="repo", slug="slug")
        fetcher = SkillSourceFetcher(client=mock_client)
        with pytest.raises(ValidationError, match="no files"):
            fetcher.fetch_as_zip(ref)

    def test_fetch_github_single_skill(self):
        archive = _make_github_archive_zip("test-skill-abc")
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = archive
        mock_client.get.return_value = mock_resp

        ref = parse_skill_source_url("https://github.com/owner/repo")
        fetcher = SkillSourceFetcher(client=mock_client)
        result = fetcher.fetch_as_zip(ref)

        with zipfile.ZipFile(result, "r") as zf:
            assert "SKILL.md" in zf.namelist()

    def test_fetch_github_multiple_skills_raises(self):
        archive = _make_github_archive_zip("skill-a", extra_skill="skill-b")
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = archive
        mock_client.get.return_value = mock_resp

        ref = parse_skill_source_url("https://github.com/owner/repo")
        fetcher = SkillSourceFetcher(client=mock_client)
        with pytest.raises(ValidationError, match="multiple skills"):
            fetcher.fetch_as_zip(ref)

    def test_fetch_github_with_path_filter(self):
        archive = _make_github_archive_zip("skill-a", extra_skill="skill-b")
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = archive
        mock_client.get.return_value = mock_resp

        ref = parse_skill_source_url("https://github.com/owner/repo/tree/main/skills/skill-a")
        fetcher = SkillSourceFetcher(client=mock_client)
        result = fetcher.fetch_as_zip(ref)

        with zipfile.ZipFile(result, "r") as zf:
            assert "SKILL.md" in zf.namelist()

    def test_rejects_redirect_to_disallowed_host(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock()
        mock_resp.status_code = 302
        mock_resp.headers = {"location": "https://evil.com/steal"}
        mock_client.get.return_value = mock_resp

        ref = parse_skill_source_url("anthropics/skills/test-skill")
        fetcher = SkillSourceFetcher(client=mock_client)
        with pytest.raises(ValidationError, match="disallowed host"):
            fetcher.fetch_as_zip(ref)

    def test_http_error_raises(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client.get.return_value = mock_resp

        ref = parse_skill_source_url("anthropics/skills/missing-skill")
        fetcher = SkillSourceFetcher(client=mock_client)
        with pytest.raises(ValidationError, match="HTTP 404"):
            fetcher.fetch_as_zip(ref)
