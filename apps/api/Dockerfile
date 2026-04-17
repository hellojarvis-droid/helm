FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy lockfile + project metadata first so dependency install caches between builds.
COPY apps/api/pyproject.toml apps/api/uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev || uv sync --no-install-project --no-dev

# Now copy source.
COPY apps/api/ .

# Install project itself (editable so restart-on-change works in dev; prod still fast).
RUN uv sync --no-dev

ENV PORT=8000
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "helm.main:app", "--host", "0.0.0.0", "--port", "8000"]
