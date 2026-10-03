"""LLM configuration router - platform catalog and tenant model registry."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.infra.llm.provider_catalog import get_provider_catalog
from apps.shared.llm_providers.domain import ModelProfileCategory
from apps.shared.llm_providers.dtos import (
    CreateLLMModelProfileRequest,
    CreateLLMProviderRequest,
    LLMDefaultsResponseDTO,
    LLMModelProfileResponseDTO,
    LLMProviderResponseDTO,
    TestModelProfileRequest,
    TestProviderConnectionRequest,
    UpdateLLMDefaultsRequest,
    UpdateLLMModelProfileRequest,
    UpdateLLMProviderRequest,
)
from apps.shared.llm_providers.catalog_dtos import (
    ModelCategory,
    ModelDTO,
    ProviderWithModelsByCategoryDTO,
    ProviderWithModelsDTO,
)
from apps.shared.llm_providers.service import LLMProviderConfigService
from apps.shared.schemas.user import UserDTO

router = APIRouter(prefix="/llm-config", tags=["llm-config"])


@router.get("/providers", response_model=list[ProviderWithModelsDTO])
async def list_llm_providers(
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
):
    """List platform catalog providers and their models."""
    catalog = get_provider_catalog()
    providers = catalog.list_providers()
    return [ProviderWithModelsDTO(**p) for p in providers]


@router.get("/providers/by-category", response_model=list[ProviderWithModelsByCategoryDTO])
async def list_providers_by_category(
    category: ModelCategory,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
):
    """List catalog providers with models filtered by category."""
    catalog = get_provider_catalog()
    providers = catalog.list_providers_by_category(category)
    return [ProviderWithModelsByCategoryDTO(**p) for p in providers]


@router.get("/models", response_model=list[ModelDTO])
async def list_models(
    category: ModelCategory,
    provider: str | None = None,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
):
    """List catalog models filtered by category and optionally by provider."""
    catalog = get_provider_catalog()
    models = catalog.list_models(category=category, provider=provider)
    return [ModelDTO(**m) for m in models]


# ==================== Registry Routes (DB-backed providers & profiles) ====================


def _registry_service(current_user: UserDTO, db: AsyncSession) -> LLMProviderConfigService:
    return LLMProviderConfigService(current_user.tenant_id, db)


@router.get("/registry/providers", response_model=list[LLMProviderResponseDTO])
async def list_registry_providers(
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await _registry_service(current_user, db).list_providers()


@router.post("/registry/providers", response_model=LLMProviderResponseDTO)
async def create_registry_provider(
    request: CreateLLMProviderRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await _registry_service(current_user, db).create_provider(request)


@router.put("/registry/providers/{provider_id}", response_model=LLMProviderResponseDTO)
async def update_registry_provider(
    provider_id: int,
    request: UpdateLLMProviderRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await _registry_service(current_user, db).update_provider(provider_id, request)


@router.delete("/registry/providers/{provider_id}", status_code=204)
async def delete_registry_provider(
    provider_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    await _registry_service(current_user, db).delete_provider(provider_id)


@router.post("/registry/providers/{provider_id}/test")
async def test_registry_provider_connection(
    provider_id: int,
    request: TestProviderConnectionRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    message = await _registry_service(current_user, db).test_provider_connection(
        provider_id,
        api_base=request.api_base,
        model_id=request.model_id,
        api_key=request.api_key,
        category=request.category,
    )
    return {"status": "success", "message": message}


@router.get("/registry/profiles", response_model=list[LLMModelProfileResponseDTO])
async def list_registry_profiles(
    category: ModelProfileCategory | None = None,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await _registry_service(current_user, db).list_profiles(category=category)


@router.post("/registry/profiles", response_model=LLMModelProfileResponseDTO)
async def create_registry_profile(
    request: CreateLLMModelProfileRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await _registry_service(current_user, db).create_profile(request)


@router.put("/registry/profiles/{profile_id}", response_model=LLMModelProfileResponseDTO)
async def update_registry_profile(
    profile_id: int,
    request: UpdateLLMModelProfileRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await _registry_service(current_user, db).update_profile(profile_id, request)


@router.delete("/registry/profiles/{profile_id}", status_code=204)
async def delete_registry_profile(
    profile_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    await _registry_service(current_user, db).delete_profile(profile_id)


@router.post("/registry/profiles/{profile_id}/test")
async def test_registry_profile_connection(
    profile_id: int,
    request: TestModelProfileRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    message = await _registry_service(current_user, db).test_profile_connection(profile_id, request.api_key)
    return {"status": "success", "message": message}


@router.get("/registry/defaults", response_model=LLMDefaultsResponseDTO)
async def get_registry_defaults(
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await _registry_service(current_user, db).get_defaults()


@router.put("/registry/defaults", response_model=LLMDefaultsResponseDTO)
async def update_registry_defaults(
    request: UpdateLLMDefaultsRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await _registry_service(current_user, db).update_defaults(request)
