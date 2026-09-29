# Custom CI/CD (Path B)

Use build and deploy scripts from your pipeline. Template: [`.github/workflows/deploy.example.yml`](../../.github/workflows/deploy.example.yml).

## Flow

```text
Tag or main commit
  → build-backend.sh / build-frontend.sh
  → generate-env.sh
  → remote/deploy.sh
  → smoke checks
```

## Scripts

| Script | Purpose |
| --- | --- |
| `deploy/scripts/build-backend.sh` | Build/push backend + sandbox images |
| `deploy/scripts/build-frontend.sh` | Build/push frontend gateway |
| `deploy/scripts/generate-env.sh` | Expand `deploy/env/.env.template` from secrets |
| `deploy/scripts/remote/deploy.sh` | SSH deploy to target VM |

Example:

```bash
./deploy/scripts/build-backend.sh registry.example.com/lingqing v2.0.0 --ci
./deploy/scripts/build-frontend.sh registry.example.com/lingqing v2.0.0 --ci

export SECRET_KEY=... TENANT_APP_DB_PASSWORD=... TENANT_MANAGER_DB_PASSWORD=...
./deploy/scripts/generate-env.sh deploy/env/.env.template /tmp/.env.prod

./deploy/scripts/remote/deploy.sh v2.0.0 registry.example.com/lingqing prod.example.com deploy /tmp/.env.prod all
```

`deploy.sh` arguments: `VERSION REGISTRY_URL DEPLOY_HOST DEPLOY_USER ENV_FILE [STACK] [SSH_KEY]`

- `STACK`: `all` | `app` | `manager`

Use separate VMs (or separate CI workflows with different secrets/vars) for staging vs production.

## Secrets

Never commit `.env.prod`. Inject secrets in CI for `generate-env.sh`.

## Related

- [guide.md](guide.md) — manual first deploy
- [reference.md](reference.md) — env and PostgreSQL reference
