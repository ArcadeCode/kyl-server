FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

# Our modules (app, database, models, routes...) live in src/ and import each other by top-level name.
ENV PYTHONPATH=/app/src

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-cache

COPY . .

EXPOSE 5000

CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:create_app()"]
