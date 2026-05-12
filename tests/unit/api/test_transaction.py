"""Tests for transaction decorator and context manager."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.transaction import (
    TransactionManager,
    transaction,
    transaction_context,
)

# Configure pytest to use asyncio for async tests
pytestmark = pytest.mark.asyncio


class MockRepository:
    """Mock repository for testing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict):
        return {"id": 1, **data}


class MockService:
    """Mock service for testing decorator on service methods."""

    def __init__(self, data_source_repo: MockRepository):
        self.data_source_repo = data_source_repo

    @transaction
    async def create_with_success(self, name: str):
        """Method that succeeds."""
        return await self.data_source_repo.create({"name": name})

    @transaction
    async def create_with_failure(self, name: str):
        """Method that raises exception."""
        await self.data_source_repo.create({"name": name})
        raise ValueError("Simulated error")


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


async def test_transaction_context_manager_success(mock_db):
    """Test transaction as context manager with success."""
    async with transaction(mock_db):
        # Simulate database operations
        pass

    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()


async def test_transaction_context_manager_failure(mock_db):
    """Test transaction as context manager with exception."""
    with pytest.raises(ValueError):
        async with transaction(mock_db):
            raise ValueError("Test error")

    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()


async def test_transaction_decorator_on_service_method_success(mock_db):
    """Test transaction decorator on service method with success."""
    repo = MockRepository(mock_db)
    service = MockService(repo)

    result = await service.create_with_success("test")

    assert result == {"id": 1, "name": "test"}
    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()


async def test_transaction_decorator_on_service_method_failure(mock_db):
    """Test transaction decorator on service method with exception."""
    repo = MockRepository(mock_db)
    service = MockService(repo)

    with pytest.raises(ValueError, match="Simulated error"):
        await service.create_with_failure("test")

    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()


async def test_transaction_decorator_on_router_handler(mock_db):
    """Test transaction decorator on router handler."""

    @transaction
    async def mock_handler(request: dict, db: AsyncSession):
        return {"status": "ok"}

    result = await mock_handler({"data": "test"}, db=mock_db)

    assert result == {"status": "ok"}
    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()


async def test_transaction_decorator_on_router_handler_with_failure(mock_db):
    """Test transaction decorator on router handler with exception."""

    @transaction
    async def mock_handler(request: dict, db: AsyncSession):
        raise RuntimeError("Handler error")

    with pytest.raises(RuntimeError, match="Handler error"):
        await mock_handler({"data": "test"}, db=mock_db)

    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()


async def test_transaction_context_function_success(mock_db):
    """Test transaction_context helper function."""
    async with transaction_context(mock_db):
        # Simulate operations
        pass

    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()


async def test_transaction_context_function_failure(mock_db):
    """Test transaction_context helper function with exception."""
    with pytest.raises(ValueError):
        async with transaction_context(mock_db):
            raise ValueError("Context error")

    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()


async def test_transaction_decorator_without_db_raises_error():
    """Test that decorator raises error when db session cannot be found."""

    @transaction
    async def invalid_function(data: str):
        return data

    with pytest.raises(ValueError, match="Cannot find AsyncSession"):
        await invalid_function("test")


async def test_transaction_manager_class(mock_db):
    """Test TransactionManager class directly."""
    manager = TransactionManager(mock_db)

    # Test successful transaction
    async with manager:
        pass

    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()

    # Reset mocks
    mock_db.reset_mock()

    # Test failed transaction
    with pytest.raises(RuntimeError):
        async with manager:
            raise RuntimeError("Manager error")

    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()
