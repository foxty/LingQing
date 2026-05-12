# Contributing

Thank you for your interest in LingQing.

## Before you start

1. Read [AGENTS.md](AGENTS.md) for architecture, layering, and coding conventions.
2. Read [docs/dev-guide.md](docs/dev-guide.md) for local setup.
3. Browse [docs/README.md](docs/README.md) for the full documentation index.

## Development workflow

```bash
uv sync --all-groups
cp deploy/env/.env.template .env.local
./deploy/scripts/local-stack.sh infra-up
npm run dev:ta
```

## Checks before opening a PR

```bash
npm run test:unit          # unit tests (same as pre-push)
npm run lint               # ruff + ESLint
npm run check-api-spec     # agent API contract
```

CI (`.github/workflows/ci.yml`) runs the full suite: backend pytest, frontend lint/build/test.

## Pull requests

- Keep changes focused; prefer small, reviewable PRs.
- Add or update tests when behavior changes.
- Use synthetic test data only — never production tenant or customer identifiers.
- Do not commit secrets (`.env.local`, API keys, credentials).

## Questions

Open a GitHub issue for bugs, feature requests, or design discussions.
