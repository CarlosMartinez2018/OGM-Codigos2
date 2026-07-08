# =============================================================
# AcentoPartners Email Classifier — imagen de produccion
# Etapa 1: build del frontend (Vite) · Etapa 2: FastAPI + estaticos
# =============================================================

FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /srv

# Dependencias primero (cache de capas)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend + activos de negocio + scripts (seed/migraciones)
COPY app/ app/
COPY data/ data/
COPY scripts/ scripts/

# Frontend compilado (FastAPI lo sirve con fallback SPA)
COPY --from=frontend /build/dist frontend/dist

# Usuario sin privilegios
RUN useradd --create-home appuser && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000
# App Service inyecta PORT/WEBSITES_PORT; default 8000
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
