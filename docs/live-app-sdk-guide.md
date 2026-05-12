# LingQing Live App SDK - Complete Guide

## Overview

The LingQing Platform provides unified SDKs for live applications across different runtimes:

- **Frontend apps**: JavaScript/TypeScript SDK auto-injected into HTML (`window.LQ.liveApp`)
- **Scheduled jobs**: Python SDK auto-injected to workspace (`lingqing_sdk.LiveAppClient`)
- **Agent skills**: Python SDK for internal platform API access

Both SDKs provide identical functionality with language-appropriate interfaces, enabling consistent development patterns across your entire application stack.

---

## Architecture: How SDK Injection Works

### Frontend SDK (JavaScript/TypeScript)

```
┌─────────────────────────────────────────────────────────────┐
│  BUILD PHASE (Developer)                                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Source: apps/shared/sdk/js-api/src/lq-sdk.v1.0.ts          │
│         + components/*.ts                                    │
│              ↓                                                │
│  Build: npm run gen-live-app-sdk                           │
│         (scripts/build-js-sdk.sh)                            │
│              ↓                                                │
│  Output: apps/tenant_app_service/routers/sdk/                │
│          ├── lq-sdk.v1.0.js       (69KB bundled)            │
│          └── lq-sdk.v1.0.d.ts     (Type declarations)       │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  RUNTIME PHASE (Backend Server)                              │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. User requests: GET /api/apps/{id}/{env}/entry           │
│              ↓                                                │
│  2. Backend loads entry.html from workspace                  │
│              ↓                                                │
│  3. _inject_sdk_once() modifies HTML:                        │
│     - Adds Tailwind CSS script                               │
│     - Adds Alpine.js script                                  │
│     - Adds LingQing SDK script                               │
│     - Initializes window.LQ.liveApp client                   │
│              ↓                                                │
│  4. Returns modified HTML to browser                         │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  BROWSER PHASE (User's Browser)                              │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Browser receives HTML with injected scripts              │
│              ↓                                                │
│  2. Scripts load in order:                                   │
│     <script src="/api/apps/sdk/vendor/tailwind-*.js">        │
│     <script src="/api/apps/sdk/vendor/alpine-*.js">          │
│     <script src="/api/apps/sdk/lq-sdk.v1.0.js">              │
│     <script>window.LQ.liveApp = ...</script>                 │
│              ↓                                                │
│  3. App code can now use:                                    │
│     window.LQ.liveApp.query("SELECT ...")                    │
│     window.LQ.liveApp.callApiConnector(...)                  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Python SDK (Scheduled Jobs)

```
┌─────────────────────────────────────────────────────────────┐
│  APP CREATION PHASE                                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Agent/User creates live app                             │
│              ↓                                                │
│  2. LiveAppService._bootstrap_app_workspace()               │
│              ↓                                                │
│  3. ensure_entry_file() called for each environment          │
│              ↓                                                │
│  4. _bootstrap_python_sdk() copies SDK:                     │
│     apps/shared/sdk/py-api/ → /workspace/lingqing_sdk/      │
│              ↓                                                │
│  Result: Each app environment has its own SDK copy           │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  JOB EXECUTION PHASE                                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Job scheduled via schedule_task(task_type="liveapp_job")│
│              ↓                                                │
│  2. Sandbox container starts with PYTHONPATH preamble:      │
│     export PYTHONPATH="/workspace/lingqing_sdk:${PYTHONPATH}"│
│              ↓                                                │
│  3. Job script runs:                                         │
│     from lingqing_sdk import LiveAppClient                   │
│     async with LiveAppClient.from_environment() as client:   │
│         result = await client.query("SELECT * FROM orders")  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Features

Both SDKs provide the same core operations:

### 1. Database Operations

Query and mutate data in your app's PostgreSQL database.

**Python:**

```python
async with LiveAppClient.from_environment() as client:
    # Query
    result = await client.query("SELECT * FROM orders WHERE status = 'pending'")
    print(f"Found {result.row_count} rows")

    # Insert (single or batch)
    await client.mutate_insert("orders", {
        "customer_id": 123,
        "total": 99.99,
        "status": "pending"
    })

    # Update by ID
    await client.mutate_update_by_id("orders", 42, {"status": "completed"})

    # Update with WHERE clause
    await client.mutate_update_rows(
        "orders",
        {"status": "archived"},
        {"created_at": {"lt": "2024-01-01"}}
    )

    # Delete by ID
    await client.mutate_delete_by_id("orders", 42)
```

**TypeScript:**

```javascript
// Query
const result = await window.LQ.liveApp.query(
  "SELECT * FROM orders WHERE status = 'pending'",
);
console.log(`Found ${result.row_count} rows`);

// Insert
await window.LQ.liveApp.mutateInsert("orders", {
  customer_id: 123,
  total: 99.99,
  status: "pending",
});

// Update by ID
await window.LQ.liveApp.mutateUpdateById("orders", 42, { status: "completed" });

// Update with WHERE
await window.LQ.liveApp.mutateUpdateRows(
  "orders",
  { status: "archived" },
  { created_at: { lt: "2024-01-01" } },
);

// Delete by ID
await window.LQ.liveApp.mutateDeleteById("orders", 42);
```

### 2. API Connector Calls

Call external APIs securely through platform-managed connectors. Authentication is handled automatically - never hardcode credentials.

**Python:**

```python
async with LiveAppClient.from_environment() as client:
    # Call external API
    result = await client.call_api_connector(
        "abc123def456...",  # operation_uid (64-char stable identifier)
        parameters={
            "query": {"city": "Shanghai", "units": "metric"},
            "headers": {"Accept": "application/json"}
        }
    )

    print(f"Status: {result.status_code}")
    print(f"Response: {result.body}")
    print(f"Time: {result.elapsed_ms}ms")
```

**TypeScript:**

```javascript
const result = await window.LQ.liveApp.callApiConnector(
  "abc123def456...", // operation_uid
  {
    query: { city: "Shanghai", units: "metric" },
    headers: { Accept: "application/json" },
  },
);

console.log(`Status: ${result.status_code}`);
console.log(`Response:`, result.body);
console.log(`Time: ${result.elapsed_ms}ms`);
```

### 3. CSV Import

Import CSV files into database tables.

**Python:**

```python
# Note: CSV import typically done via frontend file upload
# For programmatic import, use mutate_insert with parsed data
import csv
from io import StringIO

csv_data = "id,name,email\n1,Alice,alice@example.com"
reader = csv.DictReader(StringIO(csv_data))
for row in reader:
    await client.mutate_insert("users", row)
```

**TypeScript:**

```javascript
// File upload via HTML input
const fileInput = document.getElementById("csv-file");
const file = fileInput.files[0];

const result = await window.LQ.liveApp.importCsv("users", file, "append");
console.log(`Imported ${result.imported_rows} rows`);
```

---

## Detailed Injection Flow

### Frontend SDK Injection

#### Phase 1: Build (Development)

**Trigger:** Developer runs `npm run gen-live-app-sdk`

**Script:** [`scripts/build-js-sdk.sh`](scripts/build-js-sdk.sh)

**Steps:**

1. Read source from `apps/shared/sdk/js-api/src/lq-sdk.v1.0.ts`
2. Install dependencies if needed (TypeScript, esbuild)
3. Generate type declarations (.d.ts files)
4. Bundle with esbuild:
   ```bash
   npx esbuild src/lq-sdk.v1.0.ts \
       --bundle \
       --format=iife \
       --platform=browser \
       --target=es2020 \
       --outfile=apps/tenant_app_service/routers/sdk/lq-sdk.v1.0.js
   ```

**Output:**

- `apps/tenant_app_service/routers/sdk/lq-sdk.v1.0.js` (69.1KB)
- `apps/tenant_app_service/routers/sdk/lq-sdk.v1.0.d.ts` (Type declarations)

#### Phase 2: Runtime Injection (Backend)

**Route Handler:** [`live_apps.py:get_live_app_entry()`](apps/tenant_app_service/routers/live_apps.py#L167-L184)

**Flow:**

1. **User requests entry page:**

   ```
   GET /api/apps/42/prod/entry
   ```

2. **Backend loads raw HTML** from app workspace:

   ```python
   service = LiveAppService.create(...)
   entry = await service.get_entry_page_for_actor(
       app_id=42,
       actor=current_user,
       environment="prod"
   )
   # entry["html"] = raw HTML from workspace/entry.html
   # entry["sdk_version"] = "1.0"
   ```

3. **Inject SDK scripts** via `_inject_sdk_once()`:

   ```python
   html_with_sdk = _inject_sdk_once(
       entry["html"],
       sdk_version="1.0",
       app_id=42,
       environment="prod"
   )
   ```

4. **Injection logic** ([`_inject_sdk_once()`](apps/tenant_app_service/routers/live_apps.py#L58-L82)):
   ```python
   def _inject_sdk_once(html: str, sdk_version: str, app_id: int, environment: str) -> str:
       # Check if already injected (idempotent)
       sdk_tag = f'<script src="/api/apps/sdk/lq-sdk.v{sdk_version}.js"></script>'
       if sdk_tag in html:
           return html  # Already injected, skip

       # Discover vendor assets (Tailwind, Alpine)
       tailwind_file = _discover_vendor_asset("tailwind")
       alpine_file = _discover_vendor_asset("alpine")

       # Build injection snippet
       lines = []
       if tailwind_file:
           lines.append(f'  <script src="/api/apps/sdk/vendor/{tailwind_file}"></script>')
       if alpine_file:
           lines.append(f'  <script defer src="/api/apps/sdk/vendor/{alpine_file}"></script>')
       lines.append(f"  {sdk_tag}")

       # Initialize SDK client with app context
       lines.append(
           "  <script>"
           f"window.LQ=window.LQ||{{}};"
           f'window.LQ.liveApp=window.LQ.createLiveAppClient('
           f'{{appId:{app_id},environment:"{environment}"}});'
           "</script>"
       )

       # Inject before </head> tag
       snippet = "\n".join(lines) + "\n"
       if "</head>" in html:
           return html.replace("</head>", f"{snippet}</head>", 1)
       return f"{snippet}{html}"
   ```

**Result:** Raw HTML becomes:

```html
<!DOCTYPE html>
<html>
  <head>
    <title>My App</title>

    <!-- INJECTED BY BACKEND -->
    <script src="/api/apps/sdk/vendor/tailwind-3.4.17.js"></script>
    <script defer src="/api/apps/sdk/vendor/alpine-3.14.1.js"></script>
    <script src="/api/apps/sdk/lq-sdk.v1.0.js"></script>
    <script>
      window.LQ = window.LQ || {};
      window.LQ.liveApp = window.LQ.createLiveAppClient({
        appId: 42,
        environment: "prod",
      });
    </script>
    <!-- END INJECTION -->
  </head>
  <body>
    <!-- Original app HTML -->
    <div x-data="app">...</div>
  </body>
</html>
```

#### Phase 3: Browser Execution

1. **Browser receives HTML** with injected scripts
2. **Scripts execute in order:**
   - Tailwind CSS → Enables utility classes
   - Alpine.js → Enables reactive directives
   - LingQing SDK → Defines `window.LQ.createLiveAppClient()` and registers web components
   - Initialization script → Creates SDK client instance with app context

3. **App code can now use SDK:**
   ```html
   <script>
     document.addEventListener("alpine:init", () => {
       Alpine.data("orders", () => ({
         items: [],
         async init() {
           const result = await window.LQ.liveApp.query(
             "SELECT * FROM orders LIMIT 10",
           );
           this.items = result.rows;
         },
       }));
     });
   </script>
   ```

### Python SDK Injection

#### Step 1: SDK Copy During App Creation

When a live app is created, the Python SDK is automatically copied to each environment's workspace ([`workspace.py:213-247`](apps/shared/live_app/workspace.py#L213-L247)):

```python
def _bootstrap_python_sdk(app_path: Path) -> None:
    """Copy Python SDK to app workspace for sandbox execution."""
    current_file = Path(__file__).resolve()
    sdk_source = current_file.parents[1] / "sdk" / "py-api"
    sdk_dest = app_path / "lingqing_sdk"

    if sdk_dest.exists():
        return  # Already present (idempotent)

    shutil.copytree(sdk_source, sdk_dest)
```

**Result:** `/workspace/lingqing_sdk/` contains:

- `__init__.py`
- `client.py`
- `models.py`
- `exceptions.py`

#### Step 2: PYTHONPATH Configuration

The sandbox service prepends the SDK to PYTHONPATH before executing jobs ([`skill_packages.py:190-207`](apps/sandbox_service/skill_packages.py#L190-L207)):

```bash
# Add Python SDK from workspace (lingqing_sdk package)
if [ -d "/workspace/lingqing_sdk" ]; then
  export PYTHONPATH="/workspace/lingqing_sdk${PYTHONPATH:+:${PYTHONPATH}}"
fi
```

#### Step 3: Token Generation & Context

Execution service generates short-lived JWT token (1 hour) and passes it via environment variable:

```python
# apps/shared/tasks/execution_service.py
access_token = jwt.encode({...}, SECRET_KEY)

runtime_context = {
    "tenant_id": task.tenant_id,
    "app_id": app_id,
    "access_token": access_token,
    "api_base_url": "http://...",
}

command = f"TASK_RUNTIME_CONTEXT='{json.dumps(runtime_context)}' python jobs/sync_weather.py"
```

#### Step 4: Auto-Initialization in Job

Job script reads context automatically:

```python
from lingqing_sdk import LiveAppClient

async def main():
    # Reads TASK_RUNTIME_CONTEXT automatically
    async with LiveAppClient.from_environment() as client:
        result = await client.query("SELECT 1")
```

---

## Authentication

### Frontend (TypeScript)

Authentication uses browser session cookies automatically. No token management needed.

### Scheduled Jobs (Python)

Jobs receive a short-lived JWT token (1 hour) in `TASK_RUNTIME_CONTEXT`. The SDK reads this automatically:

```python
# This works because TASK_RUNTIME_CONTEXT contains:
# {
#   "tenant_id": 1,
#   "app_id": 42,
#   "environment": "prod",
#   "access_token": "eyJhbGc...",  # Auto-generated
#   "api_base_url": "http://..."
# }

async with LiveAppClient.from_environment() as client:
    # Token is used automatically for all API calls
    result = await client.query("SELECT 1")
```

### Manual Initialization

For custom scenarios (e.g., testing, skills):

```python
client = LiveAppClient(
    tenant_id=1,
    app_id=42,
    environment="prod",
    api_base_url="http://localhost:8000/api",
    access_token="your-jwt-token"
)
```

---

## Error Handling

Both SDKs throw exceptions on errors. Catch and handle them appropriately.

**Python:**

```python
from lingqing_sdk import APIError, AuthError, ValidationError

try:
    result = await client.query("SELECT * FROM invalid_table")
except APIError as e:
    print(f"API error {e.status_code}: {e.message}")
    if e.body:
        print(f"Details: {e.body}")
except AuthError as e:
    print(f"Authentication failed: {e.message}")
except ValidationError as e:
    print(f"Invalid request: {e.message}")
except ValueError as e:
    print(f"Configuration error: {e}")  # e.g., missing app_id
```

**TypeScript:**

```javascript
try {
  const result = await window.LQ.liveApp.query("SELECT * FROM invalid_table");
} catch (error) {
  if (error.status === 401) {
    console.error("Authentication failed");
  } else if (error.status === 404) {
    console.error("Resource not found:", error.message);
  } else {
    console.error(`Error ${error.status}: ${error.message}`);
  }
}
```

---

## Best Practices

### 1. Use API Connectors for External APIs

❌ **Never hardcode credentials:**

```python
# BAD - Security risk!
import requests
requests.get("https://api.example.com", headers={"Authorization": "Bearer secret-key"})
```

✅ **Use API connectors:**

```python
# GOOD - Platform manages credentials
result = await client.call_api_connector("operation-uid", parameters={...})
```

### 2. Validate Inputs for SQL Queries

❌ **SQL injection risk:**

```python
await client.query(f"SELECT * FROM users WHERE id = {user_id}")
```

✅ **Safe approach:**

```python
# SDK doesn't support parameterized queries yet, validate inputs
if not str(user_id).isdigit():
    raise ValueError("Invalid user ID")
await client.query(f"SELECT * FROM users WHERE id = {user_id}")
```

### 3. Handle Errors Gracefully

```python
try:
    result = await client.call_api_connector(op_uid, params)
    if result.status_code == 200:
        await client.mutate_insert("results", result.body)
    else:
        print(f"API call failed: {result.status_code}")
except APIError as e:
    print(f"Retry logic here...")
```

### 4. Batch Operations for Performance

```python
# Instead of individual inserts
for item in items:
    await client.mutate_insert("table", item)  # SLOW

# Use bulk insert
await client.mutate_insert("table", items)  # FAST - pass list
```

### 5. Use Context Managers (Python)

```python
# GOOD - Ensures proper cleanup
async with LiveAppClient.from_environment() as client:
    result = await client.query("SELECT 1")

# BAD - May leak connections
client = LiveAppClient.from_environment()
result = await client.query("SELECT 1")
# Forgot to close!
```

---

## Migration from Direct HTTP Calls

If you have existing code using direct HTTP calls, migrate to the SDK:

**Before:**

```python
import httpx
import os

context = json.loads(os.environ["TASK_RUNTIME_CONTEXT"])
async with httpx.AsyncClient() as client:
    response = await client.post(
        f"http://localhost:8000/api/apps/v1/{context['app_id']}/prod/data/query",
        headers={"Authorization": f"Bearer {context['access_token']}"},
        json={"sql": "SELECT 1"}
    )
    result = response.json()["data"]
```

**After:**

```python
from lingqing_sdk import LiveAppClient

async with LiveAppClient.from_environment() as client:
    result = await client.query("SELECT 1")
```

---

## Troubleshooting

### Frontend SDK Issues

**SDK Not Loading**

- Check backend serving file: `curl http://localhost:8000/api/apps/sdk/lq-sdk.v1.0.js`
- Browser console for 404 errors
- HTML contains injection: View page source, search for `lq-sdk`

**window.LQ Undefined**

- SDK script loaded before initialization script
- No JavaScript errors in console
- Script order in HTML is correct

**Wrong App ID/Environment**

- URL matches pattern: `/apps/{id}/{env}/entry`
- `_inject_sdk_once()` receives correct parameters
- Initialization script has correct values

### Python SDK Issues

**"app_id required" Error**

- Job config includes `app_id`
- `TASK_RUNTIME_CONTEXT` has `app_id` field
- Or manually set: `LiveAppClient(tenant_id=1, app_id=42, ...)`

**"401 Unauthorized" Error**

- Check `TASK_RUNTIME_CONTEXT` has `access_token`
- Tokens expire after 1 hour (for long-running jobs, implement retry)
- Verify token format: should be JWT string

**"404 Not Found" for API Connector**

- Verify operation_uid from API connector admin UI
- Ensure connector belongs to same tenant
- Check operation is active (not disabled)

**Connection Timeout**

- Default timeout is 30 seconds
- For long operations, implement async polling pattern
- Check network connectivity to backend service

---

## API Reference

### LiveAppClient (Python)

#### Constructor

```python
LiveAppClient(
    tenant_id: int,
    app_id: Optional[int] = None,
    environment: str = "prod",
    api_base_url: str = "http://localhost:8000/api",
    access_token: Optional[str] = None
)
```

#### Class Methods

- `from_environment()` - Initialize from TASK_RUNTIME_CONTEXT

#### Instance Methods

- `query(sql: str)` → `LiveAppQueryResult`
- `mutate_insert(table, data)` → `LiveAppMutateResult`
- `mutate_update_by_id(table, id, data)` → `LiveAppMutateResult`
- `mutate_update_rows(table, data, where)` → `LiveAppMutateResult`
- `mutate_delete_by_id(table, id)` → `LiveAppMutateResult`
- `call_api_connector(operation_uid, parameters)` → `ApiExecutionResult`
- `close()` - Close HTTP client

### LiveAppClient (TypeScript)

Available as `window.LQ.liveApp` with same method names (camelCase):

- `query(sql)` → `Promise<LiveAppQueryResult>`
- `mutateInsert(table, data)` → `Promise<LiveAppMutateResult>`
- `mutateUpdateById(table, id, data)` → `Promise<LiveAppMutateResult>`
- `mutateUpdateRows(table, data, where)` → `Promise<LiveAppMutateResult>`
- `mutateDeleteById(table, id)` → `Promise<LiveAppMutateResult>`
- `callApiConnector(operationUid, parameters)` → `Promise<ApiExecutionResult>`

---

## Examples

### Example 1: Weather Data Sync Job (Python)

```python
"""Sync weather data from external API every hour."""
from lingqing_sdk import LiveAppClient
import json
from datetime import datetime, timezone

async def main():
    async with LiveAppClient.from_environment() as client:
        # Get cities to sync
        cities = await client.query("SELECT name, lat, lon FROM cities")

        synced = 0
        for city in cities.rows:
            name, lat, lon = city

            # Call weather API
            result = await client.call_api_connector(
                "weather-api-uid",
                parameters={"query": {"lat": lat, "lon": lon}}
            )

            if result.status_code == 200:
                # Store weather data
                await client.mutate_insert("weather_readings", {
                    "city": name,
                    "temperature": result.body["main"]["temp"],
                    "humidity": result.body["main"]["humidity"],
                    "recorded_at": datetime.now(timezone.utc).isoformat()
                })
                synced += 1

        print(json.dumps({"status": "success", "synced": synced}))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Example 2: Dashboard with Real-time Data (TypeScript)

```html
<!-- entry.html -->
<script>
  document.addEventListener("alpine:init", () => {
    Alpine.data("dashboard", () => ({
      orders: [],
      loading: true,

      async init() {
        try {
          const result = await window.LQ.liveApp.query(`
          SELECT o.*, c.name as customer_name
          FROM orders o
          JOIN customers c ON o.customer_id = c.id
          ORDER BY o.created_at DESC
          LIMIT 10
        `);
          this.orders = result.rows;
        } catch (error) {
          console.error("Failed to load orders:", error);
        } finally {
          this.loading = false;
        }
      },
    }));
  });
</script>

<div x-data="dashboard">
  <template x-if="loading">
    <p>Loading...</p>
  </template>

  <template x-if="!loading">
    <table>
      <thead>
        <tr>
          <th>Order ID</th>
          <th>Customer</th>
          <th>Total</th>
        </tr>
      </thead>
      <tbody>
        <template x-for="order in orders">
          <tr>
            <td x-text="order[0]"></td>
            <td x-text="order[1]"></td>
            <td x-text="order[2]"></td>
          </tr>
        </template>
      </tbody>
    </table>
  </template>
</div>
```

---

## Key Components Summary

| Component              | Location                                               | Purpose                       |
| ---------------------- | ------------------------------------------------------ | ----------------------------- |
| **JS Source**          | `apps/shared/sdk/js-api/src/lq-sdk.v1.0.ts`            | TypeScript source code        |
| **JS Components**      | `apps/shared/sdk/js-api/src/components/*.ts`           | Web components                |
| **Build Script**       | `scripts/build-js-sdk.sh`                              | Compiles TS → JS              |
| **JS Output**          | `apps/tenant_app_service/routers/sdk/lq-sdk.v1.0.js`   | Bundled JS served to browsers |
| **Vendor Assets**      | `apps/tenant_app_service/routers/sdk/vendor/`          | Tailwind, Alpine.js           |
| **JS Injection Logic** | `apps/tenant_app_service/routers/live_apps.py:58-82`   | `_inject_sdk_once()`          |
| **JS SDK Route**       | `apps/tenant_app_service/routers/live_apps.py:142-149` | Serves JS file                |
| **Entry Route**        | `apps/tenant_app_service/routers/live_apps.py:167-184` | Injects SDK into HTML         |
| **Python Source**      | `apps/shared/sdk/py-api/`                              | Python SDK source             |
| **Python Bootstrap**   | `apps/shared/live_app/workspace.py:213-247`            | Copies SDK to workspace       |
| **PYTHONPATH Config**  | `apps/sandbox_service/skill_packages.py:190-207`       | Prepends SDK to PYTHONPATH    |

---

## Customization

### Change SDK Version

1. Update source file name: `lq-sdk.v2.0.ts`
2. Rebuild: `npm run gen-live-app-sdk`
3. Update app metadata to use `sdk_version: "2.0"`

### Add New Vendor Library

1. Drop file in `apps/tenant_app_service/routers/sdk/vendor/`:

   ```
   vendor/mylib-1.0.js
   ```

2. Update `_inject_sdk_once()` to include it:
   ```python
   mylib_file = _discover_vendor_asset("mylib")
   if mylib_file:
       lines.append(f'  <script src="/api/apps/sdk/vendor/{mylib_file}"></script>')
   ```

### Disable Auto-Injection (Frontend)

Add SDK tag manually to `entry.html`:

```html
<head>
  <script src="/api/apps/sdk/lq-sdk.v1.0.js"></script>
  <script>
    window.LQ = window.LQ || {};
    window.LQ.liveApp = window.LQ.createLiveAppClient({
      appId: 42,
      environment: "prod",
    });
  </script>
</head>
```

Backend detects existing tag and skips injection.

---

## Performance Considerations

1. **Caching:**
   - SDK JS: 1 year cache (immutable)
   - Entry HTML: No cache in dev/test, 5 min in prod
   - Vendor libs: Auto-discovered, cached indefinitely

2. **Size:**
   - Bundled SDK: ~69KB (gzipped ~20KB)
   - Load time: <100ms on broadband

3. **Optimization:**
   - Tree-shaking via esbuild
   - IIFE format prevents global pollution
   - Lazy component registration

---

## Security

1. **CSP Compatibility:**
   - All scripts served from same origin
   - No inline scripts (except initialization)
   - Can add nonce if needed

2. **XSS Protection:**
   - App ID/environment escaped in injection
   - No user input in script tags
   - HTML sanitized before injection

3. **Authentication:**
   - Frontend: Uses browser session cookies
   - Python: Short-lived JWT tokens (1 hour)
   - No hardcoded credentials anywhere

---

## Support

For issues or questions:

- Check error messages and status codes
- Review this guide for common patterns
- Consult platform documentation for API connector setup
- Contact platform support for authentication issues

_HALO_
