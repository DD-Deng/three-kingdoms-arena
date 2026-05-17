# ── Stage 1: build frontend-v2 ──────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /src
COPY frontend-v2/package.json frontend-v2/package-lock.json ./
RUN npm ci
COPY frontend-v2/ ./
RUN npm run build

# ── Stage 2: Python app ─────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps for git-based pip installs
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/
COPY templates/ ./templates/
COPY personas/ ./personas/
COPY pyproject.toml ./

# Copy built frontend-v2
COPY --from=frontend-build /src/dist/ ./frontend-v2/dist/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
