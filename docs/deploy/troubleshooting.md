# Troubleshooting

## Manager Domain Opens App Portal

Check outer Nginx preserves host header:

```nginx
proxy_set_header Host $host;
```

Verify inner gateway `server_name` includes manager domains (`deploy/docker/nginx.conf`).

## Direct Access to 127.0.0.1:8080 Shows Default Site

Expected for default vhost. Verify with explicit host header:

```bash
curl -H 'Host: app.example.com' http://127.0.0.1:8080/health
curl -H 'Host: manager.example.com' http://127.0.0.1:8080/health
```

## Staging/Production Collisions on One VM

Common causes:

- Same published port for both tiers
- Same compose project name

Expected isolation:

- Production: `lingqing-production`, port `8080`
- Staging: `lingqing-staging`, port `18080`

## Manager Portal Works But Manager API Fails

1. `tenant-manager-service` is healthy
2. Inner gateway maps manager host `/api` → `tenant-manager-service:8010`
3. Frontend uses relative API base `/api`

## CI Did Not Deploy Manager Changes

Run workflow manually with `deploy_stack=manager` and desired tier.

## Quick Post-Deploy Checks

```bash
# production
curl -fsS -H 'Host: app.example.com' http://127.0.0.1:8080/health
curl -fsS -H 'Host: manager.example.com' http://127.0.0.1:8080/health

# staging
curl -fsS -H 'Host: app-test.example.com' http://127.0.0.1:18080/health
curl -fsS -H 'Host: manager-test.example.com' http://127.0.0.1:18080/health
```
