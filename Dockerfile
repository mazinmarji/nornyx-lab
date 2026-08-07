# syntax=docker/dockerfile:1.7

FROM node:22.18.0-alpine3.22 AS browser-build
WORKDIR /build/frontend
# The lockfile is committed, so the image build is reproducible: `npm ci`
# installs exactly the resolved tree and fails if it disagrees with package.json.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.9.3 AS uv-bin

FROM python:3.12.11-slim-bookworm AS academy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    CREWAI_DISABLE_TELEMETRY=true \
    CREWAI_TRACING_ENABLED=false \
    CREWAI_TESTING=true \
    OTEL_SDK_DISABLED=true \
    NORNYX_ACADEMY_DB=/app/.nornyx-lab/academy.db \
    NORNYX_ACADEMY_FRONTEND_DIST=/app/frontend/dist \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app

RUN groupadd --system academy \
    && useradd --system --gid academy --home-dir /app --shell /usr/sbin/nologin academy

COPY --from=uv-bin /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY labs/ ./labs/
COPY contracts/ ./contracts/
COPY scripts/ ./scripts/
COPY .github/ ./.github/

RUN uv sync --frozen --no-dev --extra crewai --extra langgraph --extra live --no-editable \
    && mkdir -p /app/.nornyx-lab \
    && chown -R academy:academy /app/.nornyx-lab

COPY --from=browser-build /build/frontend/dist/ ./frontend/dist/

USER academy
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"

CMD ["uvicorn", "nornyx_lab.academy.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
