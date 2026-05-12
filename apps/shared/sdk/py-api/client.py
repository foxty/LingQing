"""Async client wrapper for LingQing platform API."""

import json
import os

import httpx

from .exceptions import APIError
from .models import (
    ApiExecutionResult,
    ApiOperationCallParameters,
    LiveAppMutateResult,
    LiveAppQueryResult,
)


class LiveAppClient:
    """Unified client for LingQing platform operations.

    Usage in scheduled jobs:
        async with LiveAppClient.from_environment() as client:
            result = await client.query("SELECT * FROM orders")

    Usage with explicit parameters:
        client = LiveAppClient(
            tenant_id=1,
            app_id=42,
            environment="prod",
            access_token="..."
        )
    """

    def __init__(
        self,
        tenant_id: int,
        app_id: int,
        environment: str,
        api_base_url: str,
        access_token: str,
    ):
        """Initialize SDK client.

        Args:
            tenant_id: Tenant identifier
            app_id: App identifier (required for most operations)
            environment: Environment name (dev/test/prod)
            api_base_url: Base URL for API endpoints
            access_token: JWT access token for authentication
        """
        self.tenant_id = tenant_id
        self.app_id = app_id
        self.environment = environment
        self._client = httpx.AsyncClient(
            base_url=api_base_url,
            headers={"Authorization": f"Bearer {access_token}"} if access_token else {},
            timeout=30.0,
        )

    @classmethod
    def from_environment(cls) -> "LiveAppClient":
        """Initialize from TASK_RUNTIME_CONTEXT (for sandbox jobs).

        Reads context from environment variable TASK_RUNTIME_CONTEXT which contains:
        - tenant_id
        - app_id
        - environment
        - access_token
        - api_base_url (provided by execution_service via SANDBOX_RUNNER_API_BASE_URL)

        Returns:
            Configured LiveAppClient instance

        Raises:
            ValueError: If required context fields are missing
        """
        context_json = os.environ.get("TASK_RUNTIME_CONTEXT", "{}")
        try:
            context = json.loads(context_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid TASK_RUNTIME_CONTEXT JSON: {e}")

        tenant_id = context.get("tenant_id")
        if not tenant_id:
            raise ValueError("tenant_id is required in TASK_RUNTIME_CONTEXT")

        return cls(
            tenant_id=tenant_id,
            app_id=context.get("app_id"),
            environment=context.get("environment"),
            api_base_url=context.get("api_base_url"),
            access_token=context.get("access_token"),
        )

    async def query(self, sql: str) -> LiveAppQueryResult:
        """Execute SQL query against app's configured data source.

        Args:
            sql: SQL query string (SELECT statements only)

        Returns:
            Query result with rows, columns, and row_count

        Raises:
            ValueError: If app_id is not set
            APIError: If query execution fails
        """
        if not self.app_id:
            raise ValueError("app_id required for database queries")

        response = await self._client.post(
            f"/apps/v1/{self.app_id}/{self.environment}/data/query",
            json={"sql": sql},
        )

        if not response.is_success:
            raise APIError(
                message=f"Query failed: {response.text}",
                status_code=response.status_code,
                body=response.json() if response.headers.get("content-type") == "application/json" else None,
            )

        data = response.json().get("data", {})
        return LiveAppQueryResult(**data)

    async def mutate_insert(self, table: str, data: dict | list[dict]) -> LiveAppMutateResult:
        """Insert records into a table.

        Args:
            table: Table name
            data: Single record dict or list of record dicts

        Returns:
            Mutation result with affected_rows count
        """
        return await self._mutate("insert", table, data=data)

    async def mutate_update_by_id(self, table: str, id: str | int, data: dict) -> LiveAppMutateResult:
        """Update a single record by ID.

        Args:
            table: Table name
            id: Record ID
            data: Fields to update

        Returns:
            Mutation result with affected_rows count
        """
        return await self._mutate("update_by_id", table, id=id, data=data)

    async def mutate_update_rows(self, table: str, data: dict, where: dict) -> LiveAppMutateResult:
        """Update multiple records matching WHERE clause.

        Args:
            table: Table name
            data: Fields to update
            where: WHERE conditions

        Returns:
            Mutation result with affected_rows count
        """
        return await self._mutate("update", table, data=data, where=where)

    async def mutate_delete_by_id(self, table: str, id: str | int) -> LiveAppMutateResult:
        """Delete a single record by ID.

        Args:
            table: Table name
            id: Record ID

        Returns:
            Mutation result with affected_rows count
        """
        return await self._mutate("delete_by_id", table, id=id)

    async def call_api_connector(
        self,
        operation_uid: str,
        parameters: ApiOperationCallParameters | None = None,
    ) -> ApiExecutionResult:
        """Call external API through connector (app-scoped).

        Authentication managed by platform - no credentials in code.

        Args:
            operation_uid: Stable operation identifier (not DB primary key)
            parameters: Optional query/path/body parameters

        Returns:
            Execution result with status_code, body, headers, elapsed_ms

        Raises:
            ValueError: If app_id is not set
            APIError: If API call fails
        """
        if not self.app_id:
            raise ValueError("app_id required for API connector calls")

        response = await self._client.post(
            f"/apps/v1/{self.app_id}/{self.environment}/api-connectors/{operation_uid}/call",
            json={
                "parameters": parameters.model_dump()
                if hasattr(parameters, "model_dump")
                else (parameters.dict() if hasattr(parameters, "dict") else parameters or {})
            },
        )

        if not response.is_success:
            raise APIError(
                message=f"API connector call failed: {response.text}",
                status_code=response.status_code,
                body=response.json() if response.headers.get("content-type") == "application/json" else None,
            )

        return ApiExecutionResult(**response.json())

    async def close(self):
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    # Internal helper methods

    async def _mutate(
        self,
        operation: str,
        table: str,
        data: dict | list[dict] | None = None,
        where: dict | None = None,
        id: str | int | None = None,
    ) -> LiveAppMutateResult:
        """Internal mutation helper.

        Args:
            operation: Mutation type (insert/update/update_by_id/delete_by_id)
            table: Table name
            data: Record data
            where: WHERE conditions (for update)
            id: Record ID (for update_by_id/delete_by_id)

        Returns:
            Mutation result

        Raises:
            ValueError: If app_id is not set
            APIError: If mutation fails
        """
        if not self.app_id:
            raise ValueError("app_id required for mutations")

        payload = {"operation": operation, "table": table}
        if data is not None:
            payload["data"] = data
        if where is not None:
            payload["where"] = where
        if id is not None:
            payload["id"] = id

        response = await self._client.post(
            f"/apps/v1/{self.app_id}/{self.environment}/data/mutate",
            json=payload,
        )

        if not response.is_success:
            raise APIError(
                message=f"Mutation failed: {response.text}",
                status_code=response.status_code,
                body=response.json() if response.headers.get("content-type") == "application/json" else None,
            )

        data_result = response.json().get("data", {})
        return LiveAppMutateResult(**data_result)
