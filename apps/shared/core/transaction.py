"""Transaction management decorator and context manager.

This module provides a flexible transaction decorator that can be used:
1. As a function decorator for service methods
2. As a function decorator for router handlers
3. As an async context manager with `async with`

The transaction manager ensures proper ACID transaction boundaries:
- All database operations within the transaction use the same session
- Commit happens ONLY when the transaction completes successfully
- Any exception triggers automatic rollback
- Repositories should use flush() not commit() within transactions

Best Practices:
    Repository Layer:
        - Use `await self.db.flush()` to persist changes within transaction
        - Use `await self.db.refresh(entity)` to get IDs after flush
        - NEVER call `await self.db.commit()` inside repository methods
        - Let @transaction decorator handle commit/rollback

    Service Layer:
        - Apply @transaction decorator to methods that need atomicity
        - Don't pass `auto_commit=True` to repository methods
        - Repository changes are automatically committed on success

    Router Layer:
        - Apply @transaction to handler functions (less common)
        - Or rely on service-level @transaction (preferred)

Usage Examples:
    # 1. Service method decorator (RECOMMENDED)
    @transaction
    async def create_data_source(self, name: str, config: dict):
        source = await self.data_source_repo.create(...)
        await self.asset_repo.create(...)
        # Auto-commit on success, auto-rollback on exception
        return source

    # 2. Router handler decorator
    @router.post("/sources")
    @transaction
    async def create_source(request: Request, db: AsyncSession = Depends(get_db)):
        service = DataSourceService(...)
        return await service.create(...)

    # 3. Context manager
    async with transaction(db):
        await repo.create(...)
        await repo.update(...)
        # Auto-commit on exit, auto-rollback on exception

Anti-Patterns to AVOID:
    ❌ Don't use auto_commit=True within @transaction:
       @transaction
       async def bad_example(self):
           await self.repo.create(..., auto_commit=True)  # WRONG!

    ✅ Instead, let @transaction handle it:
       @transaction
       async def good_example(self):
           await self.repo.create(...)  # Correct - no auto_commit
"""

import functools
import inspect
from contextlib import asynccontextmanager
from typing import Callable, ParamSpec, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


class TransactionManager:
    """Manages database transactions with automatic commit/rollback.

    This manager ensures that:
    1. All operations within the transaction context use the same session
    2. Commit only happens at the end of successful execution
    3. Any exception triggers automatic rollback
    4. Prevents accidental commits mid-transaction
    """

    def __init__(self, db: AsyncSession):
        """Initialize transaction manager.

        Args:
            db: Database session to manage
        """
        self.db = db
        self._original_autocommit = None

    async def __aenter__(self):
        """Enter async context - transaction starts.

        Note: SQLAlchemy AsyncSession defaults to autocommit=False,
        which is the correct behavior for transactions. This manager
        ensures that commit/rollback happen only at transaction boundaries.
        """
        # Mark that we're in a managed transaction (for debugging)
        self.db.info["in_transaction"] = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context - commit or rollback.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised
        """
        try:
            if exc_type is not None:
                # Exception occurred - rollback
                await self.db.rollback()
                logger.warning(f"Transaction rolled back due to {exc_type.__name__}: {exc_val}")
                return False  # Re-raise the exception
            else:
                # Success - commit
                await self.db.commit()
                logger.debug("Transaction committed successfully")
                return True
        finally:
            # Clean up transaction marker
            self.db.info.pop("in_transaction", None)


def transaction(func_or_db: Callable[P, R] | AsyncSession | None = None):
    """Transaction decorator/context manager.

    Can be used in three ways:

    1. As a decorator for service methods (extracts db from self.repositories):
        @transaction
        async def create_something(self, data):
            ...

    2. As a decorator for router handlers (extracts db from function args):
        @transaction
        async def handler(request, db: AsyncSession = Depends(get_db)):
            ...

    3. As a context manager:
        async with transaction(db):
            ...

    Args:
        func_or_db: Either a function to decorate or an AsyncSession for context manager

    Returns:
        Decorated function or TransactionManager context manager
    """
    # Case 3: Used as context manager - transaction(db)
    if isinstance(func_or_db, AsyncSession):
        return TransactionManager(func_or_db)

    # Case 1 & 2: Used as decorator - @transaction
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            db_session = _extract_db_session(func, args, kwargs)

            if db_session is None:
                raise ValueError(
                    f"Cannot find AsyncSession for transaction in {func.__name__}. "
                    "Ensure function has 'db' parameter or 'self' with repositories."
                )

            # Execute function within transaction
            try:
                result = await func(*args, **kwargs)
                await db_session.commit()
                logger.debug(f"Transaction committed for {func.__name__}")
                return result
            except Exception as e:
                await db_session.rollback()
                logger.warning(f"Transaction rolled back in {func.__name__}: {e}")
                raise

        return wrapper

    # If called without parentheses: @transaction
    if func_or_db is not None:
        return decorator(func_or_db)

    # If called with parentheses: @transaction()
    return decorator


def _extract_db_session(func: Callable, args: tuple, kwargs: dict) -> AsyncSession | None:
    """Extract AsyncSession from function arguments.

    Supports multiple patterns:
    1. Service methods: self with repositories (checks first repo for db)
    2. Router handlers: 'db' parameter
    3. Direct 'db' in kwargs

    Args:
        func: Function being decorated
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        AsyncSession if found, None otherwise
    """
    # Pattern 1: Check kwargs for 'db' parameter (most common in routers)
    if "db" in kwargs and isinstance(kwargs["db"], AsyncSession):
        return kwargs["db"]

    # Pattern 2: Check function signature for 'db' parameter position
    sig = inspect.signature(func)
    param_names = list(sig.parameters.keys())

    if "db" in param_names:
        db_index = param_names.index("db")
        if db_index < len(args) and isinstance(args[db_index], AsyncSession):
            return args[db_index]

    # Pattern 3: Service methods - extract from self.repositories
    if args and hasattr(args[0], "__dict__"):
        self_obj = args[0]

        # Check if any attribute is a repository with a db session
        for attr_name in dir(self_obj):
            if attr_name.endswith("_repo") or attr_name.endswith("_repository"):
                repo = getattr(self_obj, attr_name, None)
                if repo and hasattr(repo, "db") and isinstance(repo.db, AsyncSession):
                    return repo.db

    return None


@asynccontextmanager
async def transaction_context(db: AsyncSession):
    """Async context manager for transactions.

    This is an alternative to using transaction(db) as a context manager.

    Usage:
        async with transaction_context(db):
            await repo.create(...)
            await repo.update(...)

    Args:
        db: Database session to manage

    Yields:
        TransactionManager instance
    """
    manager = TransactionManager(db)
    try:
        yield manager
        await db.commit()
        logger.debug("Transaction committed successfully")
    except Exception as e:
        await db.rollback()
        logger.warning(f"Transaction rolled back: {e}")
        raise
