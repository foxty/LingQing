"""Integration tests for tenant identity admin APIs."""

from __future__ import annotations

from uuid import uuid4

import pytest

from tests.integration.conftest import make_auth_headers
from tests.integration.helpers.ingress_helpers import seed_pending_slack_identity


class TestIdentityAdminApi:
    @pytest.mark.asyncio
    async def test_login_domain_crud(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        token = tenant["token"]
        new_domain = f"added-{uuid4().hex[:8]}.example"

        add_resp = await client.post(
            "/tenants/identity/domains",
            json={"domains": [new_domain]},
            headers=make_auth_headers(token),
        )
        assert add_resp.status_code == 201
        assert any(d["domain"] == new_domain for d in add_resp.json())

        list_resp = await client.get("/tenants/identity/domains", headers=make_auth_headers(token))
        assert list_resp.status_code == 200
        domain_row = next(d for d in list_resp.json() if d["domain"] == new_domain)

        delete_resp = await client.delete(
            f"/tenants/identity/domains/{domain_row['id']}",
            headers=make_auth_headers(token),
        )
        assert delete_resp.status_code == 204

    @pytest.mark.asyncio
    async def test_force_sso_requires_break_glass_admin(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        token = tenant["token"]
        admin_id = tenant["admin"].id

        settings_resp = await client.get("/tenants/identity/settings", headers=make_auth_headers(token))
        assert settings_resp.status_code == 200
        assert settings_resp.json()["break_glass_admin_count"] == 0

        fail_resp = await client.put(
            "/tenants/identity/settings",
            json={"force_sso": True},
            headers=make_auth_headers(token),
        )
        assert fail_resp.status_code == 400
        assert fail_resp.json()["code"] == "SSO_FORCE_SSO_NO_BREAK_GLASS"

        break_glass_resp = await client.put(
            f"/tenants/users/{admin_id}/break-glass",
            json={"is_break_glass": True},
            headers=make_auth_headers(token),
        )
        assert break_glass_resp.status_code == 200
        assert break_glass_resp.json()["break_glass_admin_count"] == 1

        enable_resp = await client.put(
            "/tenants/identity/settings",
            json={"force_sso": True},
            headers=make_auth_headers(token),
        )
        assert enable_resp.status_code == 200
        assert enable_resp.json()["force_sso"] is True

    @pytest.mark.asyncio
    async def test_update_workspace_bind_policy(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]

        sources_resp = await client.get("/tenants/identity-sources", headers=make_auth_headers(token))
        assert sources_resp.status_code == 200
        workspace = next(s for s in sources_resp.json() if s["source_kind"] == "channel_workspace")

        patch_resp = await client.patch(
            f"/tenants/identity-sources/{workspace['id']}",
            json={"bind_policy": "pending_approval"},
            headers=make_auth_headers(token),
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["bind_policy"] == "pending_approval"

    @pytest.mark.asyncio
    async def test_pending_approve_and_reject(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        token = tenant["token"]
        slack_user = f"U_admin_{uuid4().hex[:8]}"
        email = f"admin_flow_{uuid4().hex[:8]}@{tenant['external_domain']}"

        row = await seed_pending_slack_identity(
            slack_test_setup["session_factory"],
            tenant_id=tenant["tenant"].id,
            team_id="T_TENANT_A",
            slack_user=slack_user,
            email=email,
        )

        list_resp = await client.get("/tenants/identity/pending", headers=make_auth_headers(token))
        assert any(p["id"] == row.id for p in list_resp.json())

        approve_resp = await client.post(
            f"/tenants/identity/pending/{row.id}/approve",
            headers=make_auth_headers(token),
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "active"

        slack_user_reject = f"U_admin_reject_{uuid4().hex[:8]}"
        row_reject = await seed_pending_slack_identity(
            slack_test_setup["session_factory"],
            tenant_id=tenant["tenant"].id,
            team_id="T_TENANT_A",
            slack_user=slack_user_reject,
            email=f"reject_{uuid4().hex[:8]}@{tenant['external_domain']}",
        )
        reject_resp = await client.post(
            f"/tenants/identity/pending/{row_reject.id}/reject",
            headers=make_auth_headers(token),
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_manage_tenant_a_pending(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant_a = slack_test_setup["tenants"]["tenant_a"]
        tenant_b = slack_test_setup["tenants"]["tenant_b"]
        slack_user = f"U_cross_{uuid4().hex[:8]}"
        email = f"cross_{uuid4().hex[:8]}@{tenant_a['external_domain']}"

        row = await seed_pending_slack_identity(
            slack_test_setup["session_factory"],
            tenant_id=tenant_a["tenant"].id,
            team_id="T_TENANT_A",
            slack_user=slack_user,
            email=email,
        )

        cross_resp = await client.post(
            f"/tenants/identity/pending/{row.id}/approve",
            headers=make_auth_headers(tenant_b["token"]),
        )
        assert cross_resp.status_code in (403, 404)
