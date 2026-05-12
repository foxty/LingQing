"""ABAC policy management service."""

from apps.shared.authz.adapters import db_abac_policy_to_domain
from apps.shared.authz.domain import AbacPolicyDomain
from apps.shared.authz.dsl import DslParseError, DslValidationError, build_attr_registry, parse_dsl, validate_expr
from apps.shared.authz.repository import AbacPolicyRepository
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.core.transaction import transaction
from apps.shared.db.models import AbacPolicy
from apps.shared.domain.types import AbacAction, ResourceType


class AbacPolicyService(TenantAwareService):
    """ABAC policy management."""

    def __init__(self, tenant_id: int, policy_repo: AbacPolicyRepository):
        super().__init__(tenant_id)
        self.policy_repo = policy_repo

    @classmethod
    def create(cls, tenant_id: int, db_session) -> "AbacPolicyService":
        return cls(tenant_id=tenant_id, policy_repo=AbacPolicyRepository(db_session))

    async def list_policies(
        self,
        resource_type: ResourceType | None = None,
        action: AbacAction | None = None,
    ) -> list[AbacPolicyDomain]:
        if resource_type and action:
            policies = await self.policy_repo.list_by_resource_type_and_action(self.tenant_id, resource_type, action)
        elif resource_type:
            policies = await self.policy_repo.list_by_resource_type(self.tenant_id, resource_type)
        else:
            policies = await self.policy_repo.list_by_tenant(self.tenant_id)
        return [db_abac_policy_to_domain(policy) for policy in policies]

    async def get_policy(self, policy_id: int) -> AbacPolicyDomain | None:
        policy = await self.policy_repo.get_by_id_and_tenant(self.tenant_id, policy_id)
        return db_abac_policy_to_domain(policy) if policy else None

    async def simulate_policy(
        self,
        expression: str,
        resource_type: ResourceType,
        action: AbacAction,
        user_id: int,
        user_role: str | None,
        resource_id: int,
    ) -> tuple[bool, str]:
        """Dry-run evaluate a single DSL expression against real DB tags."""
        from apps.shared.authz.authz_query_builder import evaluate_single_expression

        self._validate_policy_expression(expression)
        return await evaluate_single_expression(
            db_session=self.policy_repo.db,
            tenant_id=self.tenant_id,
            user_id=user_id,
            user_role=user_role,
            resource_type=resource_type,
            action=action,
            resource_id=resource_id,
            expression=expression,
        )

    def _validate_policy_expression(self, expression: str) -> None:
        if not isinstance(expression, str) or not expression.strip():
            raise ValidationError("Policy expression must be a non-empty DSL string.")
        try:
            parsed = parse_dsl(expression)
            registry = build_attr_registry({"resource.id", "resource.owner_id"})
            validate_expr(parsed, registry)
        except (DslParseError, DslValidationError) as exc:
            raise ValidationError(f"Policy expression invalid: {exc}") from exc

    async def _get_policy_or_404(self, policy_id: int) -> AbacPolicy:
        policy = await self.policy_repo.get_by_id_and_tenant(self.tenant_id, policy_id)
        if not policy:
            raise ResourceNotFoundError(f"Policy not found: {policy_id}")
        return policy

    @transaction
    async def create_policy(
        self,
        name: str,
        description: str | None,
        resource_type: ResourceType,
        action: AbacAction,
        expression: str,
        created_by: int | None,
    ) -> AbacPolicyDomain:
        self._validate_policy_expression(expression)
        policy = AbacPolicy(
            tenant_id=self.tenant_id,
            name=name,
            description=description,
            resource_type=resource_type,
            action=action,
            expression=expression,
            status="active",
            created_by=created_by,
            updated_by=created_by,
        )
        policy = await self.policy_repo.create(policy)
        return db_abac_policy_to_domain(policy)

    @transaction
    async def update_policy(
        self,
        policy_id: int,
        name: str | None,
        description: str | None,
        resource_type: ResourceType | None,
        action: AbacAction | None,
        expression: str | None,
        updated_by: int | None,
    ) -> AbacPolicyDomain:
        policy = await self._get_policy_or_404(policy_id)
        if expression is not None:
            self._validate_policy_expression(expression)
            policy.expression = expression
        if name is not None:
            policy.name = name
        if description is not None:
            policy.description = description
        if resource_type is not None:
            policy.resource_type = resource_type
        if action is not None:
            policy.action = action
        policy.updated_by = updated_by
        policy = await self.policy_repo.update(policy)
        return db_abac_policy_to_domain(policy)

    @transaction
    async def disable_policy(self, policy_id: int, updated_by: int | None) -> AbacPolicyDomain:
        policy = await self._get_policy_or_404(policy_id)
        policy.status = "disabled"
        policy.updated_by = updated_by
        policy = await self.policy_repo.update(policy)
        return db_abac_policy_to_domain(policy)

    @transaction
    async def enable_policy(self, policy_id: int, updated_by: int | None) -> AbacPolicyDomain:
        policy = await self._get_policy_or_404(policy_id)
        policy.status = "active"
        policy.updated_by = updated_by
        policy = await self.policy_repo.update(policy)
        return db_abac_policy_to_domain(policy)

    @transaction
    async def delete_policy(self, policy_id: int) -> None:
        policy = await self._get_policy_or_404(policy_id)
        await self.policy_repo.delete(policy)
