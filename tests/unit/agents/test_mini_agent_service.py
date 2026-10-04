"""Unit tests for MiniAgentService capability methods."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.schemas.tenant import LLMDefaultsDTO, TenantConfigDTO, TenantDTO
from apps.tenant_app_service.agents.mini_agent import MiniAgentService


@pytest.fixture
def mini_agent_service():
    """Create a MiniAgentService with mocked DB and get_current_tenant."""
    mock_db = MagicMock()
    service = MiniAgentService.create(mock_db, tenant_id=1)

    # Mock get_current_tenant to avoid DB lookup
    service.get_current_tenant = AsyncMock(
        return_value=MagicMock(
            id=1,
            name="test_tenant",
            config=TenantConfigDTO(
                llm_defaults=LLMDefaultsDTO(
                    agent_profile_id=1,
                    mini_agent_profile_id=2,
                    embedding_profile_id=3,
                ),
            ),
        )
    )

    return service


class TestMiniAgentService:
    """Test MiniAgentService capability methods."""

    def test_service_creation(self):
        """Test creating MiniAgentService instance."""
        mock_db = MagicMock()
        service = MiniAgentService.create(mock_db, tenant_id=1)

        assert service.tenant_id == 1
        assert service.db is mock_db
        assert service.executor is not None

    @pytest.mark.asyncio
    async def test_generate_table_metadata(self, mini_agent_service):
        """Test table metadata generation."""
        # Mock executor to return metadata
        metadata_response = {
            "table_description": "Users table with authentication data",
            "column_descriptions": {
                "id": "Primary key",
                "email": "User email address",
                "name": "User display name",
                "created_at": "Account creation timestamp",
            },
            "suggested_tags": ["authentication", "users", "core"],
        }

        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(
            return_value=MagicMock(
                success=True,
                structured_data=metadata_response,
            )
        )

        mini_agent_service.executor = mock_executor

        # Execute - use simple parameters
        result = await mini_agent_service.generate_table_metadata(
            table_name="users",
            columns=[
                {"name": "id", "type": "int"},
                {"name": "email", "type": "varchar"},
                {"name": "name", "type": "varchar"},
                {"name": "created_at", "type": "timestamp"},
            ],
            sample_data=[
                {
                    "id": 1,
                    "email": "user1@example.com",
                    "name": "Alice",
                    "created_at": "2024-01-01",
                },
                {
                    "id": 2,
                    "email": "user2@example.com",
                    "name": "Bob",
                    "created_at": "2024-01-02",
                },
            ],
        )

        # Verify
        assert result["table_description"] is not None
        assert "id" in result["column_descriptions"]
        assert len(result["suggested_tags"]) > 0

    @pytest.mark.asyncio
    async def test_classify_content(self, mini_agent_service):
        """Test content classification."""
        # Mock executor to return classification
        classification_response = {
            "category": "urgent",
            "confidence": 0.95,
            "reasoning": "Contains priority keywords like 'urgent' and 'critical'",
        }

        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(
            return_value=MagicMock(
                success=True,
                structured_data=classification_response,
            )
        )

        mini_agent_service.executor = mock_executor

        # Execute - use simple parameters
        result = await mini_agent_service.classify_content(
            content="This is an urgent request that needs critical attention.",
            categories=["routine", "normal", "urgent", "critical"],
        )

        # Verify
        assert result["category"] == "urgent"
        assert result["confidence"] == 0.95
        assert "urgent" in result["reasoning"].lower()

    @pytest.mark.asyncio
    async def test_classify_content_invalid_category(self, mini_agent_service):
        """Test classification with invalid category returned."""
        # Mock executor returns a category not in the allowed list
        classification_response = {
            "category": "invalid_category",
            "confidence": 0.5,
            "reasoning": "Some reasoning",
        }

        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(
            return_value=MagicMock(
                success=True,
                structured_data=classification_response,
            )
        )

        mini_agent_service.executor = mock_executor

        result = await mini_agent_service.classify_content(
            content="Test content",
            categories=["urgent", "normal"],
        )

        # Should still succeed but return the invalid category
        # (validation is on input, not output in this case)
        assert result["category"] == "invalid_category"

    @pytest.mark.asyncio
    async def test_service_respects_tenant_isolation(self):
        """Test that service respects tenant isolation."""
        service1 = MiniAgentService.create(MagicMock(), tenant_id=1)
        service2 = MiniAgentService.create(MagicMock(), tenant_id=2)

        # Different services should have different tenant IDs
        assert service1.tenant_id == 1
        assert service2.tenant_id == 2

        # Both should have independent executors
        assert service1.executor is not service2.executor
