# Multi-stage build: build the frontend, then serve API + UI single-origin.
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app
# Backend deps
COPY backend/pyproject.toml backend/pyproject.toml
RUN pip install --no-cache-dir -e backend/[agent] || pip install --no-cache-dir -e backend/
COPY backend/ backend/
# Built frontend (served by app.core.static at /)
COPY --from=frontend /app/frontend/dist frontend/dist

ENV PYTHONUNBUFFERED=1 PORT=8080 USE_MOCKS=true
WORKDIR /app/backend
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
