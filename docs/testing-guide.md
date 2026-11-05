# Testing Guide

Strategy, patterns, and commands for LingQing tests.

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
2. Mock only at **external** boundaries — LLM, LangGraph, Slack, third-party HTTP; not domain objects; not whole application stacks (see [layer table](#where-tests-live-by-architecture-layer))
3. Match test **depth** to code **layer** — domain and routers: unit; multi-step application orchestrators: integration with real Postgres
4. E2E covers critical paths — not every branch
5. Tenant isolation — always verify in service and API tests

| Test tier | Path | Speed | Depends on | When |
| --- | --- | --- | --- | --- |
| Unit | `tests/unit/` | ms | nothing | pre-push, every change |
| Integration | `tests/integration/` | seconds | Docker | CI, before merge |
| Manual E2E | full Docker stack + smoke checks | minutes | full stack | agent features |

## Where tests live (by architecture layer)

Map backend/frontend code to the **kind** of test agents should write. This is the normative reference for [AGENTS.md](../AGENTS.md#testing--ci) and the agent **Final check** test boxes.

| Code layer | Typical paths | Test tier | What to assert | Mocking |
| --- | --- | --- | --- | --- |
| **Domain** | `domain/`, aggregates, value objects, domain services | **Unit** | Invariants, transitions, calculations | None — real domain instances |
| **Application — session use case** | `*_service.py`, `services.py`, single-transaction coordination | **Unit** | Coordination + domain calls; tenant scope | Repository / port **interfaces** only |
| **Application — orchestrator** | `application/*_flow.py`, multi-step closure, admission, committed sessions | **Integration** | End state in DB; idempotency (call twice) | External I/O only (LLM, graph, Slack) |
| **Infrastructure** | `repository.py`, persistence adapters | **Integration** (or unit with DB for pure SQL mapping) | Tenant-scoped queries, ORM mapping | Real Postgres in integration |
| **Presentation** | `routers/`, ingress | **Unit** | HTTP status, validation, DTO shape | Mock application entry or TestClient + overrides |
| **Frontend** | `components/`, `hooks/`, `lib/*Api.ts` | **Unit** (Vitest) | Hooks/state; API helpers | Mock axios / MSW at transport |

**Orchestrator rule of thumb:** If the test mostly checks “was internal mock A called / not called,” prefer **integration** with seeded rows. If it checks a **domain invariant** or **public HTTP/DTO contract**, **unit** is enough.

**Example (terminal HITL reject closure):** `tests/integration/chat/test_terminal_hitl_reject_closure_integration.py` — first finalize persists ack + completes run; second finalize does not duplicate AI rows.

**External I/O in integration:** Use real Postgres (testcontainers / `pg_async_db_session`); stub LangGraph, LLM, and long network ingress when the scenario is application-layer behavior.

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

### What to test (unit tier)

Follow [Where tests live (by architecture layer)](#where-tests-live-by-architecture-layer). Unit tests here cover **domain**, **session-scoped application** services, and **routers** — not multi-repo orchestrators (those belong in integration).

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

- `tests/conftest.py` — fixture definitions
- [AGENTS.md](../AGENTS.md#testing--ci) — CI gates and agent test-data rules
