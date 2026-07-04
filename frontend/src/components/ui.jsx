// Componentes UI — lenguaje "consola de cumplimiento" AcentoPartners.
// Marca navy #1C2445 + acento coral #E2664B. Tokens de máquina en mono.

export function Spinner({ className = '' }) {
  return (
    <span
      className={`inline-block w-4 h-4 border-2 border-line border-t-coral rounded-full animate-spin ${className}`}
      role="status"
      aria-label="Cargando"
    />
  )
}

// Monograma AP en anillo — lacre de la marca.
export function Seal({ size = 34 }) {
  return (
    <div
      className="grid place-items-center rounded-full bg-navy text-coral font-semibold ring-1 ring-coral/40 shrink-0"
      style={{ width: size, height: size, fontSize: size * 0.4 }}
      aria-hidden="true"
    >
      AP
    </div>
  )
}

// Mapea un valor de dominio a un tono de sello.
export function stampTone(value) {
  switch (value) {
    case 'APROBADO':
    case 'high':
    case 'GESTIONADO':
      return value === 'GESTIONADO' ? 'neutral' : 'ok'
    case 'POR_APROBAR':
    case 'medium':
    case 'PENDIENTE':
      return 'warn'
    case 'NO_APROBADO':
    case 'low':
      return 'stop'
    default:
      return 'neutral'
  }
}

export function Stamp({ tone = 'neutral', children }) {
  return <span className={`stamp stamp-${tone}`}>{children}</span>
}

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

// KPI tipo readout de terminal: número mono grande, etiqueta en versalitas, lomo latón.
export function Kpi({ label, value, sub, tone = 'coral' }) {
  const tick = tone === 'coral' ? 'border-coral' : tone === 'stop' ? 'border-stop' : 'border-navy'
  return (
    <div className={`card px-5 py-4 border-l-2 ${tick}`}>
      <p className="eyebrow">{label}</p>
      <p className="text-[2rem] leading-none font-mono font-medium text-navy mt-2 tnum">
        {value ?? '—'}
      </p>
      {sub && <p className="text-xs text-muted mt-1.5">{sub}</p>}
    </div>
  )
}

export function Bar({ label, count, total, mono = false }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  return (
    <div className="flex items-center gap-3">
      <span
        className={`w-40 shrink-0 truncate text-sm ${mono ? 'font-mono text-[13px] text-navy' : 'text-ink'}`}
        title={label}
      >
        {label}
      </span>
      <div className="flex-1 h-1.5 rounded-full bg-line overflow-hidden">
        <div className="h-full rounded-full bg-navy" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right font-mono text-xs text-muted tnum">{count}</span>
    </div>
  )
}

export function Card({ title, action, children, className = '' }) {
  return (
    <section className={`card overflow-hidden ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-line">
          <h2 className="text-sm font-semibold text-navy">{title}</h2>
          {action}
        </div>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  )
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 className="text-xl font-semibold text-navy tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

export function ErrorBox({ message }) {
  if (!message) return null
  return (
    <div className="border border-stop/25 bg-stop/[0.06] text-stop rounded-md px-4 py-2.5 text-sm flex items-center gap-2">
      <span className="font-mono text-xs uppercase tracking-wider">error</span>
      <span className="text-ink/80">{message}</span>
    </div>
  )
}

export function Loading({ label = 'Cargando…' }) {
  return (
    <div className="flex items-center gap-2 text-muted text-sm py-6 justify-center">
      <Spinner /> {label}
    </div>
  )
}

export function Empty({ children }) {
  return <p className="text-center text-muted text-sm py-8">{children}</p>
}

// Fila etiqueta/valor para drawers de detalle.
export function Field({ label, value, mono = false }) {
  if (value === null || value === undefined || value === '') return null
  return (
    <div>
      <p className="eyebrow mb-0.5">{label}</p>
      <p className={`text-sm text-ink ${mono ? 'font-mono text-[13px] break-all' : ''}`}>{value}</p>
    </div>
  )
}

// Bloque de sección dentro de un drawer.
export function DetailBlock({ title, children }) {
  return (
    <section className="card overflow-hidden">
      <div className="px-4 py-2.5 border-b border-line">
        <p className="eyebrow">{title}</p>
      </div>
      <div className="px-4 py-3">{children}</div>
    </section>
  )
}
