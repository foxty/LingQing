# Production Quick Start (Path A — Single VM)

Deploy LingQing to one Linux VM with Docker Compose. For tier overview, see [getting-started.md](getting-started.md). For local dev, see [dev-guide.md](../dev-guide.md).

## Prerequisites

- Linux VM with Docker Engine and Compose plugin
- Container registry (GHCR, ECR, ACR, etc.)
- Managed PostgreSQL reachable from the VM
- DNS: `app.example.com`, `manager.example.com`
- SSH access to the VM

## 1. Configure environment

```bash
cp deploy/env/.env.template .env.prod
```

Minimum edits:

| Variable | Example |
| --- | --- |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `TENANT_APP_DB_*` | PostgreSQL connection |
| `TENANT_MANAGER_DB_*` | Same or separate DB |
| `DATA_ROOT_HOST_PATH` | `/var/lib/lingqing/data` |
| `CORS_ORIGINS` | `https://app.example.com,https://manager.example.com` |
| `PORTAL_ORIGIN` | `https://app.example.com` |
| `TENANT_APP_API_ORIGIN` | `https://app.example.com` |

Full reference: [configuration.md](configuration.md).

## 2. Deploy

### Option A — Release bundle on VM (recommended, no repo clone)

Each semver tag publishes `lingqing-deploy-vX.Y.Z.tar.gz` on GitHub Releases. On the VM:

```bash
VERSION=v2.0.0
curl -fsSL "https://github.com/foxty/LingQing/releases/download/${VERSION}/lingqing-deploy-${VERSION}.tar.gz" | tar -xz
cd "lingqing-deploy-${VERSION}"
cp .env.template .env && nano .env
./bootstrap.sh --version "${VERSION}" --registry ghcr.io/foxty/lingqing
```

Full guide: [vm-bootstrap.md](vm-bootstrap.md).

### Option B — `deploy.sh` from laptop (SSH deploy)

When images already exist in the registry:

```bash
# Production (deploy only)
./deploy/scripts/generate-env.sh deploy/env/.env.template /tmp/.env.prod
./deploy/scripts/remote/deploy.sh v2.0.0 ghcr.io/foxty/lingqing your-vm deploy /tmp/.env.prod all production

# Staging
./deploy/scripts/remote/deploy.sh v2.0.0 ghcr.io/foxty/lingqing your-vm deploy .env.staging all staging
```

### Option C — `release.sh` (build locally + deploy)

Build images locally, push to registry, deploy to VM:

```bash
./deploy/scripts/remote/release.sh user@your-vm ghcr.io/yourorg/lingqing .env.prod v2.0.0 all
```

Use when you are developing/customizing images. For published GHCR tags, prefer Option A or B.

## 3. TLS and outer Nginx

Inner gateway listens on `127.0.0.1:8080`. Terminate TLS on the host and proxy to that port. See [configuration.md](configuration.md#outer-nginx-setup-merged).

## 4. Smoke checks

```bash
curl -fsS -H 'Host: app.example.com' http://127.0.0.1:8080/health
curl -fsS -H 'Host: manager.example.com' http://127.0.0.1:8080/health
```

## 5. First tenant

From a repo checkout:

```bash
uv run --env-file .env.prod scripts/tenant_cli.py create --name "Demo" --slug demo
```

On VM without repo clone:

```bash
APP_CONTAINER=$(docker ps --format '{{.Names}}' | grep tenant-app-service | head -n 1)
docker exec -it "$APP_CONTAINER" uv run --no-dev scripts/tenant_cli.py create --name "Demo" --slug demo
```

Skills sync automatically in Docker prod (`deploy/docker/entrypoint.sh`).

## Production checklist

- [ ] Unique `SECRET_KEY`
- [ ] `TENANT_APP_DB_SSL_MODE=require`
- [ ] Public URLs match `CORS_ORIGINS`, `PORTAL_ORIGIN`, `TENANT_APP_API_ORIGIN`
- [ ] Change default `admin` / `admin` password
- [ ] Backups for Postgres + `DATA_ROOT_HOST_PATH`
- [ ] LLM keys configured per tenant in Settings
- [ ] Firewall: only 443/80 public

## Upgrades

Re-run `bootstrap.sh` (VM), `deploy.sh` (SSH), or `release.sh` (local build) with a new `VERSION`.

## Next steps

- [configuration.md](configuration.md) — staging + production on one VM
- [byo-cicd.md](byo-cicd.md) — automate releases
- [troubleshooting.md](troubleshooting.md)
