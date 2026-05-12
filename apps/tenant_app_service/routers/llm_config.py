"""LLM/Embedding Configuration router - tenant-scoped model configuration."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.infra.llm.model_registry import get_model_registry
from apps.shared.schemas.model_config import (
    ModelCategory,
    ModelConfigDTO,
    ModelDTO,
    ProviderWithModelsByCategoryDTO,
    ProviderWithModelsDTO,
    TenantEmbeddingConfigDTO,
    TenantEmbeddingConfigResponseDTO,
    TenantLLMConfigDTO,
    TenantLLMConfigResponseDTO,
)
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.tenant.tenant_model_config_service import TenantModelConfigService

router = APIRouter(prefix="/llm-config", tags=["llm-config"])


class TestConnectionRequest(BaseModel):
    """Request body for testing LLM connection."""

    api_base: str
    model_id: str
    api_key: str = ""


class TestEmbeddingConnectionRequest(BaseModel):
    """Request body for testing Embedding connection."""

    api_base: str
    model_id: str
    api_key: str = ""


@router.get("/providers", response_model=list[ProviderWithModelsDTO])
async def list_llm_providers(
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
):
    """List all available LLM providers and their models."""
    registry = get_model_registry()
    providers = registry.list_providers()
    return [ProviderWithModelsDTO(**p) for p in providers]


@router.get("/providers/by-category", response_model=list[ProviderWithModelsByCategoryDTO])
async def list_providers_by_category(
    category: ModelCategory,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
):
    """List providers with models filtered by category (llm or embedding)."""
    registry = get_model_registry()
    providers = registry.list_providers_by_category(category)
    return [ProviderWithModelsByCategoryDTO(**p) for p in providers]


@router.get("/models", response_model=list[ModelDTO])
async def list_models(
    category: ModelCategory,
    provider: str | None = None,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
):
    """List models filtered by category and optionally by provider."""
    registry = get_model_registry()
    models = registry.list_models(category=category, provider=provider)
    return [ModelDTO(**m) for m in models]


@router.get("/config", response_model=TenantLLMConfigResponseDTO)
async def get_llm_config(
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant's current LLM configuration."""
    service = TenantModelConfigService(current_user.tenant_id, db)
    return await service.get_llm_config()


@router.put("/config", response_model=TenantLLMConfigResponseDTO)
async def update_llm_config(
    config: TenantLLMConfigDTO,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Update tenant's LLM configuration."""
    service = TenantModelConfigService(current_user.tenant_id, db)
    return await service.update_llm_config(config)


@router.post("/test-connection")
async def test_llm_connection(
    request: TestConnectionRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Test LLM connection by making an actual API call."""
    service = TenantModelConfigService(current_user.tenant_id, db)
    message = await service.test_llm_connection(request.api_base, request.model_id, request.api_key)
    return {"status": "success", "message": message}


@router.put("/agent-config", response_model=TenantLLMConfigResponseDTO)
async def update_agent_config(
    config: ModelConfigDTO,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Update only the agent model configuration."""
    service = TenantModelConfigService(current_user.tenant_id, db)
    return await service.update_agent_model(config)


@router.put("/mini-agent-config", response_model=TenantLLMConfigResponseDTO)
async def update_mini_agent_config(
    config: ModelConfigDTO,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Update only the mini agent model configuration."""
    service = TenantModelConfigService(current_user.tenant_id, db)
    return await service.update_mini_agent_model(config)


@router.post("/copy-agent-to-mini", response_model=TenantLLMConfigResponseDTO)
async def copy_agent_to_mini(
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Copy agent model config to mini agent model (including encrypted API key)."""
    service = TenantModelConfigService(current_user.tenant_id, db)
    return await service.copy_agent_to_mini()


# ==================== Embedding Config Routes ====================


@router.get("/embedding-config", response_model=TenantEmbeddingConfigResponseDTO | None)
async def get_embedding_config(
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant's current Embedding configuration.

    Returns None if not yet configured, allowing UI to show default selection.
    """
    service = TenantModelConfigService(current_user.tenant_id, db)
    return await service.get_embedding_config()


@router.put("/embedding-config", response_model=TenantEmbeddingConfigResponseDTO)
async def update_embedding_config(
    config: TenantEmbeddingConfigDTO,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Update tenant's Embedding configuration."""
    service = TenantModelConfigService(current_user.tenant_id, db)
    return await service.update_embedding_config(config)


@router.post("/test-embedding-connection")
async def test_embedding_connection(
    request: TestEmbeddingConnectionRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Test Embedding connection by making an actual API call."""
    from apps.shared.core.exceptions import ValidationError

    service = TenantModelConfigService(current_user.tenant_id, db)
    try:
        message = await service.test_embedding_connection(request.api_base, request.model_id, request.api_key)
        return {"status": "success", "message": message}
    except ValidationError as e:
        raise e
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e))
