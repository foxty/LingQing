# Deploy layout

**Procedure & troubleshooting:** [docs/deploy/guide.md](../docs/deploy/guide.md) · **Reference (env, Postgres, Nginx):** [docs/deploy/reference.md](../docs/deploy/reference.md) · **CI/CD:** [docs/deploy/byo-cicd.md](../docs/deploy/byo-cicd.md)

## Image / release tags in examples

Deploy scripts take an image tag that matches a **git semver tag** (`vX.Y.Z`) or a daily tag (`daily`, `daily-YYYY-MM-DD`). Examples use shell variables — set them from [GitHub Releases](https://github.com/foxty/LingQing/releases) or your registry, not from stale doc copy:

```bash
VERSION=vX.Y.Z                              # e.g. latest release tag
REGISTRY=ghcr.io/<org>/lingqing             # your registry namespace
GITHUB_ORG_REPO=<org>/<repo>                # for release bundle curl
```

Repo `package.json` / root `pyproject.toml` `version` is the product version; the tag you deploy must exist in the registry.

## Directory structure

```text
deploy/
├── README.md              ← you are here
├── env/
│   ├── .env.template              # full env reference (all tiers)
│   ├── .env.production.template   # minimal remote VM env (bootstrap checklist + defaults; shipped as .env.template in bundle)
│   └── .env.e2e                   # E2E container config (create from template; not committed)
├── docker/                # Dockerfiles, entrypoint, inner nginx, egress-proxy (Squid)
├── compose/
│   ├── local/
│   │   ├── infra.yml      # tier: dev (Postgres + Chroma)
│   │   └── full-stack.yml # tier: e2e (all services + Postgres)
│   └── remote/
│       └── stack.yml      # remote VM stack (prod or staging — one VM per env)
└── scripts/
    ├── local-stack.sh     # local dev + e2e
    ├── build-backend.sh
    ├── build-frontend.sh
    ├── generate-env.sh
    ├── package-release-bundle.sh  # CI: tarball for GitHub Releases
    └── remote/
        ├── host-deploy.sh   # on-host deploy (shipped as bootstrap.sh)
        ├── deploy.sh        # remote pull + compose up (SSH from laptop)
        └── release.sh       # build + push + deploy (production)
```

## Tiers at a glance

| Tier | Target | Compose | Env file | Command |
| --- | --- | --- | --- | --- |
| **dev** | Laptop | `compose/local/infra.yml` | `.env.local` | `scripts/local-stack.sh infra-up` |
| **e2e** | Laptop | `compose/local/full-stack.yml` | `deploy/env/.env.e2e` | `scripts/local-stack.sh stack-up` |
| **remote** | Remote VM | release bundle or `remote/stack.yml` | `.env` / `.env.prod` | `remote/host-deploy.sh` or `remote/deploy.sh …` |

**Folder = where** (local vs remote). **Tier = purpose** (dev/e2e on laptop; prod/staging on separate VMs with different `.env`).

## Common commands

```bash
# Local dev infra
cp deploy/env/.env.template .env.local
./deploy/scripts/local-stack.sh infra-up
npm run dev:ta

# Local E2E full stack
cp deploy/env/.env.template deploy/env/.env.e2e   # container config: DB host=postgres, port=5432, …
./deploy/scripts/local-stack.sh stack-up
./deploy/scripts/local-stack.sh smoke

# Remote VM: provision PostgreSQL first (./init_db.sh in release bundle — see docs/deploy/reference.md#postgresql-external)

# VM deploy from GitHub Release bundle (init_db.sh + .env.template + bootstrap.sh)
curl -fsSL "https://github.com/${GITHUB_ORG_REPO}/releases/download/${VERSION}/lingqing-deploy-${VERSION}.tar.gz" | tar -xz
cd "lingqing-deploy-${VERSION}"
cp .env.template .env && $EDITOR .env
./bootstrap.sh --version "${VERSION}" --registry "${REGISTRY}"

# Production deploy from laptop (SSH)
cp deploy/env/.env.template .env.prod
./deploy/scripts/remote/deploy.sh "${VERSION}" "${REGISTRY}" your-vm deploy .env.prod all

# Local build + production release from laptop
./deploy/scripts/remote/release.sh user@your-vm "${REGISTRY}" .env.prod "${VERSION}" all
```

## Local tiers in detail

**dev** — `infra.yml` starts Postgres, Chroma, optional Docling, **egress-proxy** (always on), and builds the sandbox runner image. App code runs on the host via `npm run dev:ta`. For sandbox egress on the local controller: `EGRESS_PROXY_URL=http://egress-proxy:3128`, `SANDBOX_RUNNER_NETWORK_MODE=lingqing_egress-clients`, and `SANDBOX_RUNNER_API_BASE_URL=http://host.docker.internal:8000` in `.env.local`.

Egress: `${REGISTRY_URL}/egress-proxy:${VERSION}` (Squid config baked in image). Host only `${DATA_ROOT_HOST_PATH}/egress/` for `domains.custom.txt` + `logs/`. Reload after custom allowlist edits: `./deploy/scripts/egress-proxy-reload.sh`.

**e2e** — `full-stack.yml` is a self-contained Docker stack (separate Postgres container/volumes from dev).

### E2E host ports (fixed in compose)

E2E uses **fixed host ports** in `full-stack.yml` so dev and E2E can run together without env conflicts:

| Host access | Port | Notes |
| --- | --- | --- |
| Gateway | `18080` | Browser entry (`app-test.example.com`) |
| Postgres | `5433` | Migrate/tenant-cli from laptop only |

Internal services (app, manager, chroma, docling, sandbox) are **not** published to the host — containers talk over the Docker network. `.env.e2e` uses internal values only (`TENANT_APP_DB_HOST=postgres`, `TENANT_APP_DB_PORT=5432`).

**Tenant CLI from laptop** (after `stack-up`; Alembic already runs in backend entrypoint):

```bash
TENANT_APP_DB_HOST=localhost TENANT_APP_DB_PORT=5433 npm run tenant-cli -- create --name "Demo" --slug demo
```

Optional debug only: `npm run migrate-db:ta` with the same `TENANT_APP_DB_*` host overrides.
