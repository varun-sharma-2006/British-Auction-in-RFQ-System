# Single-container build: React app compiled and served by the FastAPI process (one URL, no CORS).
# Used by render.yaml. For the full Postgres + Redis + Celery topology use docker-compose.yml.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FRONTEND_DIST=/app/frontend_dist
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist ./frontend_dist

EXPOSE 8000
# Migrate, load demo data on a fresh database (SEED_DEMO=true), then serve on $PORT (set by Render) or 8000.
CMD ["sh", "-c", "alembic upgrade head && if [ \"$SEED_DEMO\" = \"true\" ]; then python -m scripts.seed --if-empty; fi && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
