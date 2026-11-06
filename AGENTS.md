# Coding Agent Instructions

**Project:** LingQing — Enterprise AI Agent Platform (LangGraph, FastAPI, React)

**Document map:** [Core Principles](#core-principles) · [Backend](#backend-guidelines) (layers, DB, exceptions, API) · [Frontend](#frontend-guidelines) · [Testing & CI](#testing--ci) · [Testing guide](docs/testing-guide.md) (pyramid, **layer → test type**, commands) · [Common Pitfalls](#common-pitfalls) · [Agent Workflow](#agent-workflow) (final check, git, PR, output)

## Core Principles

- **SOLID, KISS, DRY, YAGNI:** Apply at module/class/function level. Favor simplicity, single source of truth, avoid premature generalization.
- **Clean Architecture:** Dependency points inward — Presentation → Application → Domain ← Infrastructure. No circular imports.
- **Domain-Driven Design:** Code names mirror business terms; rich domain models with business rules; repository ports in domain, adapters in infra.
- **Composition over Inheritance:** Prefer factory functions, strategies, explicit parameters over deep hierarchies.
- **Tenant isolation:** Always scope repository/service operations by tenant.
- **Imports:** Absolute `apps.*` only across applications; no relative imports across `apps/`.
- **Logging:** Use `apps.shared.utils.logger.get_logger`; no `print`.
- **Time:** Use timezone-aware UTC (`datetime.now(timezone.utc)`).
- **Execution:** Use `uv run <command>` for Python commands.
- **Docs:** Do NOT create new docs unless explicitly asked.

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

### Layers and models (DDD)

_Inward dependency rule:_ outer layers depend on inner layers; **Domain** depends on nothing outward. **Infrastructure** implements **ports** defined in Domain (DIP).

**Four layers:**

```text
Presentation (routers, ingress)  →  Application  →  Domain  ←  Infrastructure
```

| Layer | Responsibility | Must not |
| --- | --- | --- |
| **Presentation** | HTTP/auth, Slack payloads, SSE response wiring; DTO ↔ domain mapping at the edge | Repositories, domain rules, long-lived `AsyncSession` across LLM/SSE |
| **Application** | **Use cases:** orchestrate domain + persistence + external **ports**; decide transaction boundaries and transport (queues, background tasks) | Domain invariants re-encoded ad hoc; holding one DB session across long I/O |
| **Domain** | Aggregates/entities, value objects, **domain services**, invariants, **repository and external ports** (interfaces) | Frameworks, ORM, HTTP, LangGraph |
| **Infrastructure** | Repository implementations, ORM mapping, LangGraph/Slack/agent adapters, message buses | Business rules, `commit`/`rollback` in repos |

There is **no separate “service layer”** below Application. Classes in **`services.py`** or **`*_service.py`** (e.g. `ThreadRunService`, `ChatTurnService`) are **Application layer** code: session-scoped use-case steps on a supplied `AsyncSession`. The **`application/`** package holds **orchestrating** use cases (multi-step, multi-session, or explicit entry points for routers/ingress). Both belong to Application; the split is **organization**, not a different tier.

**Dependency direction:** **Presentation → Application → Domain**. Application depends on Domain (and port interfaces). Infrastructure depends on Domain and is wired at the edges (handlers construct repos/adapters with `db`).

**Application layer (detail):**

- **Orchestrators** (`<module>/application/`, e.g. `turn_flow.py`): which use-case steps run, in which order, in which committed session; SSE/background wiring.
- **Session-scoped use cases** (`services.py`, `*_service.py`): one transaction on supplied `AsyncSession` — load/save via repositories or port implementations, invoke **domain** behavior, return DTOs upward.
- **Compose peers** in the same transaction when the use case spans aggregates (e.g. turn execution + run finalization): still Application, same layer.
- **Invariants** live in **Domain**; Application coordinates only.
- Prefer **ports** for cross-context I/O (e.g. `AgentRunPort`); concrete repositories in the same module are acceptable where ports are not yet extracted.

**Domain (detail):**

- **Aggregates** and **aggregate roots** define consistency boundaries (e.g. agent run status, promotion eligibility).
- **Domain services** for rules that do not fit a single entity.
- **Ports** (repository interfaces, invoker interfaces) declared here; no SQLAlchemy or FastAPI types.

**Infrastructure (detail):**

- **Repositories:** tenant-scoped persistence; `flush()` only; map ORM ↔ domain at the boundary.
- **Adapters:** thin DTO↔domain mappers at presentation or persistence edges.
- **External systems:** LangGraph invoke, Slack client, etc. — no business rules.

**Bounded contexts:** Name modules by capability (chat, HITL, agents). Cross-context interaction via **application orchestration** or **ports**, not repositories reaching into another context’s tables ad hoc.

**Incremental strictness:** New behavior → put rules on **domain** first; add port interfaces when swapping implementations or testing demands it; keep use cases thin. Refactor **inward**; no big-bang folder moves required.

Add `<module>/application/` when use cases need **orchestration** (multiple steps, multiple committed sessions, cross-module glue, or long I/O). A single-session use case may live in **`services.py`** with **Presentation → `SomeService(db)`** — still Application layer. Session rules: [Database sessions](#database-sessions). Example: `chat/__init__.py` module docstring.

**Layer detail (presentation):**

- Map request/response DTOs; call Application use cases; let domain exceptions bubble ([Exception handling](#exception-handling)); no broad `try/except` around use cases.

**Models (three types — do not mix):**

- _Domain models_ — domain layer; behavior + invariants.
- _DB entity models_ — infrastructure persistence; ORM schema at the repository boundary.
- _DTOs_ — presentation ↔ application boundary; public API contracts ([API contracts](#api-contracts)).

### Database sessions

Session lifecycle is owned by the **Application** entry point — not by repositories or domain.

- **HTTP requests:** inject `AsyncSession = Depends(get_db)`. `get_db` commits on success and rolls back on exception.
- **Background tasks / scripts:** use `async with app_db_session() as db:` — same commit-on-success, rollback-on-error behavior.
- **Repositories:** `flush()` only to persist within the current transaction. Never `commit()` or `rollback()`.
- **Application use cases:** see [Layers](#layers-and-models-ddd) — orchestrators open each `app_db_session()` step; session-scoped use cases run inside the supplied session and do **not** `commit()`/`rollback()` unless the entry-point doc says otherwise.
- **Routers:** do not `rollback()` — the dependency handles errors. Avoid `commit()` before background work; use `<module>/application/` instead of pinning `Depends(get_db)` across long I/O.

**When explicit `commit()` is allowed:**

- In a router/handler **immediately before** `asyncio.create_task(...)`, so the background task's separate `app_db_session()` can read committed state (e.g. Slack event dedupe).
- Inside a standalone `app_db_session()` block when later steps in the **same** block need earlier writes persisted first (rare; document why).
- Do **not** add service-layer commits "just to be safe" — double commits are redundant in production and break savepoint-based integration tests.

### Exception handling

- Domain exceptions (`apps.shared.core.exceptions`) represent business rule violations.
- Use exception chaining (`raise X(...) from e`). Never log stack traces manually; global handler logs with `exc_info=True`.
- Exceptions handled in `apps.shared.core.exception_handlers`; routers should not catch/log again.
- Only catch errors for request parsing or explicit HTTP protocol mapping.

### API contracts

- Treat DTO fields as public contracts; avoid breaking changes without migration.
- Add fields backward-compatibly first (optional/defaulted), then migrate callers.
- Keep response envelopes and error shapes consistent across routers.

**Backend Module Structure (per service module):**

Prefer a flat, file-per-layer layout. Each layer is a single Python module; promote to a package only when a file grows unwieldy (e.g. >1000 LOC or multiple cohesive concerns).

<module>/
├── **init**.py
├── router.py # Presentation: DTO mapping; calls application/ and/or services.py
├── application/ # Application: orchestrating use cases (multi-step / multi-session)
├── services.py # Application: session-scoped use cases (one transaction per call)
├── domain.py # Domain: entities, aggregates, domain services, port interfaces
├── repository.py # Infrastructure: persistence adapters (+ ORM models at boundary)
└── dtos.py # Presentation/application API contracts (Pydantic)

_Why files over packages by default:_

- **KISS / YAGNI:** one file per layer is the simplest thing that works; no premature folder hierarchy.
- **Discoverability:** layer boundaries are visible at a glance; fewer `__init__.py` re-exports to maintain.
- **Refactor cost is low:** splitting `repository.py` into a `repos/` package later is mechanical when a real need arises.

_When to promote a file to a package:_

- `domain.py` → `domain/` when entities, ports, and domain services each warrant their own file.
- `repository.py` → `repos/` when multiple aggregates or ORM models bloat the file.
- `services.py` → `services/` when Application use-case classes multiply and cross-cut concerns.
- Add `<module>/application/` when use cases need orchestration (multiple steps, committed sessions, cross-module glue, or long I/O — not before).
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
- **LingQing UI (`apps/tenant_app_portal`):** Follow `apps/tenant_app_portal/DESIGN.md`. Classify the job, pick one layout surface (Detail views: one `prose` or `metrics` modifier), compose from existing shadcn primitives, pass the lint list. Feedback: one channel per event — `useNotification` for toasts, `getApiErrorMessage` for API errors, inline for validation and diagnostics (§5). Do not add a route/page inventory to that file.

### Error handling

- Parse transport/API errors in `lib/*Api.ts` helpers. Hooks map failures to stable UI states.
- Components render user-facing fallbacks and retry affordances. Prefer typed shared error payloads from `lib/`.

**UI Layout & Component Reuse:**

- Reuse existing components in `components/` first (tables, dialogs, pagination, stats/action bars, empty/loading states).
- Keep new components generic and composable. Avoid duplicating interaction patterns.
- Prefer shared `PageStatsActionBar` for metrics rows, not as the home of the page CTA.

## Testing & CI

**Normative testing strategy (pyramid, architecture layer → unit vs integration, examples):** [docs/testing-guide.md](docs/testing-guide.md) — especially [Where tests live (by architecture layer)](docs/testing-guide.md#where-tests-live-by-architecture-layer).

- **Local fast path:** `npm run test:unit` (pre-push runs this + contract checks).
- **Full backend:** `uv run pytest tests/ -v` (CI Backend job).
- **Integration:** `uv run pytest tests/integration/ -v` (requires Docker).
- CI workflow: `.github/workflows/ci.yml` (backend + both frontends in parallel).

**Agent rule (summary):** domain → unit, no I/O mocks; `application/*_flow` orchestrators → integration + real DB; session `*_service.py` → unit with repo/port mocks; routers/hooks → unit at the HTTP/transport boundary. Do not duplicate long testing rules here — use the guide.

### Test data (all agents)

- Use synthetic generated names and mocks only — never copy production tenant, schema, table, data-source, or customer identifiers into tests.
- Prefer `uuid4()` suffixes or small factories (e.g. `_build_asset_db()`, `test_schema.orders_<id>`) over real paths like `main.gold_*.*`.
- Do not paste conversation snippets, screenshots, or live metadata verbatim into assertions or fixtures.
- Integration tests may seed DB rows, but names must still be synthetic and unique per run.

**CI Gates (all must pass):**

- **Python:** ruff lint/format, `uv run pytest`.
- **Frontend:** ESLint, Prettier, `npm run typecheck`, `npm run build`.

## Common Pitfalls

_Quick ❌/✅ index. Normative detail lives in [Core Principles](#core-principles), [Backend](#backend-guidelines), and [Frontend](#frontend-guidelines)—do not duplicate rules here when editing._

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

## Agent Workflow

_Process, mandatory pre-done review, git/PR (only when asked), and reply format._

- Clarify inputs when requirements incomplete. Minimal diffs; targeted edits.
- Create TODO plan for multi-step tasks; give brief updates.
- **Before finishing any task that changes code** (and again before a user-requested commit), run the **Final check** below. Fix violations in scope; call out gaps explicitly if the user did not ask to fix them.
- **Security (all code):** secrets via `EnvConfig`; tenant isolation in services/repos; least privilege and redacted logs — see [Core Principles](#core-principles) and [Common Pitfalls](#common-pitfalls).

### Final check (required)

_Review the diff against sections above — not style preferences. Check each box; if a box fails, fix or call out the gap in your reply._

**Design & architecture**

- [ ] **Layers & dependency rule** — [Layers and models](#layers-and-models-ddd): presentation → application → domain ← infrastructure; no inward imports of frameworks or UI transport into domain.
- [ ] **Tenant isolation** — [Core Principles](#core-principles) / repos: tenant-scoped reads and writes where applicable.
- [ ] **Database sessions** — [Database sessions](#database-sessions): no pinning `Depends(get_db)` for streaming/long waits; repos `flush()` only; commits only where this doc allows.
- [ ] **Exceptions** — [Exception handling](#exception-handling): domain exceptions bubble; no router catch-and-log; chain with `from e`.
- [ ] **API contracts** — [API contracts](#api-contracts): backward-compatible DTO/event fields or explicit versioning.
- [ ] **Frontend** — [Frontend Guidelines](#frontend-guidelines) + `DESIGN.md`: Components → Hooks → `lib/*Api.ts`; one feedback channel per event.
- [ ] **Imports, logging, secrets** — [Core Principles](#core-principles) + [Common Pitfalls](#common-pitfalls): `apps.*`, `get_logger`, no hardcoded secrets.
- [ ] **Scope** — [Core Principles](#core-principles): minimal diff; KISS / YAGNI (no drive-by refactors).

**Tests**

- [ ] **Coverage** — [Testing guide — by layer](docs/testing-guide.md#where-tests-live-by-architecture-layer): right tier for the code (orchestrator → integration; domain → unit); regression when feasible.
- [ ] **Test data** — [Test data (all agents)](#test-data-all-agents): synthetic only; no production identifiers in fixtures.
- [ ] **Executed** — run pytest/vitest (or lint/typecheck) on touched areas when feasible before claiming done.
- [ ] **Gaps** — if tests skipped, state what is missing and what would cover it.

### Git commits (only when the user explicitly asks)

Follow [Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/#summary):

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

- **Types (lowercase):** `feat` (new feature), `fix` (bug fix), plus `docs`, `refactor`, `test`, `chore`, `ci`, `build`, `perf` as needed
- **Scope (optional):** noun in parentheses — e.g. `deploy`, `docs`, `ci`, `tenant-app`, `shared`
- **Description:** imperative mood, lowercase start, no trailing period, ≤72 chars — e.g. `refactor(deploy): simplify release bundle and consolidate docs`
- **Body:** optional; blank line after description; explain **why**, not a file list
- **Breaking changes:** `feat!:` / `fix(scope)!:` or footer `BREAKING CHANGE: …`
- **Do not** commit unless explicitly requested; never skip hooks; never amend unless user rules allow
- **Never auto-commit or auto-push.** `commit`, `push`, and `PR` are three separate actions, each requiring its own explicit user request:
  - A request to commit does **not** imply permission to push
  - A request to push does **not** imply permission to open a PR
  - An earlier agreement like "we'll PR this later" is a plan, not a trigger — wait for the explicit ask at that point
  - When in doubt, stop after the requested action and confirm before proceeding

```bash
git commit -m "$(cat <<'EOF'
refactor(deploy): simplify release bundle and consolidate docs

Drop side-by-side staging on one VM; ship init_db.sh in the bundle.
EOF
)"
```

### Pull requests (only when the user explicitly asks)

- **Title:** same [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/#summary) format as the commit subject — e.g. `refactor(deploy): simplify release bundle and consolidate docs`
- **Body sections** (use what applies):
  - `## Summary` — 1–3 bullets: what changed and why
  - `## Architecture / decisions` — key design choices, trade-offs, or behavior changes reviewers should know (omit if trivial)
  - `## Test plan` — checkbox list of verification steps
- Push with `git push -u origin HEAD`; create with `gh pr create`; return the PR URL — **only after the user explicitly asks to push/open the PR**

```bash
gh pr create --title "refactor(deploy): simplify release bundle and consolidate docs" --body "$(cat <<'EOF'
## Summary
- Drop side-by-side staging/prod on one VM
- Ship init_db.sh and minimal .env.template in release bundle

## Architecture / decisions
- One VM per environment; same bundle for prod and staging, only `.env` differs
- PostgreSQL stays external; bundle includes `init_db.sh` for no-repo operators
- Deploy docs consolidated to guide + reference (procedure vs lookup)

## Test plan
- [ ] package-release-bundle.sh produces expected tarball
- [ ] bootstrap.sh smoke checks pass
EOF
)"
```

### Output style

- Concise, code-first. File refs: `path/file.ts#L10-L12`. Commands in fenced blocks. Direct tone.
- When code changed, end with a short **Final check** note: architecture (pass or what was fixed) and tests (added/ran, or explicit gap). Omit for question-only or doc-only replies with no logic impact.
- **Always add _HALO_** at the bottom of each conversation (see [Core Principles](#core-principles)).

---
