"""Tag services (read-only and management)."""

from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import DuplicateResourceError, ResourceNotFoundError, ValidationError
from apps.shared.core.transaction import transaction
from apps.shared.db.models import ResourceTagConfig, TagBinding, TagKey, TagValue
from apps.shared.domain.types import ResourceType
from apps.shared.tag.adapters import (
    db_resource_tag_config_to_domain,
    db_tag_key_to_domain,
    db_tag_value_to_domain,
)
from apps.shared.tag.domain import ResourceTagConfigDomain, TagKeyDomain, TagValueDomain
from apps.shared.tag.repository import (
    ResourceTagConfigRepository,
    TagBindingRepository,
    TagKeyRepository,
    TagValueRepository,
)
from apps.shared.tag.types import TagValueMode


class TagService(TenantAwareService):
    """Tag service (read + management)."""

    def __init__(
        self,
        tenant_id: int,
        tag_key_repo: TagKeyRepository,
        tag_value_repo: TagValueRepository,
        tag_binding_repo: TagBindingRepository,
        resource_tag_repo: ResourceTagConfigRepository,
    ):
        super().__init__(tenant_id)
        self.tag_key_repo = tag_key_repo
        self.tag_value_repo = tag_value_repo
        self.tag_binding_repo = tag_binding_repo
        self.resource_tag_repo = resource_tag_repo

    @classmethod
    def create(cls, tenant_id: int, db_session) -> "TagService":
        return cls(
            tenant_id=tenant_id,
            tag_key_repo=TagKeyRepository(db_session),
            tag_value_repo=TagValueRepository(db_session),
            tag_binding_repo=TagBindingRepository(db_session),
            resource_tag_repo=ResourceTagConfigRepository(db_session),
        )

    async def list_tag_keys(self) -> list[TagKeyDomain]:
        tag_keys = await self.tag_key_repo.list_by_tenant(self.tenant_id)
        return [db_tag_key_to_domain(tag_key) for tag_key in tag_keys]

    async def get_tag_key(self, tag_key_id: int) -> TagKeyDomain | None:
        tag_key = await self.tag_key_repo.get_by_id_and_tenant(self.tenant_id, tag_key_id)
        return db_tag_key_to_domain(tag_key) if tag_key else None

    async def list_tag_values(self, key_id: int | None = None) -> list[TagValueDomain]:
        if key_id is None:
            tag_values = await self.tag_value_repo.list_by_tenant(self.tenant_id)
        else:
            tag_values = await self.tag_value_repo.list_by_key(self.tenant_id, key_id)
        return [db_tag_value_to_domain(tag_value) for tag_value in tag_values]

    async def get_tag_value(self, tag_value_id: int) -> TagValueDomain | None:
        tag_value = await self.tag_value_repo.get_by_id_and_tenant(self.tenant_id, tag_value_id)
        return db_tag_value_to_domain(tag_value) if tag_value else None

    async def list_tags_for_resource(self, resource_type: ResourceType, resource_id: int) -> list[TagValueDomain]:
        tag_values = await self.tag_binding_repo.list_tag_values_by_resource(
            tenant_id=self.tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return [db_tag_value_to_domain(tag_value) for tag_value in tag_values]

    async def list_resource_tag_configs(
        self, resource_type: ResourceType | None = None
    ) -> list[ResourceTagConfigDomain]:
        if resource_type:
            resource_tags = await self.resource_tag_repo.list_by_resource_type(self.tenant_id, resource_type)
        else:
            resource_tags = await self.resource_tag_repo.list_by_tenant(self.tenant_id)
        return [db_resource_tag_config_to_domain(resource_tag) for resource_tag in resource_tags]

    async def get_resource_tag_config(self, config_id: int) -> ResourceTagConfigDomain | None:
        resource_tag = await self.resource_tag_repo.get_by_id_and_tenant(self.tenant_id, config_id)
        return db_resource_tag_config_to_domain(resource_tag) if resource_tag else None

    async def _ensure_tag_key_unique(self, tag_key_id: int | None, name: str) -> None:
        existing = await self.tag_key_repo.get_by_name(self.tenant_id, name)
        if existing and (tag_key_id is None or existing.id != tag_key_id):
            raise DuplicateResourceError(f"TagKey name already exists: {name}")

    async def _ensure_tag_value_unique(self, tag_value_id: int | None, key_id: int, value: str) -> None:
        existing_values = await self.tag_value_repo.list_by_key(self.tenant_id, key_id)
        for existing in existing_values:
            if existing.value == value and (tag_value_id is None or existing.id != tag_value_id):
                raise DuplicateResourceError(f"TagValue already exists: {value}")

    async def _ensure_tag_value_rank_unique(
        self,
        tag_value_id: int | None,
        key_id: int,
        rank: int | None,
    ) -> None:
        if rank is None:
            return
        if rank <= 0:
            raise ValidationError("TagValue rank must be a positive integer.")
        existing = await self.tag_value_repo.get_by_key_and_rank(self.tenant_id, key_id, rank)
        if existing and (tag_value_id is None or existing.id != tag_value_id):
            raise DuplicateResourceError(f"TagValue rank already exists under this key: {rank}")

    async def _get_tag_key_or_404(self, tag_key_id: int):
        tag_key = await self.tag_key_repo.get_by_id_and_tenant(self.tenant_id, tag_key_id)
        if not tag_key:
            raise ResourceNotFoundError(f"TagKey not found: {tag_key_id}")
        return tag_key

    async def _get_resource_tag_config_or_404(self, config_id: int) -> ResourceTagConfig:
        resource_tag = await self.resource_tag_repo.get_by_id_and_tenant(self.tenant_id, config_id)
        if not resource_tag:
            raise ResourceNotFoundError(f"ResourceTagConfig not found: {config_id}")
        return resource_tag

    async def _get_tag_value_or_404(self, tag_value_id: int):
        tag_value = await self.tag_value_repo.get_by_id_and_tenant(self.tenant_id, tag_value_id)
        if not tag_value:
            raise ResourceNotFoundError(f"TagValue not found: {tag_value_id}")
        return tag_value

    @transaction
    async def create_tag_key(
        self,
        name: str,
        description: str | None,
        color: str | None,
        created_by: int | None,
    ) -> TagKeyDomain:
        await self._ensure_tag_key_unique(None, name)

        tag_key = TagKey(
            tenant_id=self.tenant_id,
            name=name,
            description=description,
            color=color,
            status="active",
            created_by=created_by,
            updated_by=created_by,
        )
        tag_key = await self.tag_key_repo.create(tag_key)
        return db_tag_key_to_domain(tag_key)

    @transaction
    async def update_tag_key(
        self,
        tag_key_id: int,
        name: str | None,
        description: str | None,
        color: str | None,
        updated_by: int | None,
    ) -> TagKeyDomain:
        tag_key = await self._get_tag_key_or_404(tag_key_id)

        new_name = name or tag_key.name

        await self._ensure_tag_key_unique(tag_key_id, new_name)

        tag_key.name = new_name
        tag_key.description = description if description is not None else tag_key.description
        tag_key.color = color if color is not None else tag_key.color
        tag_key.updated_by = updated_by

        tag_key = await self.tag_key_repo.update(tag_key)
        return db_tag_key_to_domain(tag_key)

    @transaction
    async def disable_tag_key(self, tag_key_id: int, updated_by: int | None) -> TagKeyDomain:
        tag_key = await self._get_tag_key_or_404(tag_key_id)
        tag_key.status = "disabled"
        tag_key.updated_by = updated_by
        tag_key = await self.tag_key_repo.update(tag_key)
        return db_tag_key_to_domain(tag_key)

    @transaction
    async def enable_tag_key(self, tag_key_id: int, updated_by: int | None) -> TagKeyDomain:
        tag_key = await self._get_tag_key_or_404(tag_key_id)
        tag_key.status = "active"
        tag_key.updated_by = updated_by
        tag_key = await self.tag_key_repo.update(tag_key)
        return db_tag_key_to_domain(tag_key)

    @transaction
    async def delete_tag_key(self, tag_key_id: int) -> None:
        tag_key = await self._get_tag_key_or_404(tag_key_id)
        tag_values = await self.tag_value_repo.list_by_key(self.tenant_id, tag_key_id)
        if tag_values:
            raise ValidationError("TagKey is in use and cannot be deleted.")
        await self.tag_key_repo.delete(tag_key)

    @transaction
    async def create_tag_value(
        self,
        key_id: int,
        value: str,
        rank: int | None,
        created_by: int | None,
    ) -> TagValueDomain:
        await self._get_tag_key_or_404(key_id)

        await self._ensure_tag_value_unique(None, key_id, value)
        await self._ensure_tag_value_rank_unique(None, key_id, rank)

        tag_value = TagValue(
            tenant_id=self.tenant_id,
            key_id=key_id,
            value=value,
            rank=rank,
            status="active",
            created_by=created_by,
            updated_by=created_by,
        )
        tag_value = await self.tag_value_repo.create(tag_value)
        return db_tag_value_to_domain(tag_value)

    @transaction
    async def update_tag_value(
        self,
        tag_value_id: int,
        value: str | None,
        rank: int | None,
        rank_provided: bool,
        updated_by: int | None,
    ) -> TagValueDomain:
        tag_value = await self._get_tag_value_or_404(tag_value_id)
        new_value = value or tag_value.value
        new_rank = rank if rank_provided else tag_value.rank

        await self._ensure_tag_value_unique(tag_value_id, tag_value.key_id, new_value)
        await self._ensure_tag_value_rank_unique(tag_value_id, tag_value.key_id, new_rank)

        tag_value.value = new_value
        tag_value.rank = new_rank
        tag_value.updated_by = updated_by
        tag_value = await self.tag_value_repo.update(tag_value)
        return db_tag_value_to_domain(tag_value)

    @transaction
    async def disable_tag_value(self, tag_value_id: int, updated_by: int | None) -> TagValueDomain:
        tag_value = await self._get_tag_value_or_404(tag_value_id)
        tag_value.status = "disabled"
        tag_value.updated_by = updated_by
        tag_value = await self.tag_value_repo.update(tag_value)
        return db_tag_value_to_domain(tag_value)

    @transaction
    async def enable_tag_value(self, tag_value_id: int, updated_by: int | None) -> TagValueDomain:
        tag_value = await self._get_tag_value_or_404(tag_value_id)
        tag_value.status = "active"
        tag_value.updated_by = updated_by
        tag_value = await self.tag_value_repo.update(tag_value)
        return db_tag_value_to_domain(tag_value)

    @transaction
    async def delete_tag_value(self, tag_value_id: int) -> None:
        tag_value = await self._get_tag_value_or_404(tag_value_id)
        bindings = await self.tag_binding_repo.list_by_tag_value(self.tenant_id, tag_value_id)
        if bindings:
            raise ValidationError(
                f"TagValue ({tag_value.id}) is in use by {len(bindings)} resource(s) and cannot be deleted."
            )
        await self.tag_value_repo.delete(tag_value)

    @transaction
    async def bind_tag_value(
        self,
        resource_type: ResourceType,
        resource_id: int,
        tag_value_id: int,
        created_by: int | None,
    ) -> TagValueDomain:
        tag_value = await self._get_tag_value_or_404(tag_value_id)
        if tag_value.status != "active":
            raise ValidationError("TagValue is disabled and cannot be bound.")

        tag_key = await self._get_tag_key_or_404(tag_value.key_id)
        if tag_key.status != "active":
            raise ValidationError("TagKey is disabled and cannot be bound.")

        whitelist = await self.resource_tag_repo.get_by_resource_and_key(
            self.tenant_id,
            resource_type,
            tag_key.id,
        )
        if not whitelist:
            raise ValidationError("TagKey is not allowed for this resource type.")

        existing = await self.tag_binding_repo.get_by_resource_and_tag_value(
            tenant_id=self.tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            tag_value_id=tag_value_id,
        )
        if existing:
            return db_tag_value_to_domain(tag_value)

        if whitelist.value_mode is None:
            raise ValidationError("ResourceTagConfig value_mode must be set.")

        if whitelist.value_mode == "exclusive":
            existing_for_key = await self.tag_binding_repo.list_by_resource_and_key(
                tenant_id=self.tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
                tag_key_id=tag_key.id,
            )
            for binding in existing_for_key:
                await self.tag_binding_repo.delete(binding)

        tag_binding = TagBinding(
            tenant_id=self.tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            tag_value_id=tag_value_id,
            created_by=created_by,
        )
        await self.tag_binding_repo.create(tag_binding)
        return db_tag_value_to_domain(tag_value)

    @transaction
    async def unbind_tag_value(
        self,
        resource_type: ResourceType,
        resource_id: int,
        tag_value_id: int,
    ) -> None:
        binding = await self.tag_binding_repo.get_by_resource_and_tag_value(
            tenant_id=self.tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            tag_value_id=tag_value_id,
        )
        if not binding:
            raise ResourceNotFoundError("TagBinding not found.")
        await self.tag_binding_repo.delete(binding)

    @transaction
    async def create_resource_tag_config(
        self,
        resource_type: ResourceType,
        tag_key_id: int,
        value_mode: TagValueMode,
        created_by: int | None,
    ) -> ResourceTagConfigDomain:
        if value_mode not in {"inclusive", "exclusive"}:
            raise ValidationError("ResourceTagConfig value_mode must be 'inclusive' or 'exclusive'.")

        tag_key = await self._get_tag_key_or_404(tag_key_id)
        if tag_key.status != "active":
            raise ValidationError("TagKey is disabled and cannot be used in whitelist.")

        existing = await self.resource_tag_repo.get_by_resource_and_key(
            self.tenant_id,
            resource_type,
            tag_key_id,
        )
        if existing:
            raise DuplicateResourceError("ResourceTagConfig already exists.")

        resource_tag = ResourceTagConfig(
            tenant_id=self.tenant_id,
            resource_type=resource_type,
            tag_key_id=tag_key_id,
            value_mode=value_mode,
            created_by=created_by,
        )
        resource_tag = await self.resource_tag_repo.create(resource_tag)
        return db_resource_tag_config_to_domain(resource_tag)

    @transaction
    async def update_resource_tag_config(
        self,
        config_id: int,
        value_mode: TagValueMode,
    ) -> ResourceTagConfigDomain:
        if value_mode not in {"inclusive", "exclusive"}:
            raise ValidationError("ResourceTagConfig value_mode must be 'inclusive' or 'exclusive'.")

        resource_tag = await self._get_resource_tag_config_or_404(config_id)
        resource_tag.value_mode = value_mode
        resource_tag = await self.resource_tag_repo.update(resource_tag)
        return db_resource_tag_config_to_domain(resource_tag)

    @transaction
    async def delete_resource_tag_config(self, config_id: int) -> None:
        resource_tag = await self._get_resource_tag_config_or_404(config_id)
        await self.resource_tag_repo.delete(resource_tag)
