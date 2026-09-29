# Testing Guide

Strategy, patterns, and commands for LingQing tests. Cheat sheet: [tests/README.md](../tests/README.md).

## Overview

LingQing uses a **test pyramid** aligned with the layered architecture:

```
                 E2E (manual, 2-3 flows)
                   ↑
            Integration (2-5 per feature)
              ↑
        Unit tests (~80%)
```

**Principles:**

1. Fast feedback — unit tests on every change; full suite in CI
2. Mock only at boundaries — DB, HTTP, env; not domain objects
3. E2E covers critical paths — not every branch
4. Tenant isolation — always verify in service and API tests

| Layer | Path | Speed | Depends on | When |
| --- | --- | --- | --- | --- |
| Unit | `tests/unit/` | ms | nothing | pre-push, every change |
| Integration | `tests/integration/` | seconds | Docker | CI, before merge |
| Manual E2E | full Docker stack + smoke checks | minutes | full stack | agent features |

---

## Quick commands

```bash
npm run test:unit                              # unit tests (pre-push)
uv run pytest tests/integration/ -v            # integration (Docker required)
uv run pytest tests/ -v                        # full suite (CI)

uv run pytest tests/unit/dashboard/ -v         # one module
uv run pytest tests/unit/foo.py::test_bar -v   # single test
uv run pytest tests/unit/ -vv -s --pdb         # debug
uv run pytest tests/unit/ --cov=apps --cov-report=html
uv run pytest tests/ --durations=10            # slowest tests
uv run pytest -m "not slow" -v                 # skip slow-marked tests
```

---

## Unit tests

**Location:** `tests/unit/`  
**Prerequisites:** none

```bash
uv run pytest tests/unit/ -v
uv run pytest tests/unit/dashboard/ -v
uv run pytest tests/unit/rag/ -v
```

Common directories: `agents/`, `auth/`, `authz/`, `chat/`, `dashboard/`, `hitl/`, `infra/`, `rag/`, `services/`, `utils/`.

### What to test

| Layer | Focus | Mock? |
| --- | --- | --- |
| Domain | Invariants, validation, calculations | No — create real objects |
| Adapter | Serialization round-trips, field mapping | No |
| Service | Business logic, tenant isolation | Mock repository only |
| Router | Input validation, HTTP status codes | TestClient + mock service |

**Domain example:**

```python
def test_entity_constraint_validation():
    layout = Layout(cols=12)
    position = Position(x=8, w=5)
    with pytest.raises(ConstraintError):
        layout.validate_position(position)
```

**Service example:**

```python
@pytest.mark.asyncio
async def test_tenant_isolation(mock_repo):
    resource_1 = await create_test_resource(tenant_id=1, name="R1")
    service_2 = MyService.create(tenant_id=2, db_session=session)
    assert await service_2.get_resource(resource_1.id) is None
```

**Router example:**

```python
def test_invalid_input_returns_422(client, mock_service):
    response = client.post("/api/v1/resources", json={"position": {"x": 10, "w": 5}})
    assert response.status_code == 422
```

Use **FastAPI TestClient** for router unit tests (no running server). Use `httpx.AsyncClient` only when a real service is required.

---

## Integration tests

**Location:** `tests/integration/`  
**Prerequisites:** Docker running (testcontainers manages Postgres/Chroma automatically)

```bash
docker info                    # verify Docker
uv run pytest tests/integration/ -v
```

Containers are created per session and torn down automatically. Each test uses SAVEPOINT rollback — no manual cleanup.

### Common errors

| Error | Fix |
| --- | --- |
| `Docker daemon is unavailable` | Start Docker Desktop or `colima start` |
| `Docker socket not found` (Colima) | `export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock` |
| `Future attached to a different loop` | Use `pg_async_db_session`; don't reuse outer session in TestClient |

### TestClient + async DB

Do not pass an outer `async_db_session` into TestClient (different event loop). Override per request:

```python
@pytest.fixture
def test_client_with_db(pg_container):
    engine = create_async_engine(pg_container)
    async def override_get_db():
        async with AsyncSession(engine) as session:
            yield session
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.sync_engine.dispose()
```

### API / tool workflow patterns

Integration tests verify full HTTP or tool chains with real DB:

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_update_workflow(test_client_with_db, auth_headers):
    resp = test_client_with_db.post("/api/v1/resources", json={...}, headers=auth_headers)
    assert resp.status_code == 200
    resource_id = resp.json()["id"]
    # update, get, assert tenant isolation...
```

---

## Manual E2E

Automated browser E2E is planned; today use the full Docker stack and smoke checks in [deploy/guide.md](deploy/guide.md).

```bash
cp deploy/env/.env.template deploy/env/.env.e2e
# .env.e2e: TENANT_APP_DB_HOST=postgres, TENANT_APP_DB_PORT=5432; host ports fixed in full-stack.yml
./deploy/scripts/local-stack.sh stack-up
./deploy/scripts/local-stack.sh smoke
TENANT_APP_DB_HOST=localhost TENANT_APP_DB_PORT=5433 npm run migrate-db:ta
TENANT_APP_DB_HOST=localhost TENANT_APP_DB_PORT=5433 npm run tenant-cli -- create --name "Test" --slug test
./deploy/scripts/local-stack.sh stack-down
```

---

## Deploy validation (non-daily)

Verify `init_main_db.sh` and tenant provisioning when changing deployment scripts — see commands in git history or run against a throwaway Postgres container on port `55432`.

---

## Fixtures

Core fixtures live in `tests/conftest.py` and `tests/integration/conftest.py`:

- `async_db_session` / `pg_async_db_session` — DB sessions with rollback
- `client` — FastAPI TestClient
- `runtime_context` — agent tool runtime context

Prefer per-test data over global autouse seeds (avoids ordering conflicts).

### Mock vs fixture

```
External dependency?
├─ Yes → Mock (repository, httpx, os.environ)
└─ No  → Real object or fixture (domain models, TestClient + mock service)
```

---

## RBAC / permission tests

Backend: `get_effective_rbac()` and `/auth/profile` return shape.  
Frontend: `useAuth` checkers and `<Can>` component rendering.

```bash
uv run pytest tests/unit/shared/core/test_rbac.py -v
```

---

## CI

Push/PR runs [`.github/workflows/ci.yml`](../.github/workflows/ci.yml):

- Backend: ruff + `pytest tests/` + API spec + SDK checks
- Tenant app portal: lint + build + vitest
- Tenant manager portal: lint + build

Local pre-push (`.husky/pre-push`): contract checks + `npm run test:unit`.

---

## FAQ

**Why unit-test Service if E2E exists?**  
Branchy logic (auto-layout, constraints, tenant scoping) is expensive to cover only via E2E.

**How to isolate integration data?**  
Use SAVEPOINT fixtures (`pg_async_db_session`); each test creates only what it needs.

**Test data rules:**  
Synthetic names only — never production tenant, schema, or customer identifiers. Prefer `uuid4()` suffixes.

---

## See also

- [tests/README.md](../tests/README.md) — one-page command cheat sheet
- `tests/conftest.py` — fixture definitions
