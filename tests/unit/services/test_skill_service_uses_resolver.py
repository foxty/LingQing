"""Unit test: SkillService delegates reads to the injected SkillResolver.

Locks in the contract from PR 5: ``SkillService.list_skills``,
``get_skill`` and ``toggle_enabled`` go through the resolver rather
than re-implementing skill discovery. Tests inject a fake resolver
and assert it is consulted.
"""

from __future__ import annotations

from typing import Any

from apps.tenant_app_service.agents.domain import SkillConfig
from apps.tenant_app_service.skills.domain import SkillType
from apps.tenant_app_service.skills.service import SkillService


class _FakeResolver:
    """Records calls and returns canned skill data."""

    def __init__(self, skills: dict[str, SkillConfig] | None = None) -> None:
        self.resolve_calls: list[dict[str, Any]] = []
        self.clear_cache_calls = 0
        self._skills = skills or {}

    def resolve(
        self,
        tenant_id: int | None = None,
        user_id: int | None = None,
        force_reload: bool = False,
        type_filter: SkillType | None = None,
    ) -> dict[str, SkillConfig]:
        self.resolve_calls.append(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "force_reload": force_reload,
                "type_filter": type_filter,
            }
        )
        if type_filter is None:
            return dict(self._skills)
        return {n: s for n, s in self._skills.items() if s.scope == type_filter}

    def clear_cache(self) -> None:
        self.clear_cache_calls += 1


def _make_skill(name: str, scope: SkillType = SkillType.TENANT) -> SkillConfig:
    """Minimal SkillConfig stub for resolver tests."""
    from apps.tenant_app_service.agents.domain import SkillLocator

    return SkillConfig(
        name=name,
        description=f"desc for {name}",
        system_prompt="p",
        tools=[],
        api_refs=[],
        source_file=f"/fake/{name}",
        source_format="standard_skill",
        scope=scope,
        locator=SkillLocator(
            scope=scope,
            host_skill_dir=f"/fake/{name}",
            host_packages_dir=None,
            container_skill_dir=f"/fake/{name}",
            container_packages_dir=None,
        ),
    )


def test_list_skills_delegates_to_resolver(tmp_path) -> None:
    """``list_skills`` calls the resolver once per scope and aggregates."""
    resolver = _FakeResolver(
        skills={
            "alpha": _make_skill("alpha", SkillType.TENANT),
            "beta": _make_skill("beta", SkillType.BUILTIN),
        }
    )
    svc = SkillService(data_root=str(tmp_path), resolver=resolver)
    result = svc.list_skills(tenant_id=1, user_id=1)

    # One resolve call per scope (builtin, tenant, personal) when no filter.
    assert len(resolver.resolve_calls) == 3
    assert {c["type_filter"] for c in resolver.resolve_calls} == {
        SkillType.BUILTIN,
        SkillType.TENANT,
        SkillType.PERSONAL,
    }
    # Every call asked for the same tenant/user.
    assert all(c["tenant_id"] == 1 and c["user_id"] == 1 for c in resolver.resolve_calls)
    # Aggregation surface: 2 unique skills returned.
    assert {s.name for s in result} == {"alpha", "beta"}


def test_list_skills_with_type_filter_calls_resolver_once(tmp_path) -> None:
    """``list_skills(type_filter=X)`` short-circuits to a single resolver call."""
    resolver = _FakeResolver()
    svc = SkillService(data_root=str(tmp_path), resolver=resolver)
    svc.list_skills(tenant_id=7, user_id=3, type_filter=SkillType.TENANT)

    assert len(resolver.resolve_calls) == 1
    call = resolver.resolve_calls[0]
    assert call["type_filter"] == SkillType.TENANT
    assert call["tenant_id"] == 7
    assert call["user_id"] == 3


def test_get_skill_delegates_to_resolver(tmp_path) -> None:
    """``get_skill`` calls ``resolve`` (no filter) and looks up by name."""
    resolver = _FakeResolver(
        skills={"only": _make_skill("only", SkillType.TENANT)},
    )
    svc = SkillService(data_root=str(tmp_path), resolver=resolver)
    info = svc.get_skill(tenant_id=1, user_id=1, name="only")

    assert info is not None
    assert info.name == "only"
    assert len(resolver.resolve_calls) == 1
    assert resolver.resolve_calls[0]["type_filter"] is None


def test_create_skill_clears_resolver_cache(tmp_path) -> None:
    """After upload, the resolver cache is dropped so the new skill is visible."""
    import io

    resolver = _FakeResolver()
    svc = SkillService(data_root=str(tmp_path), resolver=resolver)

    # Build a tiny valid SKILL.md zip.
    buf = io.BytesIO()
    import zipfile

    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "SKILL.md",
            "---\nname: fresh\ndescription: new skill\n---\n\nBody",
        )
    buf.seek(0)

    svc.create_skill(
        tenant_id=1,
        user_id=1,
        skill_type=SkillType.TENANT,
        zip_file=buf,
        created_by="tester",
    )
    assert resolver.clear_cache_calls == 1


def test_delete_skill_clears_resolver_cache(tmp_path) -> None:
    """After delete, the resolver cache is dropped so the skill disappears."""
    resolver = _FakeResolver()
    svc = SkillService(data_root=str(tmp_path), resolver=resolver)

    skill_dir = tmp_path / "tenants" / "tenant_1" / "skills" / "stale"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: stale\ndescription: d\n---\n\nBody")

    svc.delete_skill(tenant_id=1, user_id=1, skill_type=SkillType.TENANT, name="stale")
    assert resolver.clear_cache_calls == 1
