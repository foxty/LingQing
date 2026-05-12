# Configuration Reference

Env vars, domain routing, and outer Nginx/TLS. For environment choice (E2E vs test vs prod) and deploy scripts, see [getting-started.md](getting-started.md). For step-by-step production deploy, see [quick-start.md](quick-start.md).

## Deployment axes

Two dimensions:

- **Tier:** `staging` or `production` (aliases: `test`, `prod`)
- **Stack:** `all`, `app`, `manager`

Recommended targets:

- Full production release: `all production`
- App-only production: `app production`
- Staging validation: `all staging`

## Service Names

- `tenant-app-service`: app backend (`APP_MODULE=tenant_app_service`)
- `tenant-manager-service`: manager backend (`APP_MODULE=tenant_manager_service`)
- `scheduler-service`: background scheduler
- `gateway-service`: shared frontend gateway (contains both app and manager portals)

## Domain Routing

Inner gateway config in `deploy/docker/nginx.conf`:

- `app.example.com` and `app-test.example.com`
  - static root: `/usr/share/nginx/html/app`
  - API proxy: `/api -> http://tenant-app-service:8000/`
- `manager.example.com` and `manager-test.example.com`
  - static root: `/usr/share/nginx/html/manager`
  - API proxy: `/api -> http://tenant-manager-service:8010/`

## Port Strategy

Internal container ports are fixed (app `8000`, manager `8010`, gateway `80`, sandbox `8090`, chroma `8000`, postgres `5432`). Env vars are **connection endpoints** for apps, not compose host bindings — except where noted.

| Tier | Host-published | Env vars (connection) |
| --- | --- | --- |
| **dev** (`infra.yml`) | Postgres `${TENANT_APP_DB_PORT}`, Chroma `8002`, Docling `${DOCLING_HOST_PORT}` | `.env.local`: `CHROMA_URL=http://localhost:8002`, `TENANT_APP_DB_PORT=5432` |
| **e2e** (`full-stack.yml`) | Postgres `5433`, Gateway `18080` (fixed in YAML) | `.env.e2e`: `CHROMA_URL=http://chroma:8000`, `TENANT_APP_DB_PORT=5432` |
| **remote prod** (`stack.yml`) | Gateway `${GATEWAY_SERVICE_PORT:-8080}` | `.env.prod`: docker service names |
| **remote staging** (+ override) | Gateway `18080` (override wins) | same as prod |

Removed from template (unused): `TENANT_APP_SERVICE_PORT`, `TENANT_MANAGER_SERVICE_PORT` — E2E no longer publishes app/manager to host; remote stack routes via gateway only.

Remote production default in `deploy/compose/remote/stack.yml`:

- `gateway-service` publishes `127.0.0.1:${GATEWAY_SERVICE_PORT:-8080}:80`

Staging override in `deploy/compose/remote/overrides/staging.yml`:

- `gateway-service` publishes `127.0.0.1:18080:80`

Notes:

- Bind to localhost for same-VM outer Nginx topology.
- Outer Nginx must preserve host header:
  - `proxy_set_header Host $host;`

## Outer Nginx Setup (Merged)

Use outer Nginx (host machine) as the public entrypoint, and forward requests to the inner gateway exposed by Docker Compose.

Routing target ports:

- Production tier: `127.0.0.1:8080` (or `127.0.0.1:${GATEWAY_SERVICE_PORT}`)
- Staging tier: `127.0.0.1:18080`

For internet-facing traffic, use one HTTPS-first config that includes HTTP-to-HTTPS redirect plus proxy rules for both prod/test domains.

Example merged config (`/etc/nginx/conf.d/lingqing-gateway.conf`):

```nginx
map $http_upgrade $connection_upgrade {
  default upgrade;
  ''      close;
}

# HTTP -> HTTPS redirect (and ACME challenge)
server {
  listen 80;
  server_name app.example.com manager.example.com app-test.example.com manager-test.example.com;

  location / {
    return 301 https://$host$request_uri;
  }
}

# --- Production HTTPS ---
server {
  listen 443 ssl http2;
  server_name app.example.com manager.example.com;

  # SSL Certificate (preconfigured wildcard or per-host)
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

# --- Test HTTPS ---
server {
  listen 443 ssl http2;
  server_name app-test.example.com manager-test.example.com;

  # SSL Certificate (preconfigured wildcard or per-host)
  ssl_certificate cert/_.example.com.cer;
  ssl_certificate_key cert/_.example.com.key;
  ssl_session_timeout 1d;
  ssl_session_cache shared:SSL:10m;
  ssl_session_tickets off;
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_prefer_server_ciphers off;

  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

  location / {
    proxy_pass http://127.0.0.1:18080;
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

Certificate management:

- This setup uses preconfigured wildcard certificates:
  - `cert/_.example.com.cer`
  - `cert/_.example.com.key`
- Ensure the certificate files are readable by the Nginx worker user.
- If you later switch to Certbot, replace the `ssl_certificate` and `ssl_certificate_key` paths accordingly.

Optional Certbot example (only if you switch away from preconfigured certs):

```bash
sudo mkdir -p /var/www/certbot
sudo certbot certonly --webroot -w /var/www/certbot \
  -d app.example.com -d manager.example.com \
  -d app-test.example.com -d manager-test.example.com
```

Optional auto-renew hook:

```bash
sudo crontab -e
# renew twice daily and reload nginx when cert changes
0 3,15 * * * certbot renew --quiet --deploy-hook "systemctl reload nginx"
```

Validation:

- `nginx -t`
- `systemctl reload nginx`
- `curl -H 'Host: app.example.com' http://127.0.0.1/health`
- `curl -H 'Host: manager.example.com' http://127.0.0.1/health`
- `curl -I https://app.example.com/health`
- `curl -I https://manager.example.com/health`

Notes:

- Keep `Host` header unchanged so the inner gateway can route by domain.
- If you deploy only one stack, keep only the corresponding server block.
- TLS should terminate at outer Nginx; keep proxy target as `http://127.0.0.1:<port>`.

## Environment Files

- Production: `.env.prod` (or `/tmp/.env.prod` from CI)
- Staging: `.env.staging`

Compose project names:

- `lingqing-production`
- `lingqing-staging`

## CI / automation

- Tests (every push/PR in this repo): `.github/workflows/ci.yml`
- Deploy automation: see [byo-cicd.md](byo-cicd.md) and [`.github/workflows/deploy.example.yml`](../../.github/workflows/deploy.example.yml)
