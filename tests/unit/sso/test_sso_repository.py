"""Integration tests for SsoRepository using in-memory SQLite.

Locks tenant isolation, config encryption, login state/ticket consumption,
and break-glass admin counting. Uses the shared unit async_db_session fixture.
"""

import pytest

from apps.shared.db.models import Tenant, TenantMembership, User
from apps.shared.external_identity.identity_source_repository import IdentitySourceRepository
from apps.tenant_app_service.auth.repository import UserRepository
from apps.tenant_app_service.identity.repository import IdentityRepository
from apps.tenant_app_service.sso.repository import SsoRepository

pytestmark = pytest.mark.asyncio


async def _make_tenant(db, name: str, force_sso: bool = False) -> Tenant:
    tenant = Tenant(name=name, slug=name.lower(), status="active", force_sso=force_sso)
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    return tenant


async def _make_user(db, tenant_id: int, username: str, email: str | None = None) -> User:
    user = User(
        username=username,
        email=email.lower() if email else None,
        hashed_password="x",
        role="member",
        tenant_id=tenant_id,
        status="active",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def _make_membership(db, tenant_id: int, user_id: int, break_glass: bool = False) -> TenantMembership:
    m = TenantMembership(
        tenant_id=tenant_id,
        user_id=user_id,
        status="active",
        is_break_glass=break_glass,
    )
    db.add(m)
    await db.flush()
    return m


async def _create_oidc_provider(
    db,
    *,
    tenant_id: int,
    display_name: str = "P",
    enabled: bool = True,
    config: dict | None = None,
    bind_policy: str = "jit_create",
):
    repo = SsoRepository(db)
    source_repo = IdentitySourceRepository(db)
    source = await source_repo.create_login_provider_source(
        tenant_id=tenant_id,
        display_name=display_name,
        bind_policy=bind_policy,
    )
    provider = await repo.create_provider(
        tenant_id=tenant_id,
        provider_type="oidc",
        display_name=display_name,
        enabled=enabled,
        config=config or {"client_id": "c"},
        identity_source_id=source.id,
    )
    await source_repo.finalize_login_provider_source_key(source, provider.id)
    return provider


# ---------- Provider config encryption ----------


async def test_provider_config_secret_is_encrypted_at_rest(async_db_session):
    tenant = await _make_tenant(async_db_session, "Acme")
    repo = SsoRepository(async_db_session)
    provider = await _create_oidc_provider(
        async_db_session,
        tenant_id=tenant.id,
        display_name="Google",
        config={"client_id": "cid", "client_secret": "super-secret", "issuer": "https://g"},
    )
    # Stored config_json must NOT contain plaintext secret
    stored = provider.config_json or {}
    assert stored.get("client_secret") != "super-secret"
    # Decrypted config must contain plaintext
    decrypted = repo.decrypt_provider_config(provider)
    assert decrypted["client_secret"] == "super-secret"
    assert decrypted["client_id"] == "cid"


# ---------- Tenant isolation ----------


async def test_list_providers_is_tenant_scoped(async_db_session):
    t1 = await _make_tenant(async_db_session, "Acme")
    t2 = await _make_tenant(async_db_session, "Globex")
    repo = SsoRepository(async_db_session)
    await _create_oidc_provider(async_db_session, tenant_id=t1.id, display_name="P1")
    await _create_oidc_provider(async_db_session, tenant_id=t2.id, display_name="P2")
    t1_providers = await repo.list_providers(t1.id)
    t2_providers = await repo.list_providers(t2.id)
    assert len(t1_providers) == 1
    assert t1_providers[0].display_name == "P1"
    assert len(t2_providers) == 1
    assert t2_providers[0].display_name == "P2"


async def test_get_provider_cross_tenant_returns_none(async_db_session):
    t1 = await _make_tenant(async_db_session, "Acme")
    t2 = await _make_tenant(async_db_session, "Globex")
    repo = SsoRepository(async_db_session)
    p = await _create_oidc_provider(async_db_session, tenant_id=t1.id, display_name="P1")
    # t2 cannot read t1's provider
    assert await repo.get_provider(t2.id, p.id) is None


async def test_pending_identities_are_tenant_scoped(async_db_session):
    t1 = await _make_tenant(async_db_session, "Acme")
    t2 = await _make_tenant(async_db_session, "Globex")
    repo = SsoRepository(async_db_session)
    p1 = await _create_oidc_provider(async_db_session, tenant_id=t1.id, display_name="P1")
    p2 = await _create_oidc_provider(async_db_session, tenant_id=t2.id, display_name="P2")
    await repo.create_identity(
        tenant_id=t1.id,
        identity_source_id=p1.identity_source_id,
        external_subject="s1",
        user_id=None,
        email="a@company.com",
        display_name="A",
        status="pending",
    )
    await repo.create_identity(
        tenant_id=t2.id,
        identity_source_id=p2.identity_source_id,
        external_subject="s2",
        user_id=None,
        email="b@company.com",
        display_name="B",
        status="pending",
    )
    t1_pending = await repo.list_pending_identities(t1.id)
    t2_pending = await repo.list_pending_identities(t2.id)
    assert len(t1_pending) == 1
    assert t1_pending[0].external_subject == "s1"
    assert len(t2_pending) == 1
    assert t2_pending[0].external_subject == "s2"


# ---------- Login domains ----------


async def test_login_domain_is_lowercased_and_unique(async_db_session):
    t1 = await _make_tenant(async_db_session, "Acme")
    repo = IdentityRepository(async_db_session)
    await repo.add_domain(t1.id, "Company.COM")
    # Lookup is case-insensitive
    fetched = await repo.get_domain("company.com")
    assert fetched is not None
    assert fetched.domain == "company.com"
    assert fetched.tenant_id == t1.id


async def test_remove_domain_is_tenant_scoped(async_db_session):
    t1 = await _make_tenant(async_db_session, "Acme")
    t2 = await _make_tenant(async_db_session, "Globex")
    repo = IdentityRepository(async_db_session)
    d = await repo.add_domain(t1.id, "acme.com")
    # t2 cannot delete t1's domain
    assert await repo.remove_domain(t2.id, d.id) is False
    # t1 can
    assert await repo.remove_domain(t1.id, d.id) is True


# ---------- Login state (PKCE) consumption ----------


async def test_login_state_consumed_once(async_db_session):
    t = await _make_tenant(async_db_session, "Acme")
    repo = SsoRepository(async_db_session)
    p = await _create_oidc_provider(async_db_session, tenant_id=t.id, display_name="P")
    state = await repo.create_login_state(
        tenant_id=t.id,
        provider_id=p.id,
        state="STATE-1",
        code_verifier="v",
        nonce="n",
    )
    assert state.state == "STATE-1"
    # First consume succeeds
    consumed = await repo.consume_login_state("STATE-1")
    assert consumed is not None
    assert consumed.consumed is True
    # Second consume fails (already consumed)
    assert await repo.consume_login_state("STATE-1") is None


async def test_login_state_expired_not_consumed(async_db_session):
    t = await _make_tenant(async_db_session, "Acme")
    repo = SsoRepository(async_db_session)
    p = await _create_oidc_provider(async_db_session, tenant_id=t.id, display_name="P")
    # ttl=0 means already expired
    await repo.create_login_state(
        tenant_id=t.id,
        provider_id=p.id,
        state="STATE-EXP",
        code_verifier="v",
        nonce="n",
        ttl_seconds=0,
    )
    # Need to advance time: SQLite stores tz-aware; the row's expires_at is now.
    # consume checks expires_at > now, so an expires_at equal to now fails.
    assert await repo.consume_login_state("STATE-EXP") is None


# ---------- Login ticket consumption ----------


async def test_login_ticket_consumed_once(async_db_session):
    t = await _make_tenant(async_db_session, "Acme")
    repo = SsoRepository(async_db_session)
    user = await _make_user(async_db_session, t.id, "alice", "alice@company.com")
    ticket = await repo.create_login_ticket(tenant_id=t.id, user_id=user.id)
    consumed = await repo.consume_login_ticket(ticket.ticket)
    assert consumed is not None
    assert consumed.user_id == user.id
    assert consumed.consumed is True
    # Replay rejected
    assert await repo.consume_login_ticket(ticket.ticket) is None


async def test_login_ticket_unknown_rejected(async_db_session):
    repo = SsoRepository(async_db_session)
    assert await repo.consume_login_ticket("does-not-exist") is None


# ---------- Break-glass admin counting ----------


async def test_count_break_glass_admins(async_db_session):
    t = await _make_tenant(async_db_session, "Acme")
    repo = IdentityRepository(async_db_session)
    u1 = await _make_user(async_db_session, t.id, "bg", "bg@company.com")
    u2 = await _make_user(async_db_session, t.id, "normal", "n@company.com")
    await _make_membership(async_db_session, t.id, u1.id, break_glass=True)
    await _make_membership(async_db_session, t.id, u2.id, break_glass=False)
    assert await repo.count_break_glass_admins(t.id) == 1


async def test_count_break_glass_excludes_inactive(async_db_session):
    t = await _make_tenant(async_db_session, "Acme")
    repo = IdentityRepository(async_db_session)
    u = await _make_user(async_db_session, t.id, "bg", "bg@company.com")
    m = await _make_membership(async_db_session, t.id, u.id, break_glass=True)
    m.status = "inactive"
    await async_db_session.flush()
    assert await repo.count_break_glass_admins(t.id) == 0


# ---------- Force SSO ----------


async def test_set_force_sso(async_db_session):
    t = await _make_tenant(async_db_session, "Acme", force_sso=False)
    repo = IdentityRepository(async_db_session)
    await repo.set_force_sso(t.id, True)
    refreshed = await repo.get_tenant(t.id)
    assert refreshed.force_sso is True


# ---------- Email member lookup ----------


async def test_count_members_by_email_case_insensitive(async_db_session):
    t = await _make_tenant(async_db_session, "Acme")
    repo = SsoRepository(async_db_session)
    u = await _make_user(async_db_session, t.id, "alice", "Alice@Company.com")
    await _make_membership(async_db_session, t.id, u.id)
    members = await repo.count_members_by_email(t.id, "alice@company.com")
    assert len(members) == 1


async def test_count_members_by_email_two_members_collision(async_db_session):
    t = await _make_tenant(async_db_session, "Acme")
    repo = SsoRepository(async_db_session)
    u1 = await _make_user(async_db_session, t.id, "a1", "shared@company.com")
    u2 = await _make_user(async_db_session, t.id, "a2", "shared@company.com")
    await _make_membership(async_db_session, t.id, u1.id)
    await _make_membership(async_db_session, t.id, u2.id)
    members = await repo.count_members_by_email(t.id, "shared@company.com")
    assert len(members) == 2


# ---------- Unique username ----------


async def test_get_unique_username_uniquifies(async_db_session):
    t = await _make_tenant(async_db_session, "Acme")
    u = await _make_user(async_db_session, t.id, "alice", "alice@company.com")
    await _make_membership(async_db_session, t.id, u.id)
    user_repo = UserRepository(async_db_session)
    # "alice" taken -> should return "alice2"
    name = await user_repo.get_unique_username(t.id, "alice")
    assert name == "alice2"


async def test_get_unique_username_returns_base_when_free(async_db_session):
    t = await _make_tenant(async_db_session, "Acme")
    user_repo = UserRepository(async_db_session)
    name = await user_repo.get_unique_username(t.id, "newuser")
    assert name == "newuser"


async def test_create_jit_member_uniquifies_username(async_db_session):
    t = await _make_tenant(async_db_session, "Acme")
    u = await _make_user(async_db_session, t.id, "alice", "alice@company.com")
    await _make_membership(async_db_session, t.id, u.id)
    user_repo = UserRepository(async_db_session)
    jit = await user_repo.create_jit_member(tenant_id=t.id, email="alice@company.com", display_name="Alice")
    assert jit.username == "alice2"
    assert jit.role == "viewer"
    assert jit.email == "alice@company.com"
    assert jit.status == "active"
    # membership created
    members = await user_repo.get_by_tenant(t.id)
    assert any(m.id == jit.id for m in members)


async def test_create_jit_member_placeholder_password_unusable(async_db_session):
    t = await _make_tenant(async_db_session, "Acme")
    user_repo = UserRepository(async_db_session)
    jit = await user_repo.create_jit_member(tenant_id=t.id, email="bob@company.com", display_name="Bob")
    # placeholder starts with "!" so bcrypt verify can never match a real input
    assert jit.hashed_password.startswith("!")
