# LingQing Platform SDK Architecture

## Overview

The LingQing SDK provides unified API access across different runtimes:

- **Frontend apps**: JavaScript/TypeScript SDK auto-injected into HTML
- **Scheduled jobs**: Python SDK auto-injected to workspace during app creation
- **Agent skills**: Python SDK for internal platform API access

## Directory Structure

```
apps/shared/sdk/
├── README.md                    # This file
├── js-api/                      # JavaScript/TypeScript SDK (source)
│   ├── src/
│   │   ├── lq-sdk.v1.0.ts      # Main SDK source + component imports
│   │   └── components/          # Web component implementations
│   │       ├── lq-toast.ts
│   │       ├── lq-page-shell.ts
│   │       ├── lq-data-table.ts
│   │       ├── lq-form.ts
│   │       ├── lq-stat-card.ts
│   │       └── lq-import.ts
│   ├── package.json
│   └── tsconfig.json
└── py-api/                      # Python SDK
    ├── __init__.py
    ├── client.py               # LiveAppClient implementation
    ├── models.py               # Pydantic models
    └── exceptions.py           # Custom exceptions
```

**Runtime Serving Structure** (`apps/tenant_app_service/routers/sdk/`):

```
routers/sdk/
├── lq-sdk.v1.0.js              # Bundled JS (69KB) - served to browsers
└── lq-sdk.v1.0.d.ts            # Self-contained type declarations (504 lines)
                                  # - All component types inlined
                                  # - No import statements
                                  # - Used by agents for API spec loading
```

## Build & Distribution

### JavaScript SDK

**Build Process:**

```bash
npm run gen-live-app-sdk
```

This script:

1. Compiles TypeScript from `apps/shared/sdk/js-api/src/`
2. Bundles with esbuild
3. Outputs to `apps/tenant_app_service/routers/sdk/lq-sdk.v1.0.js`
4. Generates type declarations (.d.ts)

**Why this structure?**

- **Source in shared/**: Single source of truth, easy to maintain
- **Output in routers/**: Backend serves from existing route (`/apps/sdk/lq-sdk.v1.0.js`)
- **No breaking changes**: Existing deployments continue working
- **Self-contained .d.ts**: All component types inlined for agent consumption (no imports needed)

### Python SDK

**Distribution Strategy:**

**Option A: Bundle in Sandbox Container Image** (Recommended)

```dockerfile
# In Dockerfile.sandbox-runner
COPY apps/shared/sdk/py-api /opt/lingqing/sdk/py-api
ENV PYTHONPATH="/opt/lingqing/sdk:${PYTHONPATH}"
```

Jobs can then import directly:

```python
from lingqing_sdk import LiveAppClient
```

**Option B: Install as Package**

```bash
pip install -e apps/shared/sdk/py-api
```

**Option C: Copy at Runtime** (Flexible but slower)
Execution service copies SDK files to job workspace before running.

---

## Auto-Injection Mechanisms

### 1. JavaScript SDK → Frontend Apps

**How it works:**

1. **Backend serves compiled JS** at `/apps/sdk/lq-sdk.v1.0.js`
   - Route handler: `apps/tenant_app_service/routers/live_apps.py`
   - Function: `_load_live_app_sdk()`

2. **HTML auto-injection** when serving entry.html:

   ```python
   # In live_apps.py, get_live_app_entry()
   html = _inject_sdk_once(html, sdk_version, app_id, environment)
   ```

3. **Injection adds**:

   ```html
   <!-- Tailwind CSS -->
   <script src="/api/apps/sdk/vendor/tailwind-3.4.17.js"></script>

   <!-- Alpine.js -->
   <script defer src="/api/apps/sdk/vendor/alpine-3.x.js"></script>

   <!-- LingQing SDK -->
   <script src="/api/apps/sdk/lq-sdk.v1.0.js"></script>

   <!-- Initialize client -->
   <script>
     window.LQ = window.LQ || {};
     window.LQ.liveApp = window.LQ.createLiveAppClient({
       appId: 42,
       environment: "prod",
     });
   </script>
   ```

4. **Usage in app code**:
   ```javascript
   // No imports needed - SDK is global
   const result = await window.LQ.liveApp.query("SELECT * FROM orders");
   ```

**Key files:**

- [`live_apps.py:52-82`](apps/tenant_app_service/routers/live_apps.py#L52-L82) - `_inject_sdk_once()`
- [`live_apps.py:86-97`](apps/tenant_app_service/routers/live_apps.py#L86-L97) - `_load_live_app_sdk()`

### 2. Python SDK → Scheduled Jobs

**How it works:**

1. **SDK injection during app creation**:

   When a live app is created, the Python SDK is automatically copied to each environment's workspace:

   ```python
   # apps/shared/live_app/workspace.py
   def _bootstrap_python_sdk(app_path: Path) -> None:
       sdk_source = Path(__file__).parents[1] / "sdk" / "py-api"
       sdk_dest = app_path / "lingqing_sdk"
       shutil.copytree(sdk_source, sdk_dest)
   ```

   **Result**: `/workspace/lingqing_sdk/` contains:
   - `__init__.py`
   - `client.py`
   - `models.py`
   - `exceptions.py`

2. **PYTHONPATH configuration** in sandbox:

   The sandbox service prepends the SDK to PYTHONPATH before executing jobs ([`skill_packages.py:190-207`](apps/sandbox_service/skill_packages.py#L190-L207)):

   ```bash
   # Add Python SDK from workspace (lingqing_sdk package)
   if [ -d "/workspace/lingqing_sdk" ]; then
     export PYTHONPATH="/workspace/lingqing_sdk${PYTHONPATH:+:${PYTHONPATH}}"
   fi
   ```

3. **Token generation** in execution service:

   ```python
   # apps/shared/tasks/execution_service.py
   access_token = jwt.encode({...}, SECRET_KEY)

   runtime_context = {
       "tenant_id": task.tenant_id,
       "app_id": app_id,
       "access_token": access_token,  # Short-lived JWT
       "api_base_url": "http://...",
   }
   ```

4. **Context passed to sandbox** via environment variable:

   ```bash
   TASK_RUNTIME_CONTEXT='{"tenant_id": 1, "app_id": 42, ...}'
   ```

5. **SDK auto-initializes** from context:

   ```python
   from lingqing_sdk import LiveAppClient

   async def main():
       # Reads TASK_RUNTIME_CONTEXT automatically
       async with LiveAppClient.from_environment() as client:
           result = await client.query("SELECT 1")
   ```

**Key files:**

- [`execution_service.py:502-533`](apps/shared/tasks/execution_service.py#L502-L533) - Token generation
- [`client.py:60-85`](apps/shared/sdk/py-api/client.py#L60-L85) - `from_environment()`

---

## Usage Examples

### Frontend (JavaScript)

```html
<!-- entry.html - SDK auto-injected, no imports needed -->
<script>
  // Query database
  const orders = await window.LQ.liveApp.query(
    "SELECT * FROM orders WHERE status = 'pending'"
  );

  // Call external API
  const weather = await window.LQ.liveApp.callApiConnector(
    "weather-api-uid",
    { query: { city: "Shanghai" } }
  );

  // Insert data
  await window.LQ.liveApp.mutateInsert("readings", {
    temperature: weather.body.temp,
    recorded_at: new Date().toISOString()
  });
</script>
```

### Scheduled Job (Python)

```python
# jobs/sync_weather.py
from lingqing_sdk import LiveAppClient
import json

async def main():
    # Auto-initialize from TASK_RUNTIME_CONTEXT
    async with LiveAppClient.from_environment() as client:
        # Get cities to sync
        cities = await client.query("SELECT name, lat, lon FROM cities")

        for city in cities.rows:
            name, lat, lon = city

            # Call weather API (credentials managed by platform)
            result = await client.call_api_connector(
                "weather-api-uid",
                parameters={"query": {"lat": lat, "lon": lon}}
            )

            if result.status_code == 200:
                await client.mutate_insert("weather_readings", {
                    "city": name,
                    "temperature": result.body["main"]["temp"],
                    "humidity": result.body["main"]["humidity"]
                })

        print(json.dumps({"status": "success", "synced": len(cities.rows)}))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

---

## Authentication Flow

### Frontend

- Uses browser session cookies automatically
- No token management needed
- CORS handles cross-origin requests

### Scheduled Jobs

1. Execution service generates short-lived JWT (1 hour expiry)
2. Token embedded in `TASK_RUNTIME_CONTEXT`
3. SDK reads token and includes in all API calls:
   ```python
   headers={"Authorization": f"Bearer {access_token}"}
   ```
4. Backend validates token on each request

### Security Benefits

- ✅ No hardcoded credentials
- ✅ Short-lived tokens (auto-expire)
- ✅ Tenant-scoped permissions
- ✅ Automatic rotation per job execution

---

## Migration Guide

### From Old Structure

If you have code using the old `apps/shared/lingqing_sdk/`:

1. **Update imports**:

   ```python
   # Old
   from lingqing_sdk import LiveAppClient

   # New (same - backward compatible)
   from lingqing_sdk import LiveAppClient
   ```

2. **Update build commands**:

   ```bash
   # Old
   npm run gen-live-app-sdk  # Built from routers/sdk/src/

   # New (same command, different source)
   npm run gen-live-app-sdk  # Builds from shared/sdk/js-api/src/
   ```

3. **No changes needed for runtime** - output location unchanged

---

## Development Workflow

### Modifying JavaScript SDK

1. Edit source: `apps/shared/sdk/js-api/src/lq-sdk.v1.0.ts`
2. Build: `npm run gen-live-app-sdk`
3. Test in dev environment
4. Commit both source and built output

### Modifying Python SDK

1. Edit source: `apps/shared/sdk/py-api/*.py`
2. Test locally:
   ```bash
   uv run python apps/shared/sdk/py-api/test_sdk.py
   ```
3. For sandbox testing, rebuild container image or use Option C (copy at runtime)

### Adding New Methods

1. Add to TypeScript SDK: `js-api/src/lq-sdk.v1.0.ts`
2. Add to Python SDK: `py-api/client.py`
3. Update types/models in both
4. Rebuild JavaScript SDK
5. Update documentation

---

## Troubleshooting

### "SDK not found" in Frontend

Check:

1. Backend serving SDK: `curl http://localhost:8000/api/apps/sdk/lq-sdk.v1.0.js`
2. HTML includes script tag: View page source
3. Browser console for 404 errors

### "Module not found" in Python Job

Check:

1. SDK installed in sandbox: `docker exec <container> python -c "import lingqing_sdk"`
2. PYTHONPATH includes SDK directory
3. Or use Option C (copy at runtime) during development

### Authentication Errors

Check:

1. `TASK_RUNTIME_CONTEXT` has `access_token` field
2. Token hasn't expired (1 hour limit)
3. Backend SECRET_KEY matches between services

---

## Future Enhancements

- [ ] Versioned SDK endpoints (`/sdk/v1/`, `/sdk/v2/`)
- [ ] CDN distribution for frontend SDK
- [ ] Python SDK published to PyPI
- [ ] Automatic SDK updates via WebSocket
- [ ] SDK telemetry/metrics collection

_HALO_
