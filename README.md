# OGM Lenders — Clasificador de Waivers (end-to-end)

Pipeline de clasificación de correos lender/waiver: **preflight (5 gates) → aprobación de lenders → clasificador híbrido (reglas + LLM Ollama opcional)**, con **API FastAPI** y **UI React**.

Este repo es el backend autoritativo (la "Mejora" que consume el cascarón `OGM_Lenders`). La integración API+UI vive aquí.

## Arquitectura

```
React (Vite :5173)  ──/api──►  FastAPI (api.py :8000)  ──►  pipeline
                                                             ├─ preflight.py     (5 gates → email_reviews)
                                                             ├─ lender_approval  (APROBADO/POR_APROBAR/NO_APROBADO)
                                                             └─ llm_classifier   (reglas + Ollama opcional)
                                                                    │
                                                             PostgreSQL (async / SQLAlchemy)
```

## Requisitos

- Python 3.12 + `venv` (deps en `requirements.txt`)
- PostgreSQL corriendo (`DATABASE_URL` en `.env`)
- Node 18+ (para el frontend)
- Ollama opcional (`USE_LLM_CLASSIFIER=true` para activar el LLM; default reglas-only)

## Arrancar

### 1. Backend API

```bash
./venv/Scripts/python.exe -m pip install -r requirements.txt
# migraciones in-place (no destructivas), si aplica:
./venv/Scripts/python.exe migrate_preflight.py
./venv/Scripts/python.exe migrate_classifier_features.py
# servidor:
./venv/Scripts/python.exe -m uvicorn api:app --reload --port 8000
```

Swagger: http://localhost:8000/docs

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173 (proxya `/api` → :8000)

## Endpoints (api.py, prefijo `/api/v1`)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` `/stats` | salud + métricas |
| GET | `/lenders` | dominios + estado |
| POST | `/lenders/{domain}/approve` `/reject` | aprobar (reprocesa correos) / rechazar |
| GET | `/emails` | production_emails |
| GET | `/reviews` | cola de revisión (descartes del preflight) |
| GET | `/classifications` | resultados (incluye category, escalate, secondary, adjuntos) |
| POST | `/classify/run` | clasificar pendientes (`limit`, `reclassify`) |

## Tests

```bash
./venv/Scripts/python.exe -m pytest tests/ -q
```
