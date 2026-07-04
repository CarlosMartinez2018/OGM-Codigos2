# OGM Lenders — Clasificador de Waivers (end-to-end)

Pipeline de clasificación de correos lender/waiver: **preflight (5 gates) → aprobación de lenders → clasificador híbrido (reglas + LLM Ollama opcional)**, con **API FastAPI** y **UI React**.

Este repo es el backend autoritativo (la "Mejora" que consume el cascarón `OGM_Lenders`). La integración API+UI vive aquí.

## Arquitectura

```
React (Vite :5173)  ──/api──►  FastAPI (app.main :8000)  ──►  pipeline
                                                              ├─ services/preflight        (5 gates → email_reviews)
                                                              ├─ services/lender_approval  (APROBADO/POR_APROBAR/NO_APROBADO)
                                                              └─ services/llm_classifier   (reglas + Ollama opcional)
                                                                     │
                                                              PostgreSQL (async / SQLAlchemy)
```

## Estructura

```
app/                    # backend (paquete Python)
  main.py               #   FastAPI (uvicorn app.main:app)
  schemas.py            #   dataclasses (EmailData, ClassificationResult)
  core/config.py        #   Settings (pydantic)
  db/                   #   database.py (engine/Base/session) + models.py (ORM)
  services/             #   preflight, llm_classifier, lender_approval,
                        #   lender_utils, connector, read_emails, read_emls
scripts/                # seed_db.py (siembra prod limpia; correr con python -m scripts.seed_db)
data/                   # domain_lender_map.json, lender_waiver_matrix.json (semilla)
frontend/               # UI React (Vite + Tailwind)
sample_emails/          # .eml de ejemplo
tests/                  # pytest
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
# sembrar BD limpia desde data/*.json (crea el esquema desde models.py + carga datos):
./venv/Scripts/python.exe -m scripts.seed_db
# servidor:
./venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

> El esquema vive en `app/db/models.py` (única fuente). `seed_db` hace `drop + create_all + carga JSON`. `data/*.json` son fuente primaria (status de dominios y documentos ya normalizados).

Swagger: http://localhost:8000/docs

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173 (proxya `/api` → :8000)

## Endpoints (app/main.py, prefijo `/api/v1`)

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
