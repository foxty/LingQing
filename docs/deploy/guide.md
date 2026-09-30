# Deployment Guide

Operator guide: choose a path, deploy to a remote VM, troubleshoot. Env vars, PostgreSQL, Nginx, and topology → [reference.md](reference.md).

Local development details → [dev-guide.md](../dev-guide.md). Repo layout → [deploy/README.md](../../deploy/README.md).

## Choose a path

| Path | Audience | Entry |
| --- | --- | --- |
| **Local dev** | Developers | [Local development](#local-development) |
| **Local E2E** | Smoke / integration | [Local E2E](#local-e2e) |
| **Remote VM** | Production / staging | [Production deploy](#production-deploy) |
| **CI/CD** | Platform engineers | [byo-cicd.md](byo-cicd.md) |

## Tiers at a glance

| Tier | Target | Compose | Env file | Command |
| --- | --- | --- | --- | --- |
| **dev** | Laptop | `compose/local/infra.yml` | `.env.local` | `./deploy/scripts/local-stack.sh infra-up` |
| **e2e** | Laptop | `compose/local/full-stack.yml` | `.env.e2e` | `./deploy/scripts/local-stack.sh stack-up` |
| **remote** | Remote VM | release bundle or `remote/stack.yml` | `.env` / `.env.prod` | `./bootstrap.sh` or `./deploy/scripts/remote/deploy.sh …` |

Staging and production use the **same** remote stack on **separate VMs**; only `.env` differs.

## Scripts

| Script | Purpose |
| --- | --- |
| `deploy/scripts/local-stack.sh` | Local dev infra + E2E full stack |
| `deploy/scripts/build-backend.sh` | Build/push backend + sandbox images |
| `deploy/scripts/build-frontend.sh` | Build/push frontend gateway image |
| `deploy/scripts/generate-env.sh` | Materialize env from template (CI) |
| `deploy/scripts/remote/deploy.sh` | Remote deploy via SSH (pull + compose up) |
| `deploy/scripts/remote/host-deploy.sh` | On-host deploy from release bundle (shipped as `bootstrap.sh`) |
| `deploy/scripts/remote/release.sh` | Build + push + deploy from laptop |
| `deploy/scripts/package-release-bundle.sh` | Build release tarball (CI) |

### `release.sh` vs `deploy.sh`

| | `release.sh` | `deploy.sh` |
| --- | --- | --- |
| **Runs on** | Your laptop | CI runner or laptop |
| **Builds images** | Yes | No (pulls existing) |
| **Use when** | First manual deploy (build + push) | CI or deploy-only (images exist) |

```bash
# Build + deploy
./deploy/scripts/remote/release.sh user@vm ghcr.io/org/lingqing .env.prod v2.0.0 all

# Deploy only (images already in registry)
./deploy/scripts/remote/deploy.sh v2.0.0 ghcr.io/org/lingqing vm deploy .env.prod all
```

---

## Local development

Hot-reload development — see [dev-guide.md](../dev-guide.md).

```bash
cp deploy/env/.env.template .env.local
./deploy/scripts/local-stack.sh infra-up
npm run migrate-db:ta
npm run dev:ta
npm run tenant-cli -- create --name "Demo" --slug demo
```

## Local E2E

Full Docker stack on laptop — no registry or SSH.

```bash
cp deploy/env/.env.template deploy/env/.env.e2e
# Edit .env.e2e: TENANT_APP_DB_HOST=postgres, TENANT_APP_DB_PORT=5432, CHROMA_URL=http://chroma:8000, …

./deploy/scripts/local-stack.sh stack-up
./deploy/scripts/local-stack.sh smoke

TENANT_APP_DB_HOST=localhost TENANT_APP_DB_PORT=5433 npm run migrate-db:ta
TENANT_APP_DB_HOST=localhost TENANT_APP_DB_PORT=5433 npm run tenant-cli -- create --name "Demo" --slug demo
```

Host ports are fixed in `full-stack.yml` (Postgres `5433`, gateway `18080`). See [deploy/README.md](../../deploy/README.md#e2e-host-ports-fixed-in-compose).

---

## Production deploy

Deploy LingQing to one Linux VM with Docker Compose. Use a **dedicated VM per environment** (prod vs staging).

### Prerequisites

- Linux VM with Docker Engine and Compose plugin
- Container registry (GHCR, ECR, ACR, etc.)
- **PostgreSQL provisioned and initialized** ([reference → PostgreSQL](reference.md#postgresql-external))
- DNS: `app.example.com`, `manager.example.com`
- SSH access to the VM (for Options B/C)

### 1. Prepare PostgreSQL

The remote stack does **not** include PostgreSQL. Provision it and run `./init_db.sh` (included in the release bundle) **before** deploying the app VM.

→ **[reference.md → PostgreSQL](reference.md#postgresql-external)**

### 2. Configure environment

```bash
cp deploy/env/.env.production.template .env.prod
```

Or use `.env.template` from the release bundle. Fill secrets, PostgreSQL (`TENANT_APP_DB_*`, `TENANT_MANAGER_DB_*`), `DATA_ROOT_HOST_PATH`, and public URLs.

`bootstrap.sh` derives `CORS_ORIGINS`, `PORTAL_ORIGIN`, and `TENANT_APP_API_ORIGIN` from `APP_PUBLIC_URL` and `MANAGER_PUBLIC_URL`.

Full variable reference: [reference.md](reference.md).

### 3. Deploy

#### Option A — Release bundle on VM (recommended, no repo clone)

Each semver tag publishes `lingqing-deploy-vX.Y.Z.tar.gz` on GitHub Releases (includes `init_db.sh`, `.env.template`, `bootstrap.sh`):

```bash
VERSION=v2.0.0
curl -fsSL "https://github.com/foxty/LingQing/releases/download/${VERSION}/lingqing-deploy-${VERSION}.tar.gz" | tar -xz
cd "lingqing-deploy-${VERSION}"

# Once: initialize PostgreSQL (from laptop; needs psql + admin access)
export POSTGRES_HOST=your-db.example.com POSTGRES_USER=postgres PGPASSWORD=admin_pass
./init_db.sh 'app_pass' 'manager_pass'

cp .env.template .env && nano .env   # fill "FILL BEFORE DEPLOY" section
./bootstrap.sh --version "${VERSION}" --registry ghcr.io/foxty/lingqing
```

**Upgrade** (from the bundle directory):

```bash
./bootstrap.sh --version v2.1.0 --registry ghcr.io/foxty/lingqing
```

**Private GHCR packages:**

```bash
echo "$GITHUB_PAT" | docker login ghcr.io -u USERNAME --password-stdin
```

PAT requires `read:packages`.

#### Option B — `deploy.sh` from laptop (SSH deploy)

When images already exist in the registry:

```bash
./deploy/scripts/generate-env.sh deploy/env/.env.template /tmp/.env.prod
./deploy/scripts/remote/deploy.sh v2.0.0 ghcr.io/foxty/lingqing your-vm deploy /tmp/.env.prod all
```

#### Option C — `release.sh` (build locally + deploy)

```bash
./deploy/scripts/remote/release.sh user@your-vm ghcr.io/yourorg/lingqing .env.prod v2.0.0 all
```

Use when customizing images. For published GHCR tags, prefer Option A or B.

### 4. TLS and outer Nginx

Inner gateway listens on `127.0.0.1:8080`. Terminate TLS on the host and proxy to that port.

→ [reference.md → Outer Nginx](reference.md#outer-nginx)

### 5. Smoke checks

```bash
curl -fsS -H 'Host: app.example.com' http://127.0.0.1:8080/health
curl -fsS -H 'Host: manager.example.com' http://127.0.0.1:8080/health
```

### 6. First tenant

From a repo checkout:

```bash
uv run --env-file .env.prod scripts/tenant_cli.py create --name "Demo" --slug demo
```

On VM without repo clone:

```bash
APP_CONTAINER=$(docker ps --format '{{.Names}}' | grep tenant-app-service | head -n 1)
docker exec -it "$APP_CONTAINER" uv run --no-dev scripts/tenant_cli.py create --name "Demo" --slug demo
```

Login: `admin@demo` / `admin` — change immediately in production.

### Production checklist

- [ ] PostgreSQL reachable from app VM; `init_db.sh` completed
- [ ] Unique `SECRET_KEY`
- [ ] `TENANT_APP_DB_SSL_MODE=require` (and manager DB if separate)
- [ ] `APP_PUBLIC_URL` and `MANAGER_PUBLIC_URL` set in `.env`
- [ ] Change default `admin` / `admin` password
- [ ] Backups for Postgres + `DATA_ROOT_HOST_PATH`
- [ ] LLM keys configured per tenant in Settings
- [ ] Firewall: only 443/80 public

### Upgrades

Re-run `bootstrap.sh` (VM), `deploy.sh` (SSH), or `release.sh` (local build) with a new `VERSION`.

---

## Troubleshooting

### App or manager container exits / migration errors

```bash
docker logs "$(docker ps -a --format '{{.Names}}' | grep tenant-app-service | head -n 1)" 2>&1 | tail -50
```

Common causes: PostgreSQL unreachable, `init_db.sh` not run, wrong `.env` credentials, empty `TENANT_MANAGER_DB_HOST` when sharing one PG server, or SSL mode mismatch.

→ [reference.md → PostgreSQL](reference.md#postgresql-external)

### Manager domain opens app portal

Outer Nginx must preserve the host header:

```nginx
proxy_set_header Host $host;
```

Verify inner gateway `server_name` includes manager domains (`deploy/docker/nginx.conf`).

### Direct access to 127.0.0.1:8080 shows default site

Expected for default vhost. Verify with explicit host header:

```bash
curl -H 'Host: app.example.com' http://127.0.0.1:8080/health
curl -H 'Host: manager.example.com' http://127.0.0.1:8080/health
```

### Manager portal works but manager API fails

1. `tenant-manager-service` is healthy
2. Inner gateway maps manager host `/api` → `tenant-manager-service:8010`
3. Frontend uses relative API base `/api`

### CI did not deploy manager changes

Run workflow manually with `deploy_stack=manager`.

### Docker registry pull slow or blocked

Configure Docker Engine `registry-mirrors` (region-dependent), then restart Docker:

```json
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
```
