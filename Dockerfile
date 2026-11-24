# ClaimSense: one image with the React frontend and the FastAPI backend.
#   docker build -t claimsense .
#   docker compose -f docker-compose.full.yml up --build      (app + PostgreSQL)

# ---- Stage 1: build the React app (uses frontend/.env.production -> API under /api)
FROM node:20-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/app backend/app
COPY data/policy_wording data/policy_wording
COPY --from=frontend /src/dist frontend/dist
RUN useradd --create-home appuser && mkdir -p backend/logs && chown -R appuser /srv
USER appuser
WORKDIR /srv/backend
EXPOSE 8000
# No secrets in the image: all settings come from environment variables at run time.
CMD gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:${PORT} --timeout 120 app.serve:root
