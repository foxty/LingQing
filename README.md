# LingQing

**Enterprise multi-tenant AI agent platform** — build, deploy, and operate LangGraph agents in an isolated, controlled environment connected to enterprise knowledge bases and data sources.

---

## What is it?

LingQing is a self-hostable agent platform with:

- **Tenant App** — chat, knowledge base, dashboards, Live Apps, and more for business users
- **Tenant Manager** — multi-tenant control plane for platform admins (tenants, users, models, permissions)
- **Agent runtime** — LangGraph tool calling, skill loading, RAG retrieval, and sandbox execution

Built for **tenant isolation**, **enterprise permission models (RBAC/ABAC)**, and **private deployment** — not one-off scripts or single-user chatbots.

## Why use it?

| Pain point | LingQing approach |
| --- | --- |
| Agent logic scattered and hard to reuse | LangGraph state machine + unified tool/skill registry |
| Hard to connect knowledge and business data to agents | Built-in RAG, document assets, API connectors, vector search |
| SaaS cannot meet data residency requirements | Docker self-hosting; per-tenant DB isolation |
| Multiple teams on one platform | Split control plane and app plane; per-tenant config and permissions |
| Demo-to-production gap | FastAPI layered architecture, contract tests, CI, deploy scripts |

## Core capabilities

- Multi-agent orchestration and chat (streaming / non-streaming)
- Enterprise knowledge RAG and hybrid retrieval
- JWT auth, RBAC/ABAC, tenant-scoped data isolation
- Live Apps (agent-driven deployable mini-apps)
- Code sandbox and async task scheduling
- Nx monorepo: Python backends + dual React portals

## Architecture

```
apps/
├── tenant_app_service/       # App API (:8000)
├── tenant_manager_service/   # Control plane API (:8010)
├── tenant_app_portal/        # App frontend (:5173)
├── tenant_manager_portal/    # Admin frontend (:5174)
├── scheduler_service/        # Async tasks
├── sandbox_service/          # Agent code sandbox
└── shared/                   # Shared libraries
```

| Layer | Stack |
| --- | --- |
| Agents | LangGraph, LangChain |
| Backend | FastAPI, SQLAlchemy, PostgreSQL |
| Vectors | ChromaDB |
| Frontend | React, Vite, shadcn/ui |
| Tooling | uv, Nx, Node 24 |

Agent runtime details: [docs/agent-architecture.md](docs/agent-architecture.md).

---

## 5-minute local start

**Prerequisites:** [uv](https://docs.astral.sh/uv/), Node 24, Docker Desktop (or Colima)

```bash
# from a clone of this repository
uv sync --all-groups
cp deploy/env/.env.template .env.local
./deploy/scripts/local-stack.sh infra-up   # PostgreSQL, Chroma, Sandbox
npm run migrate-db:ta
cd apps/tenant_app_portal && npm install && cd ../..
npm run dev:ta                          # API + frontend + scheduler + sandbox
```

**First-time setup:** create a tenant and symlink skills (see [dev guide](docs/dev-guide.md)):

```bash
npm run tenant-cli -- --name demo --slug demo
ln -sfn "$(pwd)/config/skills" "<DATA_ROOT_PATH>/skills"   # DATA_ROOT_PATH in .env.local
```

**Open in browser:**

| Service | URL |
| --- | --- |
| App portal | http://localhost:5173 |
| API docs | http://localhost:8000/docs |
| Control plane (optional `npm run dev:tm`) | http://localhost:5174 |

Default local credentials: `admin` / `admin` (development only).

Full install, run modes (hot reload vs full Docker), and troubleshooting → **[docs/dev-guide.md](docs/dev-guide.md)**

---

## Deployment

LingQing is self-hosted. See [docs/deploy/README.md](docs/deploy/README.md):

- **Single VM (recommended):** [Deploy guide](docs/deploy/guide.md)
- **Custom CI/CD:** [BYO pipeline guide](docs/deploy/byo-cicd.md) + [workflow example](.github/workflows/deploy.example.yml)

## Common commands

```bash
npm run dev:ta              # App stack
npm run dev:tm              # Control plane stack
npm run test:unit           # Unit tests
npm run lint                # Ruff + ESLint
```

## Documentation

| Doc | Description |
| --- | --- |
| [docs/dev-guide.md](docs/dev-guide.md) | **Local development** — setup, commands, troubleshooting |
| [docs/agent-architecture.md](docs/agent-architecture.md) | Agent runtime and tools |
| [docs/testing-guide.md](docs/testing-guide.md) | Testing strategy, commands, CI |
| [docs/deploy/README.md](docs/deploy/README.md) | Production deployment paths |
| [docs/README.md](docs/README.md) | Full documentation index |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution workflow |
| [AGENTS.md](AGENTS.md) | Code architecture conventions |

## CI

Push/PR triggers [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (backend pytest + frontend lint/build/test). Local pre-push runs contract checks and unit tests only.

---

**Version** v2.0.0 · **License** [Apache-2.0](LICENSE)
