# Deployment Getting Started

Use this page to pick the right path. Full layout reference: [deploy/README.md](../../deploy/README.md).

LingQing is **self-hosted** — you provide PostgreSQL (remote tiers), a container registry, host(s), domains, and TLS.

## Two axes: target vs tier

| Axis | Question | Where it lives |
| --- | --- | --- |
| **Target** | Where does it run? | `compose/local/` vs `compose/remote/` |
| **Tier** | What is it for? | Env file + deploy flag |

```text
                 TARGET
              local          remote
           ┌─────────────┬──────────────────┐
   dev     │ infra.yml   │                  │
           │ + npm dev   │                  │
TIER       ├─────────────┼──────────────────┤
   e2e     │ full-stack  │                  │
           ├─────────────┼──────────────────┤
   staging │             │ stack + override │
           ├─────────────┼──────────────────┤
   prod    │             │ stack.yml        │
           └─────────────┴──────────────────┘
```

## All tiers

| Tier | Target | Compose | Env file | Command |
| --- | --- | --- | --- | --- |
| **dev** | Laptop | `compose/local/infra.yml` | `.env.local` | `./deploy/scripts/local-stack.sh infra-up` |
| **e2e** | Laptop | `compose/local/full-stack.yml` | `.env.e2e` | `./deploy/scripts/local-stack.sh stack-up` |
| **staging** | Remote VM | `remote/stack.yml` + `overrides/staging.yml` | `.env.staging` | `./deploy/scripts/remote/deploy.sh … staging` |
| **production** | Remote VM | `compose/remote/stack.yml` | `.env.prod` | `./deploy/scripts/remote/release.sh …` |

Staging and production share the same remote stack; staging adds port `18080` via override.

---

## Scripts

| Script | Purpose |
| --- | --- |
| `deploy/scripts/local-stack.sh` | Local dev infra + E2E full stack |
| `deploy/scripts/build-backend.sh` | Build/push backend + sandbox images |
| `deploy/scripts/build-frontend.sh` | Build/push frontend gateway image |
| `deploy/scripts/generate-env.sh` | Materialize env from template (CI) |
| `deploy/scripts/remote/deploy.sh` | Remote deploy (`staging` or `production`) |
| `deploy/scripts/remote/release.sh` | Build + push + production deploy from laptop |

### `release.sh` vs `deploy.sh`

| | `release.sh` | `deploy.sh` |
| --- | --- | --- |
| **Runs on** | Your laptop | CI runner or laptop |
| **Builds images** | Yes | No (pulls existing) |
| **Tier** | Production only | Staging or production |
| **Use when** | First manual prod deploy | CI, or staging deploy |

```bash
# Production release (build + deploy)
./deploy/scripts/remote/release.sh user@prod-vm ghcr.io/org/lingqing .env.prod v2.0.0 all

# Staging (deploy only)
./deploy/scripts/remote/deploy.sh v2.0.0 ghcr.io/org/lingqing staging-vm deploy .env.staging all staging

# Production (deploy only — images already built)
./deploy/scripts/remote/deploy.sh v2.0.0 ghcr.io/org/lingqing prod-vm deploy .env.prod all production
```

Tier aliases: `test` → `staging`, `prod` → `production`.

---

## Local dev (tier: dev)

Hot-reload development — see [dev-guide.md](../dev-guide.md).

```bash
cp deploy/env/.env.template .env.local
./deploy/scripts/local-stack.sh infra-up
npm run migrate-db:ta
npm run dev:ta
npm run tenant-cli -- create --name "Demo" --slug demo
```

## Local E2E (tier: e2e)

Full Docker stack on laptop — no registry or SSH.

```bash
cp deploy/env/.env.template deploy/env/.env.e2e
# Edit .env.e2e: TENANT_APP_DB_HOST=postgres, TENANT_APP_DB_PORT=5432, CHROMA_URL=http://chroma:8000, …
# Host ports (5433 postgres, 18080 gateway) are fixed in full-stack.yml

./deploy/scripts/local-stack.sh stack-up
./deploy/scripts/local-stack.sh smoke

TENANT_APP_DB_HOST=localhost TENANT_APP_DB_PORT=5433 npm run migrate-db:ta
TENANT_APP_DB_HOST=localhost TENANT_APP_DB_PORT=5433 npm run tenant-cli -- create --name "Demo" --slug demo
# tenant-cli materializes platform system jobs (Scheduled Tasks) for the new tenant
```

If you created a tenant **before** this step on an older stack, restart the scheduler once to backfill system jobs:

```bash
docker restart lingqing-e2e-scheduler-service
```

See [deploy/README.md](../../deploy/README.md#e2e-host-ports-fixed-in-compose). Add `127.0.0.1 app-test.example.com manager-test.example.com` to `/etc/hosts` → http://app-test.example.com:18080

## Remote staging + production

**You provide:** PostgreSQL, registry, VM, DNS, outer Nginx/TLS, `DATA_ROOT_HOST_PATH`.

Migrations run on container start (`deploy/docker/entrypoint.sh`).

Recommended rollout:

```text
1. E2E on laptop (optional)
2. remote/deploy.sh … staging
3. remote/release.sh … production
4. CI/CD → byo-cicd.md
```

### Staging + production on one VM

| | Staging | Production |
| --- | --- | --- |
| Project | `lingqing-staging` | `lingqing-production` |
| Gateway | `127.0.0.1:18080` | `127.0.0.1:8080` |
| Env | `.env.staging` | `.env.prod` |

Outer Nginx examples: [configuration.md](configuration.md#outer-nginx-setup-merged).

---

## After deploy: first tenant

```bash
uv run --env-file .env.prod scripts/tenant_cli.py create --name "Demo" --slug demo
```

Login: `admin@demo` / `admin` — change immediately in production.

---

## Next steps

| Goal | Document |
| --- | --- |
| Production step-by-step | [quick-start.md](quick-start.md) |
| Env vars, Nginx | [configuration.md](configuration.md) |
| Topology | [architecture.md](architecture.md) |
| CI/CD | [byo-cicd.md](byo-cicd.md) |
| Local dev details | [dev-guide.md](../dev-guide.md) |
| Issues | [troubleshooting.md](troubleshooting.md) |
