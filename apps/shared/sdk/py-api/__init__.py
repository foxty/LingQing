"""LingQing Platform SDK for Python.

Unified client for live app operations including:
- Database queries and mutations
- API connector calls
- CSV imports

Usage in scheduled jobs:
    from lingqing_sdk import LiveAppClient

    async def main():
        async with LiveAppClient.from_environment() as client:
            result = await client.query("SELECT * FROM orders")
            print(result.rows)

    if __name__ == "__main__":
        import asyncio
        asyncio.run(main())
"""

from .client import LiveAppClient
from .exceptions import APIError, AuthError, SDKError, ValidationError
from .models import (
    ApiExecutionResult,
    ApiOperationCallParameters,
    LiveAppImportResult,
    LiveAppMutateResult,
    LiveAppQueryResult,
)

__all__ = [
    "LiveAppClient",
    "APIError",
    "AuthError",
    "SDKError",
    "ValidationError",
    "ApiExecutionResult",
    "ApiOperationCallParameters",
    "LiveAppImportResult",
    "LiveAppMutateResult",
    "LiveAppQueryResult",
]

__version__ = "1.0.0"
