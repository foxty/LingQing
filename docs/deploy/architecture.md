# Deployment Architecture

Describes the supported production topology (Docker Compose on a single VM or equivalent host).

## Single VM topology

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

## Design decisions

1. **Host-based routing** — avoids SPA base-path complexity; each portal has its own domain.
2. **One frontend gateway image** — contains both portal builds (`/app` and `/manager`).
3. **Independent stacks** — deploy `app`, `manager`, or `all` (see [configuration.md](configuration.md)).
4. **Staging + production on one VM** — different Compose project names and ports (`8080` vs `18080`).

## Stack definitions

| Stack | Services |
| --- | --- |
| `app` | `tenant-app-service`, `scheduler-service`, `gateway-service`, infra (chroma, sandbox, …) |
| `manager` | `tenant-manager-service`, `gateway-service` |
| `all` | Full production stack |

## Images

Built by `deploy/scripts/build-backend.sh` and `deploy/scripts/build-frontend.sh`:

| Image | Contents |
| --- | --- |
| `backend-app` | Python backend; module selected via `APP_MODULE` |
| `frontend` | Both portals + inner Nginx (`deploy/docker/nginx.conf`) |
| `sandbox-controller`, `sandbox-runner` | Agent code execution |

## Kubernetes note

Kubernetes/Helm manifests are not included in this repository. A future K8s deployment should preserve the same **host-based routing contract** (two Ingress host rules → gateway → backend services).
