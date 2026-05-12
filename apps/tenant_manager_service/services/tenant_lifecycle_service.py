"""Tenant lifecycle application service."""

from uuid import uuid4

from apps.shared.core.exceptions import DuplicateResourceError, ResourceNotFoundError, ValidationError
from apps.tenant_manager_service.repositories.tenant_repository import TenantManagerRepository


class TenantLifecycleService:
    """Application service for P0 tenant lifecycle."""

    VALID_TRANSITIONS: dict[str, set[str]] = {
        "provisioning": {"active"},
        "active": {"locked"},
        "locked": {"active"},
    }

    def __init__(self, repository: TenantManagerRepository):
        self.repository = repository

    async def create_tenant(
        self, tenant_code: str, display_name: str, actor_id: str | None, request_id: str | None, ip: str | None
    ):
        existing = await self.repository.get_tenant_by_code(tenant_code)
        if existing:
            raise DuplicateResourceError("Tenant code already exists", {"tenant_code": tenant_code})

        tenant_uid = str(uuid4())
        tenant = await self.repository.create_tenant(
            tenant_uid=tenant_uid,
            tenant_code=tenant_code,
            display_name=display_name,
        )
        await self.repository.add_lifecycle_event(
            tenant_uid=tenant.tenant_uid,
            event_type="create",
            from_status=None,
            to_status=tenant.status,
            operator_id=actor_id,
            reason_code=None,
            event_metadata={"tenant_code": tenant_code},
        )
        await self.repository.add_audit_log(
            tenant_uid=tenant.tenant_uid,
            actor_id=actor_id,
            action="tenant.create",
            resource_type="tenant",
            resource_id=tenant.tenant_uid,
            request_id=request_id,
            ip=ip,
            before_snapshot=None,
            after_snapshot={
                "tenant_uid": tenant.tenant_uid,
                "status": tenant.status,
                "tenant_code": tenant.tenant_code,
                "display_name": tenant.display_name,
            },
        )
        return tenant

    async def list_tenants(self):
        return await self.repository.list_tenants()

    async def get_tenant(self, tenant_uid: str):
        tenant = await self.repository.get_tenant_by_uid(tenant_uid)
        if not tenant:
            raise ResourceNotFoundError("Tenant not found", {"tenant_uid": tenant_uid})
        return tenant

    async def list_lifecycle_events(self, tenant_uid: str):
        await self.get_tenant(tenant_uid)
        return await self.repository.list_lifecycle_events(tenant_uid)

    async def provision_tenant(
        self, tenant_uid: str, actor_id: str | None, reason_code: str | None, request_id: str | None, ip: str | None
    ):
        return await self._change_status(
            tenant_uid=tenant_uid,
            target_status="active",
            event_type="provision",
            actor_id=actor_id,
            reason_code=reason_code,
            request_id=request_id,
            ip=ip,
            action="tenant.provision",
        )

    async def lock_tenant(
        self, tenant_uid: str, actor_id: str | None, reason_code: str | None, request_id: str | None, ip: str | None
    ):
        return await self._change_status(
            tenant_uid=tenant_uid,
            target_status="locked",
            event_type="lock",
            actor_id=actor_id,
            reason_code=reason_code,
            request_id=request_id,
            ip=ip,
            action="tenant.lock",
        )

    async def unlock_tenant(
        self, tenant_uid: str, actor_id: str | None, reason_code: str | None, request_id: str | None, ip: str | None
    ):
        return await self._change_status(
            tenant_uid=tenant_uid,
            target_status="active",
            event_type="unlock",
            actor_id=actor_id,
            reason_code=reason_code,
            request_id=request_id,
            ip=ip,
            action="tenant.unlock",
        )

    async def _change_status(
        self,
        tenant_uid: str,
        target_status: str,
        event_type: str,
        actor_id: str | None,
        reason_code: str | None,
        request_id: str | None,
        ip: str | None,
        action: str,
    ):
        tenant = await self.get_tenant(tenant_uid)
        current_status = tenant.status
        allowed = self.VALID_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise ValidationError(
                "Invalid tenant status transition",
                {
                    "tenant_uid": tenant_uid,
                    "from_status": current_status,
                    "to_status": target_status,
                },
            )

        before_snapshot = {
            "status": current_status,
            "tenant_uid": tenant.tenant_uid,
        }
        tenant = await self.repository.update_tenant_status(tenant, target_status)
        await self.repository.add_lifecycle_event(
            tenant_uid=tenant_uid,
            event_type=event_type,
            from_status=current_status,
            to_status=target_status,
            operator_id=actor_id,
            reason_code=reason_code,
            event_metadata=None,
        )
        await self.repository.add_audit_log(
            tenant_uid=tenant.tenant_uid,
            actor_id=actor_id,
            action=action,
            resource_type="tenant",
            resource_id=tenant.tenant_uid,
            request_id=request_id,
            ip=ip,
            before_snapshot=before_snapshot,
            after_snapshot={"status": target_status, "tenant_uid": tenant.tenant_uid},
        )
        return tenant
