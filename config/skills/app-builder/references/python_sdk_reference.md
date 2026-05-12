# LingQing Python SDK API Reference

## Overview

The LingQing Python SDK provides async client for live app operations in scheduled jobs and agent skills.

**Installation**: Auto-injected into workspace during app creation.

**Location**: `/app_root/lingqing_sdk/` (automatically added to PYTHONPATH)

**Auto-initialization**: SDK reads `TASK_RUNTIME_CONTEXT` environment variable for authentication.

## Contents

- [Quick Start](#quick-start)
- [Client Initialization](#client-initialization)
- [Database Operations](#database-operations)
- [API Connector Operations](#api-connector-operations)
- [Error Handling](#error-handling)
- [Data Models](#data-models)

---

## Quick Start

```python
from lingqing_sdk import LiveAppClient
import json

async def main():
    # Auto-initialize from TASK_RUNTIME_CONTEXT (includes tenant_id, app_id, access_token)
    async with LiveAppClient.from_environment() as client:
        # Query database
        result = await client.query("SELECT * FROM orders WHERE status = 'pending'")
        print(f"Found {result.row_count} rows")

        # Call external API via connector
        api_result = await client.call_api_connector(
            "operation_uid_here",  # From API connector configuration
            parameters={"query": {"city": "Shanghai"}}
        )

        # Insert data
        await client.mutate_insert("weather_data", api_result.body)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

---

## Client Initialization

### `LiveAppClient.from_environment()` → `LiveAppClient`

Initialize client from `TASK_RUNTIME_CONTEXT` environment variable (recommended for jobs).

**Environment Variable Format:**

```json
{
  "tenant_id": 1,
  "app_id": 42,
  "environment": "prod",
  "access_token": "jwt_token_here",
  "api_base_url": "http://localhost:8000/api"
}
```

**Usage:**

```python
async with LiveAppClient.from_environment() as client:
    # Use client...
```

### `LiveAppClient(tenant_id, app_id, ...)` → `LiveAppClient`

Manual initialization (for testing or custom scenarios).

**Parameters:**

- `tenant_id` (int): Tenant identifier
- `app_id` (int | None): App identifier (required for API connector calls)
- `environment` (str): Environment name (default: "prod")
- `api_base_url` (str): API base URL (default: "http://localhost:8000/api")
- `access_token` (str | None): JWT access token

**Usage:**

```python
client = LiveAppClient(
    tenant_id=1,
    app_id=42,
    environment="dev",
    access_token="your-token"
)
```

---

## Database Operations

### `client.query(sql: str)` → `LiveAppQueryResult`

Execute SQL query against app's database.

**Parameters:**

- `sql` (str): SQL SELECT statement

**Returns:** `LiveAppQueryResult`

- `rows` (list[list]): Query result rows
- `columns` (list[str]): Column names
- `row_count` (int): Number of rows returned

**Example:**

```python
result = await client.query("SELECT id, name, status FROM orders LIMIT 10")
for row in result.rows:
    print(f"Order {row[0]}: {row[1]} ({row[2]})")
```

### `client.mutate_insert(table: str, data: dict | list[dict])` → `LiveAppMutateResult`

Insert one or more records into a table.

**Parameters:**

- `table` (str): Table name
- `data` (dict | list[dict]): Record(s) to insert

**Returns:** `LiveAppMutateResult`

- `app_id` (int): App identifier
- `operation` (str): Operation type ("insert")
- `table` (str): Table name
- `affected_rows` (int): Number of inserted rows

**Example:**

```python
# Single record
await client.mutate_insert("orders", {
    "customer_name": "John Doe",
    "amount": 99.99,
    "status": "pending"
})

# Multiple records
await client.mutate_insert("orders", [
    {"customer_name": "Alice", "amount": 50.00},
    {"customer_name": "Bob", "amount": 75.00}
])
```

### `client.mutate_update_by_id(table: str, id: str | int, data: dict)` → `LiveAppMutateResult`

Update a single record by ID.

**Parameters:**

- `table` (str): Table name
- `id` (str | int): Record ID
- `data` (dict): Fields to update

**Returns:** `LiveAppMutateResult`

**Example:**

```python
await client.mutate_update_by_id("orders", 123, {
    "status": "completed",
    "updated_at": "2024-01-01T00:00:00Z"
})
```

### `client.mutate_update_rows(table: str, data: dict, where: dict)` → `LiveAppMutateResult`

Update multiple records matching WHERE clause.

**Parameters:**

- `table` (str): Table name
- `data` (dict): Fields to update
- `where` (dict): WHERE conditions

**Returns:** `LiveAppMutateResult`

**Example:**

```python
await client.mutate_update_rows(
    "orders",
    {"status": "cancelled"},
    {"status": "pending", "created_at <": "2024-01-01"}
)
```

### `client.mutate_delete_by_id(table: str, id: str | int)` → `LiveAppMutateResult`

Delete a single record by ID.

**Parameters:**

- `table` (str): Table name
- `id` (str | int): Record ID

**Returns:** `LiveAppMutateResult`

**Example:**

```python
await client.mutate_delete_by_id("orders", 123)
```

---

## API Connector Operations

### `client.call_api_connector(operation_uid: str, parameters: ApiOperationCallParameters | None)` → `ApiExecutionResult`

Call external API through configured API connector (inherits app permissions).

**Parameters:**

- `operation_uid` (str): API connector operation UID (64-char stable identifier)
- `parameters` (ApiOperationCallParameters | None): Request parameters
  - `query` (dict | None): Query string parameters
  - `path` (dict | None): Path parameters
  - `body` (dict | None): Request body
  - `headers` (dict | None): Custom headers

**Returns:** `ApiExecutionResult`

- `status_code` (int): HTTP status code
- `body` (any): Response body (parsed JSON or text)
- `headers` (dict[str, str]): Response headers
- `elapsed_ms` (int): Request duration in milliseconds
- `error` (str | None): Error message if failed

**Example:**

```python
# GET request with query parameters
result = await client.call_api_connector(
    "weather-api-uid",
    parameters={
        "query": {"city": "Shanghai", "units": "metric"}
    }
)
print(f"Temperature: {result.body['temp']}°C")

# POST request with body
result = await client.call_api_connector(
    "webhook-uid",
    parameters={
        "body": {"event": "order_completed", "order_id": 123}
    }
)
```

---

## Context Manager

### `async with client:`

Automatically manages HTTP client lifecycle.

**Example:**

```python
async with LiveAppClient.from_environment() as client:
    # Client opens here
    result = await client.query("SELECT 1")
    # Client closes automatically when block exits
```

---

## Error Handling

### `SDKError` (base exception)

Base exception for all SDK errors.

### `APIError`

HTTP API call failed.

**Attributes:**

- `message` (str): Error message
- `status_code` (int | None): HTTP status code

**Example:**

```python
from lingqing_sdk import APIError

try:
    result = await client.query("INVALID SQL")
except APIError as e:
    print(f"API error {e.status_code}: {e.message}")
```

### `AuthError`

Authentication/authorization failed.

### `ValidationError`

Invalid input parameters.

---

## Data Models

### `LiveAppQueryResult`

Query execution result.

**Fields:**

- `rows` (list[list[Any]]): Result rows
- `columns` (list[str]): Column names
- `row_count` (int): Row count

### `LiveAppMutateResult`

Mutation operation result.

**Fields:**

- `app_id` (int): App identifier
- `operation` (str): Operation type
- `table` (str): Table name
- `affected_rows` (int): Affected row count

### `ApiExecutionResult`

API connector execution result.

**Fields:**

- `status_code` (int): HTTP status code
- `body` (Any): Response body
- `headers` (dict[str, str]): Response headers
- `elapsed_ms` (int): Duration in milliseconds
- `error` (str | None): Error message

### `ApiOperationCallParameters`

API connector call parameters.

**Fields:**

- `query` (dict[str, Any] | None): Query parameters
- `path` (dict[str, Any] | None): Path parameters
- `body` (dict[str, Any] | None): Request body
- `headers` (dict[str, str] | None): Custom headers

---
