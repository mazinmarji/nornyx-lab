# syntax=docker/dockerfile:1.7
#
# The feedback intake, built as its own image.
#
# This is deliberately not part of the learner image. The learner image must
# contain no GitHub write authority at all, and the cleanest way to guarantee
# that is for the component that holds the credential to be a different
# artifact built from a different context.
#
# No secret is baked in. `NORNYX_FEEDBACK_GITHUB_TOKEN` is injected at runtime
# by the deployment, never through a build argument — a build arg would be
# recorded in the image history and readable by anyone who pulls the image.

FROM ghcr.io/astral-sh/uv:0.9.3 AS uv-bin

FROM python:3.12.11-slim-bookworm AS gateway

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    NORNYX_FEEDBACK_DB=/var/lib/nornyx-feedback/gateway.db \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app

RUN groupadd --system gateway \
    && useradd --system --gid gateway --home-dir /app --shell /usr/sbin/nologin gateway

COPY --from=uv-bin /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

RUN uv sync --frozen --no-dev --no-editable \
    && mkdir -p /var/lib/nornyx-feedback \
    && chown -R gateway:gateway /var/lib/nornyx-feedback

USER gateway
EXPOSE 8080

# Answers "is the process serving?" and nothing else. The health endpoint
# reports whether a destination is configured; it never reports the credential.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"

# `--factory` rather than a module-level `app`: importing this package must not
# open a database or read configuration as a side effect, so tests can import it
# freely.
#
# `--no-access-log` keeps client addresses out of the log stream. The gateway
# holds addresses transiently for rate limiting and never persists or logs them.
CMD ["uvicorn", "nornyx_feedback_gateway.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--proxy-headers"]
