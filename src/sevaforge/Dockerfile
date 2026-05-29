# ── SevaForge Enterprise AI Platform ────────────────────────────────────────────
# Multi-stage build: slim Python 3.11 image

FROM python:3.11-slim AS base

# Metadata
LABEL maintainer="mandeepsingh@deltek.com"
LABEL description="SevaForge Enterprise AI Platform — API & AI Gateway"
LABEL version="1.0.0"

# Security: non-root user
RUN groupadd -r sevaforge && useradd -r -g sevaforge -d /app -s /sbin/nologin sevaforge

WORKDIR /app

# ── Dependencies ────────────────────────────────────────────────────────
FROM base AS deps

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[all]"

# ── Application ─────────────────────────────────────────────────────────
FROM deps AS app

COPY src/ src/
COPY templates/ templates/

# Own everything by sevaforge user
RUN chown -R sevaforge:sevaforge /app

USER sevaforge

# ── Runtime ───────────────────────────────────────────────────────────
ENV SEVAFORGE_ENVIRONMENT=production
ENV SEVAFORGE_DEBUG=false
ENV SEVAFORGE_HOST=0.0.0.0
ENV SEVAFORGE_PORT=8000
ENV SEVAFORGE_LOG_LEVEL=INFO

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/api/v1/health'); r.raise_for_status()"

CMD ["python", "-m", "sevaforge"]
