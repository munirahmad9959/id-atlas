# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first, so code changes do not invalidate this layer. README.md, LICENSE and NOTICE are
# listed in pyproject.toml, so the build needs them.
COPY pyproject.toml uv.lock .python-version README.md LICENSE NOTICE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim-bookworm AS production

LABEL org.opencontainers.image.title="id-atlas" \
      org.opencontainers.image.description="Lightweight, self-hosted OCR for identity documents" \
      org.opencontainers.image.licenses="Apache-2.0"

RUN useradd --system --uid 10001 --create-home atlas
WORKDIR /app
COPY --from=build --chown=atlas:atlas /app/.venv /app/.venv

# The service listens on loopback by default; inside a container it has to listen on every interface.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ID_ATLAS_HOST=0.0.0.0 \
    ID_ATLAS_PORT=8000

USER atlas
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

# One process on purpose: inference is serialized by a lock, so extra workers only add memory.
# Scale by running more containers.
CMD ["id-atlas"]
