# Deploy layout

Full guides: [docs/deploy/getting-started.md](../docs/deploy/getting-started.md)

## Directory structure

```text
deploy/
├── README.md              ← you are here
├── env/
│   ├── .env.template      # env reference (all tiers)
│   └── .env.e2e           # E2E container config (create from template; not committed)
├── docker/                # Dockerfiles, entrypoint, inner nginx
├── compose/
│   ├── local/
│   │   ├── infra.yml      # tier: dev (Postgres + Chroma)
│   │   └── full-stack.yml # tier: e2e (all services + Postgres)
│   └── remote/
│       ├── stack.yml      # tier: staging + production
│       └── overrides/
│           └── staging.yml
└── scripts/
    ├── local-stack.sh     # local dev + e2e
    ├── build-backend.sh
    ├── build-frontend.sh
    ├── generate-env.sh
    ├── package-release-bundle.sh  # CI: tarball for GitHub Releases
    └── remote/
        ├── host-deploy.sh   # on-host deploy from release bundle (shipped as bootstrap.sh)
        ├── deploy.sh      # remote pull + compose up (SSH from laptop)
        └── release.sh     # build + push + deploy (production)
```

## Tiers at a glance

| Tier | Target | Compose | Env file | Command |
| --- | --- | --- | --- | --- |
| **dev** | Laptop | `compose/local/infra.yml` | `.env.local` | `scripts/local-stack.sh infra-up` |
| **e2e** | Laptop | `compose/local/full-stack.yml` | `env/.env.e2e` | `scripts/local-stack.sh stack-up` |
| **staging** | Remote VM | `compose/remote/stack.yml` + override | `.env.staging` | `scripts/remote/deploy.sh … staging` |
| **production** | Remote VM | release bundle or `remote/stack.yml` | `.env` / `.env.prod` | `remote/host-deploy.sh` or `remote/deploy.sh …` |

**Folder = where** (local vs remote). **Tier = purpose** (env file + deploy flag).

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

# Production on VM (no repo clone — from GitHub Release bundle)
curl -fsSL https://github.com/foxty/LingQing/releases/download/v2.0.0/lingqing-deploy-v2.0.0.tar.gz | tar -xz
cd lingqing-deploy-v2.0.0 && cp .env.template .env && ./bootstrap.sh --version v2.0.0 --registry ghcr.io/foxty/lingqing

# Production deploy from laptop (SSH)
cp deploy/env/.env.template .env.prod
./deploy/scripts/remote/deploy.sh v2.0.0 ghcr.io/foxty/lingqing user@vm deploy .env.prod all production

# Local build + production release from laptop
./deploy/scripts/remote/release.sh user@vm ghcr.io/org/lingqing .env.prod v2.0.0 all
```

## Local tiers in detail

**dev** — `infra.yml` starts Postgres, Chroma, optional Docling, and builds the sandbox runner image. App code runs on the host via `npm run dev:ta`.

**e2e** — `full-stack.yml` is a self-contained Docker stack (separate Postgres container/volumes from dev).

### E2E host ports (fixed in compose)

E2E uses **fixed host ports** in `full-stack.yml` so dev and E2E can run together without env conflicts:

| Host access | Port | Notes |
| --- | --- | --- |
| Gateway | `18080` | Browser entry (`app-test.example.com`) |
| Postgres | `5433` | Migrate/tenant-cli from laptop only |

Internal services (app, manager, chroma, docling, sandbox) are **not** published to the host — containers talk over the Docker network. `.env.e2e` uses internal values only (`TENANT_APP_DB_HOST=postgres`, `TENANT_APP_DB_PORT=5432`).

**Migrate / tenant-cli from laptop**:

```bash
TENANT_APP_DB_HOST=localhost TENANT_APP_DB_PORT=5433 npm run migrate-db:ta
TENANT_APP_DB_HOST=localhost TENANT_APP_DB_PORT=5433 npm run tenant-cli -- create --name "Demo" --slug demo
```
