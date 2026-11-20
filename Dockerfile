FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /bin/uv
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY rankflow ./rankflow
RUN uv sync --locked --no-dev --no-editable
CMD ["/app/.venv/bin/uvicorn", "rankflow.api:from_environment", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
