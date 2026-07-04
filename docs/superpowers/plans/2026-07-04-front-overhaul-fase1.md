# Front Overhaul — Fase 1 (frontend visual) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Modernizar la consola (menú con minigráficos, tabs-containers consistentes, filtro de fecha + recargar en Bandeja, afordancias explícitas) conservando la marca Acento, sin tocar backend.

**Architecture:** React + Vite + Tailwind (config existente en `frontend/tailwind.config.js`, componentes en `frontend/src/components/ui.jsx`). Se agrega un componente `Tabs` reutilizable y componentes de afordancia (`IconButton`, `Sparkline`), se refinan tokens de tema, y se aplican a las páginas Lenders, Clasificaciones, Bandeja y al Layout. Verificación por `npm run build` verde + preview.

**Tech Stack:** React 18, react-router-dom, TailwindCSS 3, Vite 5, lucide-react (iconos, a agregar).

## Global Constraints
- Marca: navy `#1C2445`, coral `#E2664B` — no romper la paleta.
- No tocar backend ni endpoints en esta fase.
- Fechas de correo se muestran con `lib/dates.js` (US Eastern) — ya existe.
- Cada task termina con `cd frontend && npm run build` en verde antes de commit.
- Reutilizar el patrón de tabs existente en `ReviewsPage.jsx` como referencia, pero extraerlo a componente compartido.

---

### Task 1: Dependencia de iconos + componente Tabs compartido

**Files:**
- Modify: `frontend/package.json` (agregar `lucide-react`)
- Create: `frontend/src/components/Tabs.jsx`
- Modify: `frontend/src/components/ui.jsx` (exportar `IconButton`)

**Interfaces:**
- Produces: `Tabs({ tabs, active, onChange })` donde `tabs = [{key, label, count?}]`; `IconButton({ icon: LucideIcon, label, onClick, tone? })`.

- [ ] **Step 1: Instalar lucide-react**

Run: `cd frontend && npm install lucide-react`
Expected: se agrega a dependencies, `npm install` sin error.

- [ ] **Step 2: Crear `Tabs.jsx`**

```jsx
// Tabs-container reutilizable. Segmented control con conteo opcional por tab.
export default function Tabs({ tabs, active, onChange }) {
  return (
    <div className="inline-flex items-center gap-1 p-1 rounded-lg bg-navy/[0.04] border border-line">
      {tabs.map((t) => {
        const on = t.key === active
        return (
          <button
            key={t.key}
            onClick={() => onChange(t.key)}
            className={`px-3.5 py-1.5 rounded-md text-sm font-medium transition-colors ${
              on ? 'bg-surface text-navy shadow-card' : 'text-muted hover:text-navy'
            }`}
          >
            {t.label}
            {typeof t.count === 'number' && (
              <span className={`ml-2 font-mono text-[11px] tnum ${on ? 'text-coral' : 'text-faint'}`}>
                {t.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 3: Agregar `IconButton` a `ui.jsx`**

```jsx
// Botón de acción con icono (afordancia explícita). icon = componente lucide.
export function IconButton({ icon: Icon, label, onClick, tone = 'ghost' }) {
  const cls = tone === 'coral' ? 'btn btn-coral' : tone === 'primary' ? 'btn btn-primary' : 'btn btn-ghost'
  return (
    <button className={cls} onClick={onClick} title={label} aria-label={label}>
      {Icon && <Icon size={15} strokeWidth={2} />}
      <span>{label}</span>
    </button>
  )
}
```

- [ ] **Step 4: Build verde**

Run: `cd frontend && npm run build`
Expected: `✓ built` sin errores de import.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/Tabs.jsx frontend/src/components/ui.jsx
git commit -m "feat(ui): componente Tabs compartido + IconButton + lucide-react"
```

---

### Task 2: Refinar tokens de tema (color/tipo modernos)

**Files:**
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: nuevas utilidades de superficie/hover y escala tipográfica; clase `.row-hover` para filas interactivas; variables ya usadas (`navy`, `coral`, etc.) intactas.

- [ ] **Step 1: Agregar tokens de superficie e interacción a tailwind.config.js**

En `theme.extend.colors` agregar (sin quitar los existentes):
```js
surfacealt: '#FAFBFC',
navysoft:  '#2A3565',
coralsoft: '#F4E3DE',
```
En `theme.extend.boxShadow` agregar:
```js
pop: '0 8px 24px rgba(20,26,52,0.12)',
focus: '0 0 0 3px rgba(226,102,75,0.30)',
```

- [ ] **Step 2: Agregar `.row-hover` y refinamientos en index.css (@layer components)**

```css
.row-hover { @apply transition-colors cursor-pointer; }
.row-hover:hover { background: rgba(28,36,69,0.03); }
.chip { @apply inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium; }
```

- [ ] **Step 3: Build verde**

Run: `cd frontend && npm run build`
Expected: `✓ built`.

- [ ] **Step 4: Commit**

```bash
git add frontend/tailwind.config.js frontend/src/index.css
git commit -m "feat(ui): tokens de superficie/interaccion y refinamiento tipografico"
```

---

### Task 3: Menú lateral con iconos + minigráfico de stats

**Files:**
- Modify: `frontend/src/components/Layout.jsx`
- Create: `frontend/src/components/Sparkline.jsx`

**Interfaces:**
- Consumes: `metaApi.stats()` (existente en `lib/api.js` — verificar; si no, usar `metaApi.health` + `statsApi`). `Tabs` no aplica aquí.
- Produces: nav sin códigos `00-06`, con icono lucide por item y un mini-stat en el item Panel.

- [ ] **Step 1: Crear `Sparkline.jsx`**

```jsx
// Mini-grafico SVG de barras a partir de un arreglo de numeros (0..max).
export default function Sparkline({ data = [], className = '' }) {
  const max = Math.max(1, ...data)
  return (
    <svg viewBox={`0 0 ${data.length * 4} 16`} className={className} preserveAspectRatio="none">
      {data.map((v, i) => (
        <rect key={i} x={i * 4} y={16 - (v / max) * 16} width="3" height={(v / max) * 16} rx="0.5" fill="currentColor" />
      ))}
    </svg>
  )
}
```

- [ ] **Step 2: Reemplazar `NAV` con iconos lucide (quitar `code`)**

En `Layout.jsx` importar iconos y redefinir NAV:
```jsx
import { LayoutDashboard, Inbox, Sparkles, Building2, Table2, FolderTree } from 'lucide-react'
const NAV = [
  { to: '/dashboard', label: 'Panel', Icon: LayoutDashboard },
  { to: '/inbox', label: 'Bandeja', Icon: Inbox },
  { to: '/classifications', label: 'Clasificaciones', Icon: Sparkles },
  { to: '/lenders', label: 'Lenders', Icon: Building2 },
  { to: '/waivers', label: 'Matriz waivers', Icon: Table2 },
  { to: '/sharepoint', label: 'SharePoint', Icon: FolderTree },
]
```
(NOTA: se quita '/reviews' del nav — la fusión con Bandeja es Fase 3; por ahora solo se oculta del menú pero la ruta sigue existiendo.)

- [ ] **Step 3: Renderizar icono en cada NavLink (reemplazar el `<span>` del code)**

Dentro del `.map`, cambiar el bloque del código mono por:
```jsx
<n.Icon size={17} strokeWidth={1.75} className="w-5 text-white/45 group-hover:text-coral shrink-0" />
```

- [ ] **Step 4: Build verde + preview**

Run: `cd frontend && npm run build`
Expected: `✓ built`. Preview: menú muestra iconos, sin códigos, sin item "Cola de revisión".

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Layout.jsx frontend/src/components/Sparkline.jsx
git commit -m "feat(nav): menu con iconos lucide + Sparkline (sin codigos, sin Cola de revision)"
```

---

### Task 4: Lenders con tabs-container (Aprobados · Por aprobar · Blacklist)

**Files:**
- Modify: `frontend/src/pages/LendersPage.jsx`

**Interfaces:**
- Consumes: `Tabs` (Task 1). `lendersApi.list()` con filtro de estado si existe; si no, filtrar en cliente por campo `status`/`approved`.

- [ ] **Step 1: Leer LendersPage y estado disponible**

Run: revisar `frontend/src/pages/LendersPage.jsx` y `lib/api.js` para saber qué campo distingue aprobado / pendiente / rechazado.
Expected: identificar campo (p.ej. `status` con `APPROVED|PENDING|REJECTED` o booleano). Blacklist = rechazados.

- [ ] **Step 2: Agregar estado de tab y filtrado**

```jsx
import Tabs from '../components/Tabs'
const TABS = [
  { key: 'APPROVED', label: 'Aprobados' },
  { key: 'PENDING', label: 'Por aprobar' },
  { key: 'REJECTED', label: 'Blacklist' },
]
// const [tab, setTab] = useState('PENDING')
// derivar counts y lista filtrada segun el campo real identificado en Step 1
```
Renderizar `<Tabs tabs={TABS.map(t => ({...t, count: counts[t.key]}))} active={tab} onChange={setTab} />` sobre la tabla; filtrar filas por `tab`.

- [ ] **Step 3: Build verde + preview**

Run: `cd frontend && npm run build`
Expected: `✓ built`. Preview: 3 tabs con conteos; cambiar de tab filtra.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/LendersPage.jsx
git commit -m "feat(lenders): tabs-container Aprobados/Por aprobar/Blacklist"
```

---

### Task 5: Clasificaciones con tabs-container (Aprobado · Corregido · Rechazado)

**Files:**
- Modify: `frontend/src/pages/ClassificationsPage.jsx`

**Interfaces:**
- Consumes: `Tabs`. `classificationsApi.list()`. Campo de estado: aprobado/corregido; "Rechazado" es estado nuevo (backend en Fase 2) → por ahora el tab existe y filtra por un campo `review_status` si está, o queda vacío con Empty.

- [ ] **Step 1: Leer ClassificationsPage y el campo de estado de revisión**

Run: revisar `ClassificationsPage.jsx` y la forma del item de `/classifications` (buscar `approved`, `corrected`, `review_status`).
Expected: identificar cómo se marca aprobado vs corregido.

- [ ] **Step 2: Agregar tabs y filtrado cliente**

```jsx
import Tabs from '../components/Tabs'
const TABS = [
  { key: 'APPROVED', label: 'Aprobado' },
  { key: 'CORRECTED', label: 'Corregido' },
  { key: 'REJECTED', label: 'Rechazado' },
]
```
Filtrar por el campo real; el tab REJECTED puede quedar con `<Empty>` hasta Fase 2. Mostrar counts.

- [ ] **Step 3: Reemplazar afordancia de clic-en-texto por IconButton (ojo)**

En la fila/acciones usar `IconButton` con icono `Eye` para abrir el drawer, en vez de asumir clic sobre el texto.
```jsx
import { Eye } from 'lucide-react'
// <IconButton icon={Eye} label="Ver" onClick={() => setSelected(id)} />
```

- [ ] **Step 4: Build verde + preview**

Run: `cd frontend && npm run build`
Expected: `✓ built`. Preview: 3 tabs; botón ojo abre el drawer.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ClassificationsPage.jsx
git commit -m "feat(clasificaciones): tabs Aprobado/Corregido/Rechazado + afordancia ojo"
```

---

### Task 6: Bandeja — filtro por fecha + botón Recargar (UI)

**Files:**
- Modify: `frontend/src/pages/EmailsPage.jsx`

**Interfaces:**
- Consumes: `emailsApi.list({ limit, offset, search })` (existente). Filtro de fecha: aplicar en cliente sobre `received_date` (rango desde/hasta) sobre la página actual; botón Recargar por ahora solo re-dispara `load` (el endpoint real de ingesta es Fase 2 — el botón queda cableado a `load` y se reconecta luego).

- [ ] **Step 1: Agregar inputs de rango de fecha y botón Recargar en el header**

```jsx
import { RefreshCw } from 'lucide-react'
// estados: const [from, setFrom] = useState(''); const [to, setTo] = useState('')
// inputs type="date" + IconButton icon={RefreshCw} label="Recargar" onClick={() => load(term, 0)}
```

- [ ] **Step 2: Filtrar items por rango de fecha (cliente)**

```jsx
const visible = data.items.filter((e) => {
  if (!e.received_date) return true
  const d = e.received_date.slice(0, 10) // YYYY-MM-DD del ISO
  if (from && d < from) return false
  if (to && d > to) return false
  return true
})
```
Renderizar `visible` en la tabla.

- [ ] **Step 3: Build verde + preview**

Run: `cd frontend && npm run build`
Expected: `✓ built`. Preview: inputs de fecha filtran; botón Recargar visible.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/EmailsPage.jsx
git commit -m "feat(bandeja): filtro por fecha (cliente) + boton Recargar (UI)"
```

---

## Self-Review
- **Cobertura spec Fase 1:** menú iconos+minigráfico (T3), color/tipo (T2), Lenders tabs (T4), Clasificaciones tabs + ojo (T5), filtro fecha + recargar (T6), Tabs/afordancias compartidas (T1). ✅
- **Diferido a Fase 2/3 (explícito):** endpoint real de Recargar, estado Rechazado persistido, fusión de Bandeja+Cola, composer Outlook, PDF proxy, feedback .md.
- **Placeholders:** los Steps "leer X" (T4/T5 Step 1) son inspección necesaria porque el campo de estado real debe confirmarse en código antes de filtrar; no son placeholders de implementación.
