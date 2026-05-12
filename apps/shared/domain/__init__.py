"""Domain models for business logic layer.

This package contains pure domain models that are independent of:
- HTTP/API frameworks (FastAPI, Pydantic request/response schemas)
- Database frameworks (SQLAlchemy ORM models)
- External libraries

Domain models represent business entities and contain business logic only.
They are used exclusively in the Service layer.

Domain models have been moved to their respective domain modules:
- BaseDomainModel -> apps.shared.domain.models
- TenantDomain -> apps.tenant_app_service.tenant.domain
- UserDomain -> apps.tenant_app_service.auth.domain
- CustomAgent -> apps.tenant_app_service.agent_catalog.domain
- DocumentDomain -> apps.shared.document.domain
- DataSourceDomain, AssetMetadataDomain -> apps.shared.data_source.domain
- MessageDomain, ConversationDomain -> apps.chat_backend.chat.domain

Import them directly from their respective modules to avoid circular dependencies.
"""

from apps.shared.domain.actor import ActorContext
from apps.shared.domain.base_domain_model import BaseDomainModel

__all__ = [
    "BaseDomainModel",
    "ActorContext",
]
