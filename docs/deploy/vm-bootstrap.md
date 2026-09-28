# VM Bootstrap (No Repo Clone)

Deploy LingQing on a Linux VM using pre-built images from GitHub Releases. You do not need to clone the repository.

## Prerequisites

- Linux VM with Docker Engine and Compose plugin
- Managed PostgreSQL reachable from the VM
- DNS: `app.example.com`, `manager.example.com`
- Outer Nginx (or similar) for TLS → `127.0.0.1:8080`
- GHCR packages set to **Public** (one-time, repo maintainer) for passwordless `docker pull`

## Option A — Release bundle (recommended)

Each semver tag publishes `lingqing-deploy-vX.Y.Z.tar.gz` on [GitHub Releases](https://github.com/foxty/LingQing/releases).

On the VM:

```bash
VERSION=v2.0.0
REGISTRY_URL=ghcr.io/foxty/lingqing

curl -fsSL "https://github.com/foxty/LingQing/releases/download/${VERSION}/lingqing-deploy-${VERSION}.tar.gz" | tar -xz
cd "lingqing-deploy-${VERSION}"
cp .env.template .env
nano .env   # SECRET_KEY, DB creds, DATA_ROOT_HOST_PATH, public URLs

./bootstrap.sh --version "${VERSION}" --registry "${REGISTRY_URL}"
```

Minimum `.env` edits:

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

## Option B — Bootstrap script only

If you prefer a single download step:

```bash
curl -fsSL https://github.com/foxty/LingQing/releases/download/v2.0.0/bootstrap.sh \
  | VERSION=v2.0.0 REGISTRY_URL=ghcr.io/foxty/lingqing GITHUB_REPO=foxty/LingQing bash
```

The script downloads the release bundle, creates `.env` from the template if missing, and exits so you can edit secrets. Re-run the same command after editing `.env`.

## Staging on the same VM

```bash
./bootstrap.sh \
  --version v2.0.0 \
  --registry ghcr.io/foxty/lingqing \
  --tier staging \
  --dir ~/lingqing-deploy/staging
```

Staging gateway: `127.0.0.1:18080`. See [configuration.md](configuration.md#outer-nginx-setup-merged).

## TLS and smoke checks

Inner gateway binds to localhost. Terminate TLS on the host and proxy to port `8080` (production) or `18080` (staging).

```bash
curl -fsS -H 'Host: app.example.com' http://127.0.0.1:8080/health
curl -fsS -H 'Host: manager.example.com' http://127.0.0.1:8080/health
```

## First tenant (no repo clone)

The backend image includes `tenant_cli.py`:

```bash
APP_CONTAINER=$(docker ps --format '{{.Names}}' | grep tenant-app-service | head -n 1)
docker exec -it "$APP_CONTAINER" uv run --no-dev scripts/tenant_cli.py create --name "Demo" --slug demo
```

Login: `admin@demo` / `admin` — change immediately in production.

## Upgrade

From the same deploy directory:

```bash
./bootstrap.sh --version v2.1.0 --registry ghcr.io/foxty/lingqing
```

## Private GHCR packages

If packages are not public, log in on the VM before bootstrap:

```bash
echo "$GITHUB_PAT" | docker login ghcr.io -u USERNAME --password-stdin
```

PAT requires `read:packages`.

## Related

- [quick-start.md](quick-start.md) — full production checklist
- [getting-started.md](getting-started.md) — deploy paths overview
- [byo-cicd.md](byo-cicd.md) — automate with CI
