FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-cache

COPY . .

EXPOSE 5000

CMD ["uv", "run", "--env-file", ".env", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "src.app:app"]