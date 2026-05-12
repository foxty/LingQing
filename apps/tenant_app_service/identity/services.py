"""Application services for tenant identity admin."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.shared.db.models import AgentIngressEndpoint, AuthProvider
from apps.shared.external_identity import STATUS_PENDING, IdentityBindingService
from apps.shared.external_identity.identity_source_repository import IdentitySourceRepository
from apps.shared.external_identity.repository import ExternalIdentityRepository
from apps.tenant_app_service.auth.repository import UserRepository
from apps.tenant_app_service.identity.domain import can_enable_force_sso, validate_policy
from apps.tenant_app_service.identity.dtos import (
    IdentitySettingsResponse,
    IdentitySourceResponse,
    LoginDomainResponse,
    PendingIdentityResponse,
    UpdateIdentitySourceRequest,
)
from apps.tenant_app_service.identity.repository import IdentityRepository


class IdentityAdminService:
    """Channel-agnostic tenant identity policy and pending queue admin."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = IdentityRepository(db)
        self.source_repo = IdentitySourceRepository(db)
        self.identity_repo = ExternalIdentityRepository(db)
        self.binding_service = IdentityBindingService(db)

    async def list_login_domain_names(self, tenant_id: int) -> list[str]:
        rows = await self.repo.list_domains(tenant_id)
        return [r.domain for r in rows]

    async def list_domains(self, tenant_id: int) -> list[LoginDomainResponse]:
        rows = await self.repo.list_domains(tenant_id)
        return [LoginDomainResponse(id=r.id, tenant_id=r.tenant_id, domain=r.domain) for r in rows]

    async def add_domains(self, tenant_id: int, domains: list[str]) -> list[LoginDomainResponse]:
        out: list[LoginDomainResponse] = []
        for domain in domains:
            normalized = domain.strip().lower()
            if not normalized:
                continue
            existing = await self.repo.get_domain(normalized)
            if existing:
                if existing.tenant_id != tenant_id:
                    raise DuplicateResourceError(
                        f"Domain {normalized} already claimed by another tenant",
                        {"code": "SSO_DOMAIN_CLAIMED"},
                    )
                continue
            row = await self.repo.add_domain(tenant_id, normalized)
            out.append(LoginDomainResponse(id=row.id, tenant_id=row.tenant_id, domain=row.domain))
        return out

    async def remove_domain(self, tenant_id: int, domain_id: int) -> bool:
        return await self.repo.remove_domain(tenant_id, domain_id)

    async def get_domain_by_name(self, domain: str):
        return await self.repo.get_domain(domain)

    async def get_settings(self, tenant_id: int) -> IdentitySettingsResponse:
        tenant = await self.repo.get_tenant(tenant_id)
        if not tenant:
            raise ResourceNotFoundError("Tenant not found")
        count = await self.repo.count_break_glass_admins(tenant_id)
        return IdentitySettingsResponse(force_sso=tenant.force_sso, break_glass_admin_count=count)

    async def update_force_sso(self, tenant_id: int, force_sso: bool) -> IdentitySettingsResponse:
        if force_sso:
            count = await self.repo.count_break_glass_admins(tenant_id)
            if not can_enable_force_sso(count):
                raise ValidationError(
                    "Cannot enable force SSO without at least one break-glass admin",
                    {"code": "SSO_FORCE_SSO_NO_BREAK_GLASS"},
                )
        await self.repo.set_force_sso(tenant_id, force_sso)
        return await self.get_settings(tenant_id)

    async def set_membership_break_glass(self, tenant_id: int, user_id: int, is_break_glass: bool) -> None:
        membership = await self.repo.set_membership_break_glass(tenant_id, user_id, is_break_glass)
        if not membership:
            raise ResourceNotFoundError("Tenant membership not found")

    async def list_identity_sources(self, tenant_id: int) -> list[IdentitySourceResponse]:
        sources = await self.source_repo.list_for_tenant(tenant_id)
        out: list[IdentitySourceResponse] = []
        for source in sources:
            out.append(await self._source_to_response(tenant_id, source))
        return out

    async def update_identity_source(
        self,
        tenant_id: int,
        source_id: int,
        request: UpdateIdentitySourceRequest,
    ) -> IdentitySourceResponse:
        validate_policy(request.bind_policy)
        source = await self.source_repo.get_by_id(tenant_id, source_id)
        if not source:
            raise ResourceNotFoundError("Identity source not found")
        source = await self.source_repo.update_bind_policy(tenant_id, source_id, request.bind_policy)
        return await self._source_to_response(tenant_id, source)

    async def list_pending(self, tenant_id: int) -> list[PendingIdentityResponse]:
        rows = await self.identity_repo.list_pending_identities(tenant_id)
        out: list[PendingIdentityResponse] = []
        for row in rows:
            source = await self.source_repo.get_by_id(tenant_id, row.identity_source_id)
            out.append(self._identity_to_response(row, source))
        return out

    async def approve_pending(self, tenant_id: int, identity_id: int) -> PendingIdentityResponse:
        identity = await self.identity_repo.get_identity(tenant_id, identity_id)
        if not identity:
            raise ResourceNotFoundError("Pending identity not found")
        if identity.status != STATUS_PENDING:
            raise ValidationError("Identity is not pending", {"code": "IDENTITY_NOT_PENDING"})

        user_id = identity.user_id
        if user_id is None and identity.email:
            members = await self.identity_repo.count_members_by_email(tenant_id, identity.email)
            if len(members) == 1:
                user_id = members[0].id
        if user_id is None:
            user_repo = UserRepository(self.db)
            user = await user_repo.create_jit_member(
                tenant_id=tenant_id,
                email=identity.email,
                display_name=identity.display_name,
            )
            user_id = user.id

        await self.binding_service.approve_pending(
            tenant_id=tenant_id,
            identity_id=identity_id,
            user_id=user_id,
        )
        updated = await self.identity_repo.get_identity(tenant_id, identity_id)
        source = await self.source_repo.get_by_id(tenant_id, updated.identity_source_id)
        return self._identity_to_response(updated, source)

    async def reject_pending(self, tenant_id: int, identity_id: int) -> PendingIdentityResponse:
        await self.binding_service.reject_pending(tenant_id=tenant_id, identity_id=identity_id)
        updated = await self.identity_repo.get_identity(tenant_id, identity_id)
        if not updated:
            raise ResourceNotFoundError("Pending identity not found")
        source = await self.source_repo.get_by_id(tenant_id, updated.identity_source_id)
        return self._identity_to_response(updated, source)

    async def _source_to_response(self, tenant_id: int, source) -> IdentitySourceResponse:
        provider_id = (
            await self.db.execute(
                select(AuthProvider.id).where(
                    AuthProvider.tenant_id == tenant_id,
                    AuthProvider.identity_source_id == source.id,
                )
            )
        ).scalar_one_or_none()
        endpoint_count = (
            await self.db.execute(
                select(func.count())
                .select_from(AgentIngressEndpoint)
                .where(
                    AgentIngressEndpoint.tenant_id == tenant_id,
                    AgentIngressEndpoint.identity_source_id == source.id,
                )
            )
        ).scalar_one()
        return IdentitySourceResponse(
            id=source.id,
            tenant_id=source.tenant_id,
            source_kind=source.source_kind,
            source_key=source.source_key,
            display_name=source.display_name,
            bind_policy=source.bind_policy,
            linked_auth_provider_id=provider_id,
            linked_slack_endpoint_count=int(endpoint_count or 0),
        )

    def _identity_to_response(self, identity, source) -> PendingIdentityResponse:
        return PendingIdentityResponse(
            id=identity.id,
            tenant_id=identity.tenant_id,
            provider_id=identity.identity_source_id,
            provider_display_name=source.display_name if source else "",
            external_subject=identity.external_subject,
            email=identity.email,
            display_name=identity.display_name,
            status=identity.status,
            created_at=identity.created_at.isoformat(),
        )
