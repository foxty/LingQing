"""Domain models for skill management."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import BinaryIO, Protocol
from urllib.parse import urlparse

from apps.shared.core.exceptions import ValidationError


class SkillType(StrEnum):
    BUILTIN = "builtin"
    TENANT = "tenant"
    PERSONAL = "personal"


class SkillSourceKind(StrEnum):
    SKILLS_SH = "skills_sh"
    GITHUB = "github"


@dataclass(frozen=True)
class SkillSourceRef:
    """Parsed reference to an external skill source."""

    kind: SkillSourceKind
    owner: str
    repo: str
    slug: str | None = None
    ref: str | None = None
    path: str | None = None


class SkillPackageFetcherPort(Protocol):
    """Infra port: fetch a remote skill package as an in-memory ZIP."""

    def fetch_as_zip(self, ref: SkillSourceRef) -> BinaryIO: ...


ALLOWED_SKILL_SOURCE_HOSTS = frozenset(
    {
        "skills.sh",
        "www.skills.sh",
        "github.com",
        "www.github.com",
        "codeload.github.com",
        "raw.githubusercontent.com",
    }
)

_SHORTHAND_SOURCE_RE = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)?$")


def parse_skill_source_url(url: str) -> SkillSourceRef:
    """Parse a skills.sh page URL, GitHub URL, or shorthand into a SkillSourceRef."""
    url = url.strip()
    if not url:
        raise ValidationError("URL must not be empty")

    if _SHORTHAND_SOURCE_RE.match(url):
        parts = url.split("/")
        if len(parts) == 3:
            return SkillSourceRef(
                kind=SkillSourceKind.SKILLS_SH, owner=parts[0], repo=parts[1], slug=parts[2]
            )
        if len(parts) == 2:
            return SkillSourceRef(kind=SkillSourceKind.GITHUB, owner=parts[0], repo=parts[1])
        raise ValidationError(f"Invalid shorthand format: {url}")

    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme != "https":
        raise ValidationError("Only HTTPS URLs are supported")

    host = (parsed.hostname or "").lower()
    if host and host not in ALLOWED_SKILL_SOURCE_HOSTS:
        raise ValidationError(f"Unsupported host: {host}. Only skills.sh and GitHub URLs are allowed.")

    path = parsed.path.strip("/")
    if not path:
        raise ValidationError("URL path is empty")

    if host in ("skills.sh", "www.skills.sh"):
        return _parse_skills_sh_path(path)

    if host in ("github.com", "www.github.com"):
        return _parse_github_source_path(path)

    raise ValidationError(f"Unsupported URL format: {url}")


def find_skill_md_base(members: list[str]) -> str | None:
    """Return zip path prefix containing SKILL.md, or None if SKILL.md is at root."""
    for member in members:
        normal = os.path.normpath(member)
        if normal.endswith("SKILL.md"):
            parent = os.path.dirname(normal)
            return parent if parent else None
    return None


def skill_md_base_prefix(skill_md_path: str) -> str | None:
    """Return path prefix for a specific SKILL.md member inside an archive."""
    normal = os.path.normpath(skill_md_path)
    if normal.endswith("SKILL.md"):
        parent = os.path.dirname(normal)
        return parent if parent else None
    return None


def _parse_skills_sh_path(path: str) -> SkillSourceRef:
    parts = path.split("/")
    if len(parts) == 3:
        return SkillSourceRef(
            kind=SkillSourceKind.SKILLS_SH, owner=parts[0], repo=parts[1], slug=parts[2]
        )
    raise ValidationError(
        "skills.sh URL must be https://skills.sh/{owner}/{repo}/{slug} or owner/repo/slug"
    )


def _parse_github_source_path(path: str) -> SkillSourceRef:
    parts = path.split("/")
    if len(parts) < 2:
        raise ValidationError("GitHub URL must include owner and repo")

    owner, repo = parts[0], parts[1]
    if len(parts) == 2:
        return SkillSourceRef(kind=SkillSourceKind.GITHUB, owner=owner, repo=repo)

    if len(parts) >= 4 and parts[2] in ("tree", "blob"):
        ref = parts[3]
        subpath = "/".join(parts[4:]) if len(parts) > 4 else ""
        if subpath.endswith("/SKILL.md"):
            subpath = subpath[: -len("/SKILL.md")]
        elif subpath == "SKILL.md":
            subpath = ""
        return SkillSourceRef(
            kind=SkillSourceKind.GITHUB, owner=owner, repo=repo, ref=ref, path=subpath or None
        )

    raise ValidationError(
        "GitHub URL must be https://github.com/{owner}/{repo} or "
        "https://github.com/{owner}/{repo}/tree/{ref}/{path}"
    )


@dataclass
class SkillLocator:
    """Resolved filesystem paths for a skill across host and container.

    Encapsulates the "where does this skill live" question so that
    consumers (sandbox, tools, loader) never need path-assembly logic.
    Lives in the skills domain because it is a pure skill on-disk concept;
    ``agents.domain`` re-exports it for back-compat.
    """

    scope: SkillType
    host_skill_dir: str
    host_packages_dir: str | None
    container_skill_dir: str
    container_packages_dir: str | None


@dataclass
class SkillConfigData:
    name: str
    type: SkillType
    description: str
    enabled: bool = True
    env_vars: dict[str, str] = field(default_factory=dict)
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_json(self) -> str:
        return json.dumps(
            {
                "name": self.name,
                "type": self.type,
                "description": self.description,
                "enabled": self.enabled,
                "env_vars": self.env_vars,
                "created_by": self.created_by,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            },
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, raw: str) -> SkillConfigData:
        data = json.loads(raw)
        type_str = data.get("type", "tenant")
        # Backward compatibility: treat empty string as tenant
        if not type_str:
            type_str = "tenant"
        return cls(
            name=data["name"],
            type=SkillType(type_str),
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            env_vars=data.get("env_vars", {}),
            created_by=data.get("created_by", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
