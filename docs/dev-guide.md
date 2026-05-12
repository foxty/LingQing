# LingQing Development Guide

> **Production deployment** is documented separately: [deploy/quick-start.md](deploy/quick-start.md).

## Local setup (first time)

Complete the Python/uv environment before starting services.

### 1. Install uv

macOS (recommended):

```bash
brew install uv
```

Or use the official installer (macOS/Linux):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify:

```bash
uv --version
```

### 2. Install and pin Python 3.11

This repo requires Python 3.11 (`.python-version` is pinned to 3.11):

```bash
uv python install 3.11
uv python pin 3.11
python --version
```

### 3. Sync Python dependencies

From the repository root:

```bash
uv sync --all-groups
```

For default dependencies only:

```bash
uv sync
```

### 4. Environment file

```bash
cp deploy/env/.env.template .env.local
```

Edit `.env.local` per comments (database, ports, data directories, etc.).

## Two run modes

### Local development (recommended for daily work)

Run code locally with hot reload:

```bash
# Start infrastructure (PostgreSQL, Chroma, Sandbox; initializes DB)
./deploy/scripts/local-stack.sh infra-up

# Run migrations (first time or after schema changes)
npm run migrate-db:ta   # tenant app DB
npm run migrate-db:tm   # tenant manager DB

# Install frontend deps (required once)
cd apps/tenant_app_portal && npm install

# Run full app stack
npm run dev:ta   # frontend, tenant backend, scheduler, sandbox

# Create a tenant
npm run tenant-cli -- --name test --slug test
```

**One-time: skills directory symlink (required for local dev)**

Local dev does not use `entrypoint.sh`; symlink skills so the sandbox can read `config/skills`:

```bash
# Replace with DATA_ROOT_PATH from .env.local, e.g. /your/data/root
ln -sfn "$(pwd)/config/skills" "<DATA_ROOT_PATH>/skills"
```

> Docker modes (`local-stack.sh infra-up` / `stack-up`) copy skills automatically at `tenant-app-service` startup — no symlink needed.

**Benefits:**

- Code changes apply immediately (hot reload)
- Easy debugging
- Good IDE integration

---

### Full Docker stack (integration / E2E)

Complete containerized environment for system integration testing:

```bash
./deploy/scripts/local-stack.sh stack-up
# Optional health check after startup
./deploy/scripts/local-stack.sh smoke
```

**Duration:** 1–3 minutes (first image build takes longer)  
**Suggested flow:** stack-up → smoke → logs

**Benefits:**

- One-command full stack
- Production-like environment
- Minimal local configuration

---

## Access URLs

| Mode | Frontend | API | Database |
| --- | --- | --- | --- |
| **Local dev** | http://localhost:5173 | http://localhost:8000/docs | localhost:5432 |
| **Docker stack** | http://localhost | http://localhost:8000/docs | localhost:5432 |

---

## Local test account

Development/default tenant only — **never use in production**:

```
Username: admin
Password: admin
```

---

## Common commands

**Local development:**

```bash
npm run test:unit                # unit tests (same as pre-push)
npm run test                     # full Python test suite
uv run pytest tests/unit/ -v     # equivalent to test:unit
```

**Docker stack:**

```bash
./deploy/scripts/local-stack.sh stack-up    # start full Docker stack
./deploy/scripts/local-stack.sh smoke       # smoke checks
./deploy/scripts/local-stack.sh logs        # view logs
./deploy/scripts/local-stack.sh stack-down  # stop services
./deploy/scripts/local-stack.sh infra-up    # infra only (postgres, chroma, sandbox)
./deploy/scripts/local-stack.sh clean       # clean environment

# Create test tenant (requires local psql client)
uv run --env-file .env.local scripts/tenant_cli.py create --name "Name" --slug slug
```

---

## Database

| Item | Value |
| --- | --- |
| Host | localhost:5432 |
| App DB | lq_tenant_app / lq_tenant_app_db_user / (see `.env.local`) |
| Manager DB | lq_tenant_manager / lq_tenant_manager_db_user / (see `.env.local`) |
| Postgres superuser | postgres / postgres_dev_password |

---

## Quick checklist

- [ ] Docker & Docker Compose installed
- [ ] Python 3.11 (required by onnxruntime)
- [ ] uv installed (`uv --version`)
- [ ] PostgreSQL client installed (`psql --version`, for tenant creation)
- [ ] Ports 5432/8000/5173/8002/8090 available
- [ ] `.env.local` configured correctly

---

## Troubleshooting

| Issue | Fix |
| --- | --- |
| Postgres connection failed | `./deploy/scripts/local-stack.sh infra-up` |
| Port in use | `lsof -i :5432` to find the process |
| Missing Python packages | `uv sync` |
| Hot reload not working | Ensure files are saved in the editor |
| Docker build timeout | Check network; configure registry mirrors if needed |
| Repeated build failures | `docker system prune -a` then retry |

---

## Docker build issues

**Symptoms:** `DeadlineExceeded`, `dial tcp: i/o timeout`, or image pull failures.

1. Check disk: `docker system df`
2. Clear build cache: `docker builder prune -a`
3. Full reset (destructive): `docker system prune -a`
4. Retry: `./deploy/scripts/local-stack.sh stack-up` or rebuild with `docker compose build --no-cache`

For registry mirrors (some regions), see Docker Engine `registry-mirrors` in [deploy/troubleshooting.md](deploy/troubleshooting.md).

---

## Network issues

**Symptoms:** `dial tcp: i/o timeout` or `failed to resolve source metadata`

**Causes:**

- Unstable network
- Registry mirror needed in some regions
- Docker Hub rate limits

**Manual fix — Docker registry mirrors:**

```json
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
```

Apply in Docker Desktop → Settings → Docker Engine (macOS/Windows) or `/etc/docker/daemon.json` (Linux), restart Docker, then:

```bash
./deploy/scripts/local-stack.sh stack-up
```

See [deploy/troubleshooting.md](deploy/troubleshooting.md) for production deploy issues.

---
