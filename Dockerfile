# Production image: the API and the built frontend in one container (Cloud Run).
# Local development uses backend/Dockerfile and the Vite dev server instead.

FROM node:22-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production \
    LOG_FORMAT=json \
    STATIC_DIR=/app/static \
    DOCUMENTS_DIR=/app/datasets/documents \
    PORT=8080

WORKDIR /app
COPY backend/pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install ".[gcp]" && rm -rf app

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini backend/docker-entrypoint.sh ./
COPY datasets/documents ./datasets/documents
COPY --from=frontend /web/dist ./static
RUN pip install --no-deps . \
    && chmod +x docker-entrypoint.sh \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data && chown appuser /app/data
USER appuser

EXPOSE 8080
ENTRYPOINT ["./docker-entrypoint.sh"]
# Cloud Run sets PORT. uvicorn's access log is replaced by the app's structured one, and
# client addresses come from X-Forwarded-For per FORWARDED_HOPS (app.core.protection).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
