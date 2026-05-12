"""Infra adapter: fetch skill packages from skills.sh and GitHub."""

from __future__ import annotations

import io
import json
import os
import zipfile
from typing import BinaryIO
from urllib.parse import urlparse

import httpx

from apps.shared.core.exceptions import ValidationError
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.skills.domain import (
    ALLOWED_SKILL_SOURCE_HOSTS,
    SkillSourceKind,
    SkillSourceRef,
    skill_md_base_prefix,
)
from apps.tenant_app_service.skills.validator import MAX_SKILL_SIZE_BYTES

logger = get_logger(__name__)

FETCH_TIMEOUT_SECONDS = 15.0
GITHUB_DEFAULT_REFS = ("main", "master")


class SkillSourceFetcher:
    """HTTP adapter that downloads remote skill packages as in-memory ZIP files."""

    def __init__(self, client: httpx.Client | None = None):
        self._client = client
        self._owns_client = client is None

    def fetch_as_zip(self, ref: SkillSourceRef) -> BinaryIO:
        if ref.kind == SkillSourceKind.SKILLS_SH:
            return self._fetch_skills_sh(ref)
        return self._fetch_github(ref)

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False)
        return self._client

    def _fetch_skills_sh(self, ref: SkillSourceRef) -> BinaryIO:
        if not ref.slug:
            raise ValidationError("skills.sh URL must include a skill slug")

        api_url = f"https://skills.sh/api/download/{ref.owner}/{ref.repo}/{ref.slug}"
        data = self._get_json(api_url)
        files = data.get("files")
        if not isinstance(files, list) or not files:
            raise ValidationError("skills.sh returned no files for this skill")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            has_skill_md = False
            for entry in files:
                if not isinstance(entry, dict):
                    continue
                rel_path = entry.get("path", "")
                contents = entry.get("contents", "")
                if not rel_path or not isinstance(contents, str):
                    continue
                if rel_path.endswith("SKILL.md"):
                    has_skill_md = True
                zf.writestr(rel_path, contents.encode("utf-8"))

        if not has_skill_md:
            raise ValidationError("Downloaded skill package does not contain SKILL.md")

        buf.seek(0)
        if buf.getbuffer().nbytes > MAX_SKILL_SIZE_BYTES:
            raise ValidationError(f"Skill package exceeds {MAX_SKILL_SIZE_BYTES // (1024 * 1024)}MB limit")
        return buf

    def _fetch_github(self, ref: SkillSourceRef) -> BinaryIO:
        refs_to_try = [ref.ref] if ref.ref else list(GITHUB_DEFAULT_REFS)
        last_error: Exception | None = None

        for branch_ref in refs_to_try:
            if not branch_ref:
                continue
            try:
                archive_url = f"https://codeload.github.com/{ref.owner}/{ref.repo}/zip/refs/heads/{branch_ref}"
                raw = self._get_bytes(archive_url)
                return self._process_github_archive(raw, ref.path)
            except ValidationError:
                raise
            except Exception as e:
                last_error = e
                logger.debug("GitHub fetch failed for ref %s: %s", branch_ref, e)

        msg = f"Failed to fetch skill from GitHub ({ref.owner}/{ref.repo})"
        if last_error:
            msg = f"{msg}: {last_error}"
        raise ValidationError(msg)

    def _process_github_archive(self, raw: bytes, path_filter: str | None) -> BinaryIO:
        if len(raw) > MAX_SKILL_SIZE_BYTES:
            raise ValidationError(f"Skill package exceeds {MAX_SKILL_SIZE_BYTES // (1024 * 1024)}MB limit")

        with zipfile.ZipFile(io.BytesIO(raw), "r") as src:
            members = src.namelist()
            skill_md_paths = _find_skill_md_paths(members, path_filter)

            if not skill_md_paths:
                raise ValidationError("Archive does not contain SKILL.md")

            if len(skill_md_paths) > 1 and not path_filter:
                dirs = sorted({os.path.dirname(p) for p in skill_md_paths})
                raise ValidationError(
                    f"Repository contains multiple skills. Specify a path: {', '.join(dirs)}"
                )

            base_dir = skill_md_base_prefix(skill_md_paths[0])

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
                for member in members:
                    member_path = os.path.normpath(member)
                    if not member_path or member_path.endswith("/"):
                        continue
                    if member_path.startswith("..") or member_path.startswith("/"):
                        continue
                    if base_dir and not (
                        member_path == base_dir or member_path.startswith(base_dir + "/")
                    ):
                        continue

                    if base_dir and member_path.startswith(base_dir + "/"):
                        rel_path = member_path[len(base_dir) + 1 :]
                    elif base_dir and member_path == base_dir:
                        continue
                    else:
                        rel_path = member_path

                    if not rel_path:
                        continue
                    dst.writestr(rel_path, src.read(member))

        buf.seek(0)
        return buf

    def _get_json(self, url: str) -> dict:
        self._validate_url(url)
        client = self._get_client()
        resp = client.get(url)
        self._validate_response(url, resp)
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON response from {urlparse(url).hostname}") from e
        if not isinstance(data, dict):
            raise ValidationError(f"Unexpected response format from {urlparse(url).hostname}")
        return data

    def _get_bytes(self, url: str) -> bytes:
        self._validate_url(url)
        client = self._get_client()
        resp = client.get(url)
        self._validate_response(url, resp)
        content = resp.content
        if len(content) > MAX_SKILL_SIZE_BYTES:
            raise ValidationError(f"Download exceeds {MAX_SKILL_SIZE_BYTES // (1024 * 1024)}MB limit")
        return content

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValidationError("Only HTTPS URLs are supported")
        host = (parsed.hostname or "").lower()
        if host not in ALLOWED_SKILL_SOURCE_HOSTS:
            raise ValidationError(f"Host not allowed: {host}")

    @staticmethod
    def _validate_response(url: str, resp: httpx.Response) -> None:
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location", "")
            redirect_host = (urlparse(location).hostname or "").lower()
            if redirect_host not in ALLOWED_SKILL_SOURCE_HOSTS:
                raise ValidationError(f"Redirect to disallowed host: {redirect_host or location}")
            raise ValidationError(f"Unexpected redirect from {urlparse(url).hostname}")
        if resp.status_code >= 400:
            raise ValidationError(
                f"Failed to fetch from {urlparse(url).hostname}: HTTP {resp.status_code}"
            )

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> SkillSourceFetcher:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _find_skill_md_paths(members: list[str], path_filter: str | None) -> list[str]:
    results: list[str] = []
    for member in members:
        normal = os.path.normpath(member)
        if not normal.endswith("SKILL.md"):
            continue
        if normal.startswith("__") or "/__" in normal:
            continue
        if path_filter and not _member_matches_path_filter(normal, path_filter):
            continue
        results.append(normal)
    return results


def _member_matches_path_filter(member_path: str, path_filter: str) -> bool:
    parts = member_path.split("/")
    if len(parts) < 2:
        return False
    rel = "/".join(parts[1:])
    filter_norm = path_filter.strip("/")
    return rel == filter_norm or rel.startswith(filter_norm + "/") or rel.endswith("/" + filter_norm + "/SKILL.md")
