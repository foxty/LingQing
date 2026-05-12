# Python Scheduled Jobs Guide

## Overview

Write Python scripts that run on cron schedules to automate data processing, ETL pipelines, and background tasks.

## Contents

- [Quick Start](#quick-start)
- [SDK Initialization](#sdk-initialization)
- [Common Job Patterns](#common-job-patterns)
- [Error Handling](#error-handling)
- [Available Libraries](#available-libraries)
- [Execution Environment](#execution-environment)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### Basic Job Structure

```python
"""Sync weather data from external API."""
from lingqing_sdk import LiveAppClient
import json
from datetime import datetime, timezone

async def main():
    # Auto-initialize from TASK_RUNTIME_CONTEXT
    async with LiveAppClient.from_environment() as client:
        # Your logic here
        result = await client.query("SELECT COUNT(*) FROM orders")

        # Output JSON for logging
        print(json.dumps({
            "status": "success",
            "count": result.rows[0][0],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### File Location

Jobs live in the `jobs/` directory under your app's environment:

```
apps/{app_id}/env/{environment}/
├── lingqing_sdk/          # Auto-injected by platform
├── requirements.txt       # Your dependencies (optional, per-environment)
├── jobs/
│   ├── sync_weather.py
│   └── cleanup_old_data.py
└── entry.html
```

---

## SDK Initialization

### Auto-Initialization (Recommended)

The SDK reads `TASK_RUNTIME_CONTEXT` environment variable automatically:

```python
async with LiveAppClient.from_environment() as client:
    # Ready to use
    result = await client.query("SELECT 1")
```

**What's in TASK_RUNTIME_CONTEXT:**

```json
{
  "tenant_id": 1,
  "app_id": 42,
  "environment": "prod",
  "access_token": "jwt_token_here",
  "api_base_url": "http://localhost:8000/api"
}
```

### Manual Initialization (Testing Only)

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

```python
# Query
result = await client.query("SELECT id, name FROM orders LIMIT 10")
# result.rows: list of lists, result.columns: column names, result.row_count: int

# Insert (single or batch)
await client.mutate_insert("orders", {"customer_name": "John", "amount": 99.99})
await client.mutate_insert("orders", [{"customer_name": "Alice"}, {"customer_name": "Bob"}])

# Update
await client.mutate_update_by_id("orders", 123, {"status": "completed"})
await client.mutate_update_rows("orders", {"status": "cancelled"}, {"status": "pending"})

# Delete
await client.mutate_delete_by_id("orders", 123)
```

For full parameter details and return types, see [`python_sdk_reference.md`](./python_sdk_reference.md).

---

## API Connector Calls

Call external APIs through configured connectors (authentication managed by platform):

```python
result = await client.call_api_connector(
    "weather-api-operation-uid",
    parameters={"query": {"city": "Shanghai", "units": "metric"}}
)
# result.status_code, result.body, result.elapsed_ms, result.error
```

**Parameters:** `query` (query string), `path` (URL templating), `body` (JSON), `headers` (overrides). For full details, see [`python_sdk_reference.md`](./python_sdk_reference.md).

---

## Common Job Patterns

### Pattern 1: ETL Sync Job

Extract from external API → Transform → Load to database:

```python
"""Sync products from external inventory API."""
from lingqing_sdk import LiveAppClient
import json
from datetime import datetime, timezone

async def main():
    async with LiveAppClient.from_environment() as client:
        # 1. Extract: Fetch from external API
        response = await client.call_api_connector(
            "inventory-api-uid",
            parameters={"query": {"category": "electronics"}}
        )

        if response.status_code != 200:
            raise Exception(f"API failed: {response.error}")

        products = response.body["products"]

        # 2. Transform: Clean and reshape data
        cleaned_products = []
        for product in products:
            cleaned_products.append({
                "sku": product["id"],
                "name": product["title"],
                "price": float(product["price"]),
                "stock": int(product["quantity"]),
                "synced_at": datetime.now(timezone.utc).isoformat()
            })

        # 3. Load: Upsert to database
        for product in cleaned_products:
            await client.mutate_insert("products", product)

        # 4. Log results
        print(json.dumps({
            "status": "success",
            "synced": len(cleaned_products),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

All job patterns follow the same structure: init client → fetch/process data → store results → output JSON summary. Adapt the ETL pattern above for aggregation, cleanup, webhook processing, or any other job type.

---

## Error Handling

### Basic Error Handling

```python
from lingqing_sdk import APIError, AuthError

try:
    result = await client.query("SELECT * FROM orders")
except APIError as e:
    print(json.dumps({"error": str(e), "status": e.status_code}))
    raise
except AuthError as e:
    print(json.dumps({"error": "Authentication failed"}))
    raise
```

### Retry Logic

```python
import asyncio

async def query_with_retry(client, sql, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await client.query(sql)
        except APIError as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # Exponential backoff
            await asyncio.sleep(wait_time)
```

---

## Logging

### Recommended: Structured JSON to stdout

Jobs should output structured logs to stdout. The sandbox captures all output and displays it in task execution logs:

```python
import json
from datetime import datetime, timezone

# Simple status log
print(json.dumps({
    "level": "INFO",
    "message": "Sync completed",
    "processed": 150,
    "timestamp": datetime.now(timezone.utc).isoformat()
}))

# Error log
print(json.dumps({
    "level": "ERROR",
    "message": "Failed to fetch data",
    "error": "Connection timeout",
    "timestamp": datetime.now(timezone.utc).isoformat()
}))
```

For complex jobs, Python's built-in `logging` module with a `StreamHandler` works as an alternative.

---

## Available Libraries

### Runtime Environment

- **Python 3.11** (slim variant)
- **`lingqing_sdk`** - Platform SDK (pre-installed)
- **`httpx`** - Async HTTP client (pre-installed)
- **`pydantic`** - Data validation (pre-installed)
- **Python standard library** - All built-in modules available

### Third-Party Dependencies

Add packages to `requirements.txt` at app root:

```txt
# apps/{app_id}/env/{environment}/requirements.txt
pandas==2.0.0          # Data manipulation
numpy==1.24.0          # Numerical computing
beautifulsoup4==4.12.0 # HTML parsing
openpyxl==3.1.0        # Excel file handling
```

**Best practices:**

1. **Pin versions** - Use `==` for reproducible builds
2. **Minimize dependencies** - Reduces install time
3. **Prefer async libs** - `httpx` over `requests`
4. **Avoid heavy packages** - Large packages increase install time
5. **Test locally** - Verify compatibility before scheduling

---

## Best Practices

- **Always use `async with`** context manager for `LiveAppClient`
- **Batch inserts** — pass a list of dicts to `mutate_insert()` instead of looping
- **Use API connectors** for external APIs (platform manages auth, never hardcode credentials)
- **Process large datasets in batches** with LIMIT/OFFSET to avoid memory/timeout issues
- **Pin dependency versions** in `requirements.txt` with `==`

For detailed examples and SDK best practices, see [`python_sdk_reference.md`](./python_sdk_reference.md).

---

## Execution Environment

When a scheduled job executes, the sandbox:

1. **Sets working directory** to `/app_root` (your app's environment directory)
2. **Installs dependencies** from `requirements.txt` to `.venv/` (persisted across runs)
3. **Configures PYTHONPATH** to include `/app_root` and `/app_root/.venv`

**What this means:**

- `from lingqing_sdk import LiveAppClient` works without `sys.path` manipulation
- Dependencies are auto-installed and cached for faster subsequent runs
- Relative paths resolve from `/app_root` (e.g., `open("data/file.csv")`)

---

## Scheduling Jobs

After writing and committing your job, set up a cron schedule via the platform scheduler.

**Common cron expressions:**

- `"0 * * * *"` — Every hour
- `"0 0 * * *"` — Daily at midnight
- `"0 9 * * 1"` — Every Monday at 9 AM
- `"*/5 * * * *"` — Every 5 minutes
- `"0 0 1 * *"` — First day of every month

---

## Testing Jobs Locally

You can test jobs locally before scheduling:

```bash
# Set up environment
export TASK_RUNTIME_CONTEXT='{"tenant_id": 1, "app_id": 42, "environment": "dev", "access_token": "test-token"}'

# Run job
cd apps/42
python jobs/sync_weather.py
```

---

## Troubleshooting

### Job Fails with "Module Not Found"

**Problem**: `ModuleNotFoundError: No module named 'pandas'`

**Solution**: Add the package to `requirements.txt` and commit.

### Job Times Out

**Problem**: Job exceeds execution time limit

**Solution**:

1. Process data in smaller batches
2. Add pagination to queries
3. Optimize SQL queries with indexes

### Authentication Errors

**Problem**: `AuthError: Invalid token`

**Solution**: Ensure `TASK_RUNTIME_CONTEXT` contains valid `access_token`. This is auto-injected in sandbox.

### API Connector Not Found

**Problem**: `APIError: Connector operation_uid not found`

**Solution**: Verify the operation_uid exists in your app's API connector configuration.

---

## Next Steps

For frontend development, see: [`frontend_guide.md`](./frontend_guide.md)

For complete Python SDK reference, see: [`python_sdk_reference.md`](./python_sdk_reference.md)
