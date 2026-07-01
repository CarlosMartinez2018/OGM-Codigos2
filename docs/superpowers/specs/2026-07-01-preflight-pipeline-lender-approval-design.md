# Diseño: Pipeline de pre-filtrado + Workflow de aprobación de lenders

Fecha: 2026-07-01
Estado: Aprobado (diseño) — pendiente plan de implementación

## Contexto

El clasificador (`llm_classifier.py`) hoy toma todos los `production_emails` y los
clasifica con reglas + LLM. El cliente definió (BPMN `diagram.bpmn`) un flujo de
pre-filtrado que debe correr **antes** del análisis LLM: descarta o pone en
revisión manual los correos que no cumplen condiciones, y solo deja pasar los
válidos. Además, los dominios/lenders desconocidos deben entrar a un flujo de
aprobación (POR APROBAR → APROBADO / NO APROBADO).

Objetivo: solo correos que sobreviven el pipeline y cuyo lender está `APROBADO`
llegan al LLM.

### Mapeo BPMN → gates

| BPMN | Gate |
|---|---|
| Validación black list → "En lista" = FIN | Gate 1 blacklist |
| Dominio conocido / no conocido | Gate 2 dominio + auto-alta POR_APROBAR |
| Se adiciona a black list = FIN | reject → NO_APROBADO |
| Validación de Hilos → "Hilo incompleto o reenvíos" = FIN | Gate 3 hilos |
| Validación bloqueos de seguridad → "Mensaje incompleto" = FIN | Gate 4 seguridad |
| Análisis de requerimiento (verde) | LLM (solo sobrevivientes) |

Todo evento **FIN** = correo descartado del flujo automático y guardado en la cola
de revisión manual (`email_reviews`), nunca pasa al LLM.

## Decisiones tomadas

1. **Regla de seguridad:** un correo se descarta por seguridad cuando su
   **contenido está bloqueado/incompleto** (cifrado, truncado o con placeholder
   de "contenido protegido/bloqueado"). Detección por patrones configurables.
   El tag `[EXTERNAL]` NO cuenta (es banner normal de correos de lenders).
2. **Almacenamiento de descartados:** tabla separada `email_reviews`.
3. **Estado del lender:** columna `status` en `domain_lender_map`.
4. **Alcance:** backend completo (pipeline + tablas + gate de aprobación + re-run
   al aprobar). Sin UI ni CLI en esta iteración; funciones de aprobación
   invocables programáticamente (la UI las llamará después).

## A. Modelo de datos

### `domain_lender_map` (+2 columnas)

- `status`: `VARCHAR` — `APROBADO` | `POR_APROBAR` | `NO_APROBADO`. Default `POR_APROBAR`.
- `created_at`: `timestamptz` default now.

Migración de datos:
- Los 14 dominios existentes → `APROBADO`.
- Dominios ruido sembrados como `NO_APROBADO` (blacklist inicial):
  `teams.mail.microsoft`, `proofpointessentials.com`, `microsoft.com`.

Semántica: `NO_APROBADO` unifica "blacklist" (ruido/bots) y "lender rechazado por
el usuario (✖️)". Ambos se descartan en Gate 1.

### Nueva tabla `email_reviews`

Cola de revisión manual. Un correo puede tener a lo sumo una review PENDIENTE.

| Columna | Tipo | Nota |
|---|---|---|
| `id` | PK | |
| `production_email_id` | FK → production_emails.id (CASCADE) | |
| `message_id` | varchar | unique junto a stage para idempotencia |
| `conversation_id` | varchar | |
| `case_id` | varchar | = conversation_id |
| `stage` | varchar | `blacklist`\|`lender_nuevo`\|`lender_por_aprobar`\|`hilo_incompleto`\|`reenvio`\|`seguridad_bloqueo`\|`duplicado` |
| `reason` | text | detalle legible |
| `detected_original_sender` | text null | remitente original extraído en reenvíos |
| `status` | varchar | `PENDIENTE` \| `GESTIONADO`. Default `PENDIENTE` |
| `created_at` | timestamptz | |
| `resolved_at` | timestamptz null | |

Idempotencia: `UNIQUE(message_id, stage)` + upsert. Re-correr el pipeline no
duplica reviews.

### `production_emails` (+1 columna)

- `case_id`: `varchar` — agrupa hilos (= `conversation_id`). Escenario 5.

## B. Pipeline de pre-filtrado (`preflight.py`)

Módulo con una función pura por gate y un orquestador. Interfaz:

```
@dataclass
class PreflightResult:
    passed: bool                 # True => sigue al LLM
    stage: str | None            # gate que lo detuvo (si passed=False)
    reason: str
    detected_original_sender: str | None = None

def evaluate(email: EmailData, kb: dict, conversation_group: list[EmailData]) -> PreflightResult
```

Orden (corta en el primer gate que falla):

1. **Gate blacklist** — `sender_domain` con `status=NO_APROBADO` →
   `PreflightResult(False, 'blacklist', ...)`.
2. **Gate dominio**:
   - `APROBADO` → sigue.
   - `POR_APROBAR` → `(False, 'lender_por_aprobar')`.
   - no está en `domain_lender_map` → **auto-alta**
     `domain_lender_map(domain, lender_name=inferido, status=POR_APROBAR,
     created_at=now)` y `(False, 'lender_nuevo')`.
     - `lender_name` inferido = parte principal del dominio capitalizada
       (ej. `berkleyenvironmental.com` → "Berkleyenvironmental"); el usuario lo
       corrige al aprobar.
3. **Gate hilos**:
   - Reenvío: asunto matchea `^(FW|FWD|RV|ENC|RE?V)\s*:` **o** remitente interno
     (`acentopartners.com`/`captiveadvisorypartners.com`) **o** el body contiene un
     bloque citado de reenvío (`De:`/`From:` con dirección) →
     `(False, 'reenvio', detected_original_sender=<extraído>)`.
   - Hilo sin origen: en `conversation_group` no existe un correo cuyo remitente
     sea de un dominio `APROBADO` (no hay solicitud original de lender en el buzón)
     → `(False, 'hilo_incompleto')`.
4. **Gate seguridad** — body bloqueado/incompleto: tras `clean_email_body`, el body
   queda vacío/muy corto (< N chars) **o** contiene marcadores configurables
   (`encrypted message`, `rights-protected`, `message is protected`, `enable
   content`, `contenido bloqueado`, `no se puede mostrar`, etc.) →
   `(False, 'seguridad_bloqueo')`.
5. **Gate dedup** — por `case_id`: solo el correo **primario** del caso (el de
   **menor `received_date`**, el primero del `conversation_id` por fecha) continúa
   al LLM. Todo correo que **no** sea el primero por fecha → `(False, 'duplicado')`
   y va a la **cola de revisión manual** (`email_reviews`, stage `duplicado`),
   igual que cualquier otro FIN — no se descarta en silencio. Empates o
   `received_date` nulo: primario = menor `id` (orden de ingreso).
6. Si pasa todos → `(True)` y va al LLM.

Los patrones de seguridad y umbral `N` viven en `config.py`
(`security_block_markers`, `security_min_body_len`) para ajuste sin tocar código.

## C. Aprobación de lenders (`lender_approval.py`)

```
async def approve_domain(session, domain: str) -> ReprocessSummary
async def reject_domain(session, domain: str) -> None
```

- `approve_domain`: `status → APROBADO`. Luego **re-procesa** los correos de ese
  dominio con `received_date` en `[created_at - 1 día, ahora]`:
  marca sus `email_reviews` de stage `lender_*` como `GESTIONADO`, y corre
  pipeline + LLM sobre ellos. Devuelve resumen (reprocesados, clasificados).
- `reject_domain`: `status → NO_APROBADO`. Futuros correos caen en Gate 1.

Sin UI/CLI ahora: se llaman desde código/tests. La UI (futura) las expone con
✅/✖️.

## D. Integración en el clasificador

- `_load_business_data`: `domain_map` se construye **solo** con filas
  `status='APROBADO'`. `authorized_lenders` idem. (POR_APROBAR/NO_APROBADO no
  identifican lender.)
- `classify_pending_production_emails`:
  1. Carga KB (una vez) + agrupa correos por `case_id`.
  2. Por correo: `preflight.evaluate(...)`.
     - `passed=False` → upsert `email_reviews`, no clasifica.
     - `passed=True` → clasifica (reglas + LLM) y guarda como hoy.
  3. Commit.
- La clasificación existente (`_enforce_validation`, modo lean LLM) no cambia.

## E. Migración y semilla

- `migrate_preflight.py` (in-place, preserva correos): agrega columnas a
  `domain_lender_map` y `production_emails`, crea `email_reviews`, setea status
  de los 14 existentes a `APROBADO`, inserta dominios ruido `NO_APROBADO`,
  rellena `case_id = conversation_id`.
- `seed_db.py` / `export_seed.py`: incluir `status`/`created_at` de dominios para
  reseed en producción.

## Componentes (aislados, testeables)

| Unidad | Responsabilidad | Depende de |
|---|---|---|
| `preflight.py` | 5 gates puros + orquestador `evaluate` | EmailData, kb, config |
| `lender_approval.py` | approve/reject + re-run por ventana | session, preflight, classifier |
| `models.py` | +status/created_at, +EmailReview, +case_id | — |
| `llm_classifier.py` | integra preflight; filtra APROBADO | preflight |
| `migrate_preflight.py` | migración in-place dev | models |

Cada gate es una función `def gate_x(email, kb, group) -> PreflightResult|None`
testeable con un `EmailData` sintético, sin BD.

## Testing

- Unit por gate: correo interno → `reenvio`; dominio NO_APROBADO → `blacklist`;
  body con marcador → `seguridad_bloqueo`; segundo correo de un case → `duplicado`;
  dominio nuevo → auto-alta POR_APROBAR + `lender_nuevo`.
- Integración: sobre los 137 reales, verificar conteos por stage y que solo
  sobrevivientes con lender APROBADO llegan al LLM.
- Aprobación: aprobar un dominio POR_APROBAR → sus correos en ventana se
  reprocesan y salen de la cola.

## Límites conocidos

- Detección de hilo/reenvío y origen del lender es **heurística** (asunto,
  remitente interno, bloque citado). Con `production_emails` plano no siempre hay
  certeza del origen; por eso el resultado es "revisión manual", no descarte
  silencioso.
- Marcadores de "contenido bloqueado" se afinan con casos reales; arrancan como
  lista configurable.

## No incluido (futuro)

- Interfaz de usuario (aprobar/rechazar, gestionar cola de revisión).
- CLI de aprobación.
- Reglas de seguridad adicionales que el cliente pueda definir después.
