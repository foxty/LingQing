# Tests

```bash
npm run test:unit                              # unit (pre-push)
uv run pytest tests/integration/ -v            # integration (Docker)
uv run pytest tests/ -v                        # full suite (CI)
```

Full guide: [docs/testing-guide.md](../docs/testing-guide.md)
