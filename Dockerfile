# Multi-stage: build frontend, then serve API + UI single-origin.
# Runs as non-root (UID 1001) for Cloud Run / K8s compatibility.

# ── Stage 1: build frontend ─────────────────────────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
RUN groupadd -g 1001 appgroup && useradd -u 1001 -g appgroup -m appuser
WORKDIR /app

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/ backend/
# Editable install keeps the 'app' package rooted at /app/backend/app so the
# frontend static mount (which resolves dist relative to app/core/static.py)
# points at /app/frontend/dist. Skip the optional [agent] extra (google-adk is
# slow/flaky and unused in mock mode). Run uvicorn via `python -m` at runtime
# so it doesn't depend on console-script PATH.
RUN pip install --no-cache-dir -e backend/ && \
    pip install --no-cache-dir alembic "redis>=5"
COPY --from=frontend /app/frontend/dist frontend/dist

# Writable data dir for SQLite.
RUN mkdir -p /data && chown appuser:appgroup /data
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    USE_MOCKS=true \
    DATABASE_URL=sqlite+aiosqlite:////data/spm.db
WORKDIR /app/backend
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:%s/api/v1/health'%os.environ.get('PORT','8080'))" || exit 1

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
