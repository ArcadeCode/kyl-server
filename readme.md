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

## Run

First you need to create a `.env` file with this variables :
- POSTGRES_HOST
- POSTGRES_PORT
- POSTGRES_DATABASE
- POSTGRES_USERNAME
- POSTGRES_PASSWORD
- SMTP_HOST
- SMTP_PORT
- SMTP_USERNAME
- SMTP_PASSWORD
- SMTP_USE_TLS
- SMTP_FROM_ADDRESS
- RESET_PASSWORD_BASE_URL

After that run :
```bash
uv sync
docker compose up
```