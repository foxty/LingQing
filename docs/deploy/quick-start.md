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

## 2. Build and deploy

### Option A — `release.sh` (recommended for first production deploy)

Build images locally, push to registry, deploy to VM:

```bash
./deploy/scripts/remote/release.sh user@your-vm ghcr.io/yourorg/lingqing .env.prod v2.0.0 all
```

Arguments: `REMOTE_HOST REGISTRY_URL ENV_FILE [VERSION] [STACK]`

Always deploys **production** tier (`lingqing-production`, gateway port `8080`).

### Option B — `deploy.sh` (CI or deploy-only)

When images already exist, or for **staging**:

```bash
# Production (deploy only)
./deploy/scripts/generate-env.sh deploy/env/.env.template /tmp/.env.prod
./deploy/scripts/remote/deploy.sh v2.0.0 ghcr.io/yourorg/lingqing your-vm deploy /tmp/.env.prod all production

# Staging
./deploy/scripts/remote/deploy.sh v2.0.0 ghcr.io/yourorg/lingqing your-vm deploy .env.staging all staging
```

## 3. TLS and outer Nginx

Inner gateway listens on `127.0.0.1:8080`. Terminate TLS on the host and proxy to that port. See [configuration.md](configuration.md#outer-nginx-setup-merged).

## 4. Smoke checks

```bash
curl -fsS -H 'Host: app.example.com' http://127.0.0.1:8080/health
curl -fsS -H 'Host: manager.example.com' http://127.0.0.1:8080/health
```

## 5. First tenant

```bash
uv run --env-file .env.prod scripts/tenant_cli.py create --name "Demo" --slug demo
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

Re-run `release.sh` or `deploy.sh` with a new `VERSION`.

## Next steps

- [configuration.md](configuration.md) — staging + production on one VM
- [byo-cicd.md](byo-cicd.md) — automate releases
- [troubleshooting.md](troubleshooting.md)
