# KYL server
KYL server store the active backend of Know-your-lessons project.

## Tests

```bash
uv sync                                      # installs the dev group (pytest, pytest-cov)

uv run pytest -m "not integration"           # unit tests only: no database needed

docker compose -f compose.test.yml up -d     # throw-away PostgreSQL on localhost:5433
uv run pytest                                # everything
uv run pytest --cov=src --cov-report=term-missing
docker compose -f compose.test.yml down
```

Integration tests wipe their tables: `TEST_DATABASE_URL` must point to a database whose
name ends with `_test` (the default does), otherwise the run is refused.