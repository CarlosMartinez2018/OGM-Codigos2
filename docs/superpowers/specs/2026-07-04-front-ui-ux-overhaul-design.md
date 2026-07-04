# Front IU/UX Overhaul — Design Spec

Fecha: 2026-07-04
Rama: `feat/api-and-classifier-features`
Estado: aprobado por el usuario (diseño y fasado).

## Objetivo

Modernizar la consola Acento Waiver Control: navegación con minigráficos,
bandeja unificada estilo Outlook, tabs-containers consistentes, loop de
feedback correcciones→IA, PDF real inline, y mejor IU/UX/afordancias.
Conservar marca Acento (navy `#1C2445`, coral `#E2664B`).

## Decisiones fijadas

1. **Responder/borrador (punto 5):** SOLO diseño estilo Outlook. Sin conexión
   a Graph, sin envío. Muestra el borrador sugerido ya generado por el
   clasificador; el humano edita/adjunta/firma y **guarda localmente** (BD).
   Nunca se contesta al usuario final automáticamente — todo lo hace el humano.
2. **Fusión de navegación:** "Cola de revisión" se elimina del menú; la Bandeja
   se vuelve el hub con tabs-container.
3. **PDF (punto 7):** proxy/stream on-demand — el backend baja el archivo de
   SharePoint via Graph al vuelo y lo sirve; el front previsualiza inline.
4. **Feedback IA (punto 6):** resumen `.md` incremental de correcciones +
   rechazos (con comentario) que el clasificador lee como contexto.

## Secciones

### A. Shell visual + navegación (puntos 8, 9, 10)
- Menú sin códigos `00–06`. Cada item: icono + minigráfico en miniatura
  (sparkline/stat alimentado por `/api/v1/stats`).
- Paleta modernizada sobre navy+coral: superficies, bordes suaves, estados
  hover. Escala tipográfica nueva (sans moderna UI + IBM Plex Mono para datos).
  Micro-interacciones (taste-skill / frontend-design).
- Afordancias explícitas: icono 👁 "ver/abrir" en filas en vez de asumir clic
  sobre el texto. Botones con icono+label.

### B. Bandeja unificada estilo Outlook (puntos 2, 3, 4, 5 + filtro)
- Tabs-container: **General · Por revisar · Descartado · Contestado**.
- Filtro por fecha (rango) + botón "Recargar emails" (ingesta + clasificación).
- Vista tipo Outlook con hilos; **cada iteración muestra su fecha** (arregla la
  fecha faltante en hilos de revisión). Fechas en US Eastern (ya implementado).
- "Por revisar": correos marcados por la IA + el **porqué** de la revisión.
- "Contestado": respondidos + clasificaciones **aprobadas**.
- Composer de respuesta (modal estética Outlook): borrador sugerido editable +
  adjuntos + firma guardada → guarda en BD + marca CONTESTADO. Sin envío.

### C. Clasificaciones (puntos 6, 7)
- Tabs-container: **Aprobado · Corregido · Rechazado**.
- Rechazar → modal con comentario obligatorio → alimenta contexto IA.
- Corregir y rechazar → se resumen en `data/feedback_context.md` que el
  clasificador lee. Incremental, versionable, alimenta al LLM cuando se prenda.
- PDF real inline: endpoint proxy baja el archivo de SharePoint al vuelo →
  visor PDF embebido en la sección Documentos.

### D. Lenders (punto 1)
- Tabs-container: **Aprobados · Por aprobar · Blacklist** (Blacklist =
  dominios rechazados/bloqueados).

### E. Backend nuevo/cambios
- `POST /api/v1/emails/reload` — ingesta (read_emails --all-dates) + clasifica.
- `POST /api/v1/reviews/{id}/answer` (extender) — guardar respuesta compuesta
  (texto + adjuntos + firma) + marcar CONTESTADO. Sin Graph.
- `GET /api/v1/sharepoint/files/{id}/content` — proxy stream de bytes via Graph.
- `POST /api/v1/classifications/{id}/reject` — con comentario; anexa a feedback `.md`.
- Correcciones (endpoint existente) → también anexan a feedback `.md`.
- `GET/PUT /api/v1/settings/signature` — firma persistida (BD).
- Clasificador lee `feedback_context.md` al construir contexto.

## Fasado de implementación
1. **Frontend puro** (bajo riesgo): visual/menú/color/tipo + tabs-containers
   (Lenders, Clasificaciones) + filtro fecha UI + afordancias.
2. **Backend + wiring:** reload, PDF proxy, reject+feedback `.md`, correction feedback,
   signature settings.
3. **Bandeja unificada** + hilos Outlook + composer/borrador + firma + fusión nav.

## No-objetivos (YAGNI)
- Sin envío real de correos ni conexión de escritura a Graph para respuestas.
- Sin storage duplicado de PDFs (solo proxy on-demand).
- Sin autenticación multi-usuario / firma por-usuario (firma global por ahora).

## Riesgos
- Fusión de nav (fase 3) toca routing + 2 páginas; hacer al final.
- Proxy de PDF: archivos grandes → stream, no cargar en memoria completa.
- Reclasificación en "Recargar" puede tardar; feedback de progreso en UI.
