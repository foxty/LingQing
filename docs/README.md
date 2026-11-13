# Documentation

Public docs use **kebab-case** English filenames.

## Start here

| Document | Description |
| --- | --- |
| [dev-guide.md](dev-guide.md) | **Local development** — setup, two run modes, troubleshooting |
| [agent-architecture.md](agent-architecture.md) | Agent runtime, LangGraph, tools, data flow |

## Testing

| Document | Description |
| --- | --- |
| [testing-guide.md](testing-guide.md) | **Testing** — strategy, layer → test type, commands, CI |

## Deploy & operations

Start at [../deploy/README.md](../deploy/README.md) (folder layout, commands, how release tags appear in examples).

| Document | Description |
| --- | --- |
| [deploy/guide.md](deploy/guide.md) | **Deploy guide** — production steps, scripts, troubleshooting |
| [deploy/reference.md](deploy/reference.md) | PostgreSQL, env vars, Nginx/TLS, topology |
| [deploy/byo-cicd.md](deploy/byo-cicd.md) | Custom CI/CD with build/deploy scripts |

## Development reference

| Document | Description |
| --- | --- |
| [live-app-sdk-guide.md](live-app-sdk-guide.md) | Live App / JS SDK |

## Community

| Document | Description |
| --- | --- |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | How to contribute |
| [../SECURITY.md](../SECURITY.md) | Security reporting |
| [../AGENTS.md](../AGENTS.md) | Coding conventions |

## Apps (code lives under `apps/`)

| App | Local dev | UI / API notes |
| --- | --- | --- |
| Tenant stack | `npm run dev:ta` | [dev-guide.md](dev-guide.md); OpenAPI at `:8000/docs` |
| Tenant portal | included in `dev:ta` | [tenant_app_portal/DESIGN.md](../apps/tenant_app_portal/DESIGN.md) |
| Control plane | `npm run dev:tm` | Manager API `:8010`, portal `:5174` |
| Live App SDK | `npm run gen-live-app-sdk` | [live-app-sdk-guide.md](live-app-sdk-guide.md), [apps/shared/sdk/README.md](../apps/shared/sdk/README.md) |
