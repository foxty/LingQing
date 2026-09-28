# Deployment Guide

LingQing is **self-hosted**. You provide the VM, container registry, PostgreSQL, domains, TLS, and secrets.

**Start here:** [getting-started.md](getting-started.md) · **Layout cheat sheet:** [deploy/README.md](../../deploy/README.md)

## Choose a path

| Path | Best for | Guide |
| --- | --- | --- |
| **Try locally** | Evaluation, E2E smoke | [getting-started.md](getting-started.md) + [dev-guide.md](../dev-guide.md) |
| **Single VM (Compose)** | First production | [vm-bootstrap.md](vm-bootstrap.md) or [quick-start.md](quick-start.md) |
| **Custom CI/CD** | Repeatable releases | [byo-cicd.md](byo-cicd.md) |

## Tiers

| Tier | Target | Entry command |
| --- | --- | --- |
| dev | Laptop | `./deploy/scripts/local-stack.sh infra-up` |
| e2e | Laptop | `./deploy/scripts/local-stack.sh stack-up` |
| staging | Remote VM | `./deploy/scripts/remote/deploy.sh … staging` |
| production | Remote VM | `./deploy/scripts/remote/release.sh …` |

Details: [getting-started.md → All tiers](getting-started.md#all-tiers).

## Scripts

| Script | Role |
| --- | --- |
| `deploy/scripts/local-stack.sh` | Local dev + E2E |
| `deploy/scripts/remote/host-deploy.sh` | On-host deploy from release bundle (shipped as `bootstrap.sh`) |
| `deploy/scripts/remote/deploy.sh` | Remote deploy via SSH (staging or production) |
| `deploy/scripts/remote/release.sh` | Build + push + production deploy |
| `deploy/scripts/package-release-bundle.sh` | Build release tarball (CI) |
| `deploy/scripts/build-*.sh` | Image build (local or CI) |
| `deploy/scripts/generate-env.sh` | Env file from template (CI) |

## Documentation map

| Document | Purpose |
| --- | --- |
| [vm-bootstrap.md](vm-bootstrap.md) | VM deploy without repo clone |
| [getting-started.md](getting-started.md) | Decision tree, tiers, scripts |
| [quick-start.md](quick-start.md) | Production deploy step-by-step |
| [configuration.md](configuration.md) | Env vars, Nginx/TLS |
| [architecture.md](architecture.md) | Service topology |
| [byo-cicd.md](byo-cicd.md) | CI/CD automation |
| [troubleshooting.md](troubleshooting.md) | Common issues |

## Key artifacts

| Path | Role |
| --- | --- |
| `deploy/env/.env.template` | Env reference |
| `deploy/compose/local/` | Laptop stacks (dev, e2e) |
| `deploy/compose/remote/` | Server stacks (staging, production) |
| `deploy/docker/` | Dockerfiles, entrypoint, nginx |
| `deploy/scripts/` | Operator and CI scripts |

## CI

Tests only: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). Deploy template: [`.github/workflows/deploy.example.yml`](../../.github/workflows/deploy.example.yml).
