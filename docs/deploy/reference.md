# Deployment Reference

Look up topology, PostgreSQL, env vars, ports, and outer Nginx/TLS. Step-by-step deploy → [guide.md](guide.md).

## Topology

Supported production layout: Docker Compose on a single VM (or equivalent host).

```text
Internet
  -> Outer Nginx (TLS + public domains)
     - app.example.com      -> 127.0.0.1:8080
     - manager.example.com  -> 127.0.0.1:8080

  -> gateway-service (inner Nginx in frontend image)
     - app host     -> /usr/share/nginx/html/app + /api -> tenant-app-service:8000
     - manager host -> /usr/share/nginx/html/manager + /api -> tenant-manager-service:8010

  -> Backend services (same Docker network)
     - tenant-app-service      (APP_MODULE=tenant_app_service)
     - tenant-manager-service  (APP_MODULE=tenant_manager_service)
     - scheduler-service       (APP_MODULE=scheduler_service)
     - sandbox-controller + chroma (+ optional docling-serve)

  -> External PostgreSQL
```

### Design decisions

1. **Host-based routing** — each portal has its own domain; avoids SPA base-path complexity.
2. **One frontend gateway image** — both portal builds (`/app` and `/manager`).
3. **Independent stacks** — deploy `app`, `manager`, or `all` (see [Deployment axes](#deployment-axes)).
4. **One VM per environment** — staging and production use the same stack on separate hosts; only `.env` differs.

### Stack definitions

| Stack | Services |
| --- | --- |
| `app` | `tenant-app-service`, `scheduler-service`, `gateway-service`, infra (chroma, sandbox, …) |
| `manager` | `tenant-manager-service`, `gateway-service` |
| `all` | Full production stack |

### Images

Built by `deploy/scripts/build-backend.sh` and `deploy/scripts/build-frontend.sh`:

| Image | Contents |
| --- | --- |
| `backend-app` | Python backend; module selected via `APP_MODULE` |
| `frontend` | Both portals + inner Nginx (`deploy/docker/nginx.conf`) |
| `sandbox-controller`, `sandbox-runner` | Agent code execution |

Kubernetes/Helm manifests are not included. A future K8s deployment should preserve the same **host-based routing contract**.

## Deployment axes

- **Environment:** separate VMs for staging vs production (same stack, different `.env`)
- **Stack:** `all`, `app`, `manager`

## PostgreSQL (external)

Remote deploy (`deploy/compose/remote/stack.yml`) expects **external PostgreSQL**. Local dev/E2E embed Postgres in Docker; production does not.

### What LingQing needs

| Resource | Env vars | Default |
| --- | --- | --- |
| App database | `TENANT_APP_DB_*` | DB `lq_tenant_app`, user `lq_tenant_app_db_user` |
| Manager database | `TENANT_MANAGER_DB_*` | DB `lq_tenant_manager`, user `lq_tenant_manager_db_user` |

Both databases can live on the **same PostgreSQL instance**. Set `TENANT_MANAGER_DB_HOST` to the same hostname as `TENANT_APP_DB_HOST` when they share a server.

Minimum version: **PostgreSQL 14+** (16 matches local compose images).

### Operator workflow

```text
1. Provision PostgreSQL (managed service or self-hosted)
2. Allow app VM → PostgreSQL (firewall / security group / authorized networks)
3. Run init_db.sh (creates databases + users)
4. Deploy app stack (migrations run on container start)
5. Create first tenant
```

### Initialize databases and users

Use `./init_db.sh` from the release bundle, or `scripts/init_db.sh` from a repo checkout. It is idempotent (safe to re-run).

```bash
export POSTGRES_HOST=your-db.example.com
export POSTGRES_PORT=5432
export POSTGRES_USER=postgres       # admin user with CREATE DATABASE privilege
export PGPASSWORD=admin_password

./scripts/init_db.sh 'app_user_password' 'manager_user_password'
```

Arguments are the **application** passwords (not the admin password). Put them in `.env`:

```bash
TENANT_APP_DB_HOST=your-db.example.com
TENANT_APP_DB_PASSWORD=app_user_password
TENANT_MANAGER_DB_HOST=your-db.example.com
TENANT_MANAGER_DB_PASSWORD=manager_user_password
TENANT_APP_DB_SSL_MODE=require
TENANT_MANAGER_DB_SSL_MODE=require
```

**Schema migrations** (Alembic) run automatically in `deploy/docker/entrypoint.sh` when `tenant-app-service` and `tenant-manager-service` start. You do not run `npm run migrate-db:ta` on the VM unless debugging.

### Managed PostgreSQL notes

| Provider | Typical steps |
| --- | --- |
| AWS RDS | Create instance → VPC security group allows app VM → run `init_db.sh` from bastion or laptop with VPN |
| GCP Cloud SQL | Enable public IP or Private IP + VPC peering → authorized networks → `init_db.sh` |
| Azure Database for PostgreSQL | Firewall rules for app VM → admin user may not be `postgres`; set `POSTGRES_USER` accordingly |

Enable automated backups and point-in-time recovery in production.

### Self-hosted PostgreSQL

Run PostgreSQL on a dedicated VM or existing cluster (not in the LingQing compose stack). Same `init_db.sh` flow; ensure the app VM can reach the host on `5432`.

### Connectivity check

From the app VM (or laptop):

```bash
psql "host=${POSTGRES_HOST} port=5432 dbname=lq_tenant_app user=lq_tenant_app_db_user sslmode=require"
```

If this fails, fix networking or credentials before running `bootstrap.sh`.

## Service names

- `tenant-app-service`: app backend (`APP_MODULE=tenant_app_service`)
- `tenant-manager-service`: manager backend (`APP_MODULE=tenant_manager_service`)
- `scheduler-service`: background scheduler
- `gateway-service`: shared frontend gateway (contains both app and manager portals)

## Domain routing

Inner gateway config in `deploy/docker/nginx.conf`:

- `app.example.com` and `app-test.example.com`
  - static root: `/usr/share/nginx/html/app`
  - API proxy: `/api -> http://tenant-app-service:8000/`
- `manager.example.com` and `manager-test.example.com`
  - static root: `/usr/share/nginx/html/manager`
  - API proxy: `/api -> http://tenant-manager-service:8010/`

## Port strategy

Internal container ports are fixed (app `8000`, manager `8010`, gateway `80`, sandbox `8090`, chroma `8000`, postgres `5432`). Env vars are **connection endpoints** for apps, not compose host bindings — except where noted.

| Tier | Host-published | Env vars (connection) |
| --- | --- | --- |
| **dev** (`infra.yml`) | Postgres `${TENANT_APP_DB_PORT}`, Chroma `8002`, Docling `${DOCLING_HOST_PORT}` | `.env.local`: `CHROMA_URL=http://localhost:8002`, `TENANT_APP_DB_PORT=5432` |
| **e2e** (`full-stack.yml`) | Postgres `5433`, Gateway `18080` (fixed in YAML) | `.env.e2e`: `CHROMA_URL=http://chroma:8000`, `TENANT_APP_DB_PORT=5432` |
| **remote VM** (`stack.yml`) | Gateway `${GATEWAY_SERVICE_PORT:-8080}` | `.env.prod`: docker service names |

Remote default in `deploy/compose/remote/stack.yml`:

- `gateway-service` publishes `127.0.0.1:${GATEWAY_SERVICE_PORT:-8080}:80`

Notes:

- Bind to localhost for same-VM outer Nginx topology.
- Outer Nginx must preserve host header: `proxy_set_header Host $host;`

## Outer Nginx

Use outer Nginx (host machine) as the public entrypoint, forwarding to the inner gateway exposed by Docker Compose.

Routing target port: `127.0.0.1:8080` (or `127.0.0.1:${GATEWAY_SERVICE_PORT}`).

Example production VM config (`/etc/nginx/conf.d/lingqing-gateway.conf`):

```nginx
map $http_upgrade $connection_upgrade {
  default upgrade;
  ''      close;
}

server {
  listen 80;
  server_name app.example.com manager.example.com;

  location / {
    return 301 https://$host$request_uri;
  }
}

server {
  listen 443 ssl http2;
  server_name app.example.com manager.example.com;

  ssl_certificate cert/_.example.com.cer;
  ssl_certificate_key cert/_.example.com.key;
  ssl_session_timeout 1d;
  ssl_session_cache shared:SSL:10m;
  ssl_session_tickets off;
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_prefer_server_ciphers off;

  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

  location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_read_timeout 300s;
  }
}
```

On a **separate staging VM**, duplicate with `app-test.example.com` / `manager-test.example.com` in `server_name` (still proxy to `127.0.0.1:8080` on that host).

Certificate management:

- Preconfigured wildcard: `cert/_.example.com.cer` + `.key`
- Certbot: replace `ssl_certificate` paths; optional auto-renew via `certbot renew --deploy-hook "systemctl reload nginx"`

Validation:

```bash
nginx -t && systemctl reload nginx
curl -I https://app.example.com/health
curl -I https://manager.example.com/health
```

## Environment files

- Remote VM: `.env.prod` or `.env` (or `/tmp/.env.prod` from CI)
- Full template: `deploy/env/.env.template`
- Minimal remote template: `deploy/env/.env.production.template` (shipped as `.env.template` in release bundle)

Compose project name: `lingqing` (one stack per VM).

## CI / automation

- Tests (every push/PR): `.github/workflows/ci.yml`
- Deploy automation: [byo-cicd.md](byo-cicd.md) and [`.github/workflows/deploy.example.yml`](../../.github/workflows/deploy.example.yml)
