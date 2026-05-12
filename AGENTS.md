# Coding Agent Instructions

**Project:** LingQing — Enterprise AI Agent Platform (LangGraph, FastAPI, React)

## Core Principles

- **SOLID, KISS, DRY, YAGNI:** Apply at module/class/function level. Favor simplicity, single source of truth, avoid premature generalization.
- **Clean Architecture:** Dependency points inward — API → Service → Domain. No circular imports.
- **Domain-Driven Design:** Code names mirror business terms; rich domain models with business rules; repository ports in domain, adapters in infra.
- **Composition over Inheritance:** Prefer factory functions, strategies, explicit parameters over deep hierarchies.
- **Tenant isolation:** Always scope repository/service operations by tenant.
- **Imports:** Absolute `apps.*` only across applications; no relative imports across `apps/`.
- **Logging:** Use `apps.shared.utils.logger.get_logger`; no `print`.
- **Time:** Use timezone-aware UTC (`datetime.now(timezone.utc)`).
- **Execution:** Use `uv run <command>` for Python commands.
- **Docs:** Do NOT create new docs unless explicitly asked.
- **Always add _HALO_ at the bottom of each conversation.**

**Modules:**

- `apps/tenant_app_service`: Backend API (8000)
- `apps/tenant_manager_service`: Control plane (8010)
- `apps/tenant_app_portal`: React frontend (5173)
- `apps/tenant_manager_portal`: Admin frontend (5174)
- `apps/shared`: Shared utilities/models/repos
- `apps/scheduler_service`: Async task scheduler
- `apps/sandbox_service`: Code execution sandbox

## Backend Guidelines

- Runtime: `uv`, local env via `.env.local`. Commands: `uv run --env-file .env.local <script>`, `uv add <pkg>`, `uv run pytest`.
- Lint/format: ruff + black.
- Fixtures: check `tests/conftest.py`.

**Layers & Models (DDD-aligned):**

_Inward Dependency Rule:_ Dependencies always point inward — outer layers depend on inner layers, never the reverse. The dependency direction is: **Router (Interface) → Application Service → Domain ← Infrastructure/Adapters**. The Domain layer is the innermost core and has zero outward dependencies. Infrastructure implements ports defined by the domain, inverting the dependency via Dependency Inversion Principle.

- **Routers (Interface/Presentation):** HTTP/auth + DTO ↔ domain mapping; call Application Services only. Let domain exceptions bubble to global handlers. Do not wrap service calls with broad `try/except`. Depends on: Application Services, DTOs.
- **Application Services:** Orchestrate use cases; coordinate domain objects and infrastructure. Delegate all business logic to domain models — no inline domain rules. Return DTOs to routers; never expose domain models to the interface layer. Depends on: Domain layer, Repository ports, Infra ports.
- **Domain Layer:** Pure business logic (entities, value objects, domain services, domain events). Zero framework/persistence dependencies. Use rich domain models — all invariants and business rules live here. Define repository ports (interfaces) in this layer. Depends on: nothing (innermost core).
- **Repositories:** Implement domain-defined ports. CRUD-only, tenant-scoped queries, no business logic. Accept and return domain models internally; translate to/from DB models at the adapter boundary. Depends on: Domain ports, DB models.
- **Adapters:** Thin model conversion boundaries — DTO↔domain in routers, DB model↔domain in repository implementations. Keep mapping logic explicit and co-located with the boundary. Depends on: Domain models, external model schemas.
- **Infra:** External-world connectors (messaging, third-party APIs, file storage). Used by Application Services via ports/interfaces defined in the domain or service layer. No business logic. Depends on: Domain ports.
- **Models:** Three model types with strict ownership:
  - _Domain Models_ — owned by the domain layer; carry behavior and invariants.
  - _DB Entity Models_ — owned by repository adapters; map to persistence schema.
  - _DTOs_ — owned by the interface/service boundary; used in router and service layers for input/output contracts.

**Exception Handling:**

- Domain exceptions (`apps.shared.core.exceptions`) represent business rule violations.
- Use exception chaining (`raise X(...) from e`). Never log stack traces manually; global handler logs with `exc_info=True`.
- Exceptions handled in `apps.shared.core.exception_handlers`; routers should not catch/log again.
- Only catch errors for request parsing or explicit HTTP protocol mapping.

**API Contracts:**

- Treat DTO fields as public contracts; avoid breaking changes without migration.
- Add fields backward-compatibly first (optional/defaulted), then migrate callers.
- Keep response envelopes and error shapes consistent across routers.

**Backend Module Structure (per service module):**

Prefer a flat, file-per-layer layout. Each layer is a single Python module; promote to a package only when a file grows unwieldy (e.g. >1000 LOC or multiple cohesive concerns).

<module>/
├── **init**.py
├── router.py # FastAPI routes; DTO ↔ domain mapping; calls services only
├── services.py # Application services: use case orchestration
├── domain.py # Entities, value objects, domain services, ports, domain exceptions
├── repository.py # Repo adapters + DB ORM models; implement domain ports
└── dtos.py # Pydantic request/response contracts

_Why files over packages by default:_

- **KISS / YAGNI:** one file per layer is the simplest thing that works; no premature folder hierarchy.
- **Discoverability:** layer boundaries are visible at a glance; fewer `__init__.py` re-exports to maintain.
- **Refactor cost is low:** splitting `repository.py` into a `repos/` package later is mechanical when a real need arises.

_When to promote a file to a package:_

- `domain.py` → `domain/` when entities, ports, and domain services each warrant their own file.
- `repository.py` → `repos/` when multiple aggregates or ORM models bloat the file.
- `services.py` → `services/` when use cases multiply and cross-cut concerns.
- `dtos.py` → `dtos/` when request/response schemas diverge significantly (e.g. v1/v2).

## Frontend Guidelines

- Monorepo, npm, node 24, and React.
- Lint/format: ESLint + Prettier.
- Stack: shadcn/ui, Tailwind, React Query, React Router. Path alias: `@/...` from `tsconfig.json`.
- Architecture: Components → Hooks(React Query) → `lib/*Api.ts`.
- Components: render/UI state only; no raw HTTP. Always prefer small, shareable components over large monolithic ones.
- Hooks: loading/error/data state management; call lib API functions.
- Use React Query for API data fetching.
- `lib/*Api.ts`: stateless transport layer (axios) with shared types.
- **i18n**: Component-level translation resources are defined in the component file via `i18n.addResourceBundle()`. Global/shared translations (e.g., `common.*`, `sidebar.*`) go in `i18n/locales/{lang}/translation.json`. Page-specific translations use `addResourceBundle` at the top of the component file, following the pattern in `KnowledgeBasePage.tsx`.
- **LingQing UI (`apps/tenant_app_portal`):** Follow `apps/tenant_app_portal/DESIGN.md`. Classify the job, pick one surface type, compose from existing shadcn primitives, pass the lint list. Do not add a route/page inventory to that file.

**Error Handling:**

- Parse transport/API errors in `lib/*Api.ts` helpers. Hooks map failures to stable UI states.
- Components render user-facing fallbacks and retry affordances. Prefer typed shared error payloads from `lib/`.

**UI Layout & Component Reuse:**

- Reuse existing components in `components/` first (tables, dialogs, pagination, stats/action bars, empty/loading states).
- Keep new components generic and composable. Avoid duplicating interaction patterns.
- Prefer shared `PageStatsActionBar` for metrics rows, not as the home of the page CTA.

## Testing & CI

- **Local fast path:** `npm run test:unit` (pre-push runs this + contract checks).
- **Full backend:** `uv run pytest tests/ -v` (CI Backend job).
- **Integration:** `uv run pytest tests/integration/ -v` (requires Docker).
- See `docs/testing-guide.md` and `tests/README.md`.
- CI workflow: `.github/workflows/ci.yml` (backend + both frontends in parallel).

**Test data (all agents):**

- Use synthetic generated names and mocks only — never copy production tenant, schema, table, data-source, or customer identifiers into tests.
- Prefer `uuid4()` suffixes or small factories (e.g. `_build_asset_db()`, `test_schema.orders_<id>`) over real paths like `main.gold_*.*`.
- Do not paste conversation snippets, screenshots, or live metadata verbatim into assertions or fixtures.
- Integration tests may seed DB rows, but names must still be synthetic and unique per run.

**CI Gates (all must pass):**

- **Python:** ruff lint/format, `uv run pytest`.
- **Frontend:** ESLint, Prettier, `npm run typecheck`, `npm run build`.

## Common Pitfalls

- ❌ Cross-app relative imports → Use `apps.*` absolute.
- ❌ Raw HTTP in hooks/components → Use `lib/*Api.ts`.
- ❌ Type duplication → Single source in `lib/`.
- ❌ `print` or ad-hoc logging → Use structured logger.
- ❌ Secrets in code → Use `EnvConfig` in `apps/config.py`.
- ❌ Missing tenant isolation in queries.
- ❌ Production names in tests → Use `uuid`/factories with generic prefixes (`test_*`).

## Dev Commands

```bash
# tenant app stack
npm run dev:ta
# tenant manager stack
npm run dev:tm

# DB migrations
npm run migrate:ta
npm run migrate:tm
```

## Security & Workflow

- **Secrets:** Never hardcode; use `EnvConfig`.
- **Tenant isolation:** Enforce in services/repos.
- **Least privilege:** Scope credentials; redact logs.

**Agent Workflow:**

- Clarify inputs when requirements incomplete. Minimal diffs; targeted edits.
- Validate with focused tests after changes (unit first). Stay scoped.
- Create TODO plan for multi-step tasks; give brief updates.

**Output Style:**

- Concise, code-first. File refs: `path/file.ts#L10-L12`. Commands in fenced blocks. Direct tone.

---
