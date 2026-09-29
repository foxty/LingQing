# Deployment

LingQing is **self-hosted** — you provide PostgreSQL, a VM, container registry, domains, and TLS.

Repo layout cheat sheet: [deploy/README.md](../../deploy/README.md).

## Documents

| Document | When to read |
| --- | --- |
| **[guide.md](guide.md)** | Deploy to production or staging — steps, scripts, troubleshooting |
| **[reference.md](reference.md)** | Look up PostgreSQL, env vars, Nginx/TLS, topology |
| **[byo-cicd.md](byo-cicd.md)** | Automate build and deploy from CI |

## Choose a path

| Goal | Start here |
| --- | --- |
| First production deploy | [guide.md → Production deploy](guide.md#production-deploy) |
| Try locally / E2E | [guide.md → Local](guide.md#local-development) · [dev-guide.md](../dev-guide.md) |
| Release bundle (no repo clone) | [guide.md → Option A](guide.md#option-a--release-bundle-on-vm) |
| Custom CI/CD | [byo-cicd.md](byo-cicd.md) |
