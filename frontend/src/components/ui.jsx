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

// KPI tipo readout de terminal: número display grande, etiqueta en versalitas, lomo latón.
export function Kpi({ label, value, sub, tone = 'coral' }) {
  const tick = tone === 'coral' ? 'border-coral' : tone === 'stop' ? 'border-stop' : 'border-navy'
  const accent = tone === 'stop' ? 'text-stop' : 'text-navy'
  return (
    <div className={`card card-hover px-5 py-4 border-l-[3px] ${tick}`}>
      <p className="eyebrow">{label}</p>
      <p className={`display text-[2.4rem] leading-normal ${accent} mt-2 tnum`}>
        {value ?? '—'}
      </p>
      {sub && <p className="text-xs text-muted mt-2">{sub}</p>}
    </div>
  )
}

// Tarjeta de estadística limpia: chip de icono + etiqueta + número display.
// Menos recargada que Kpi (sin lomo grueso). tone controla el color del chip.
const STAT_TONES = {
  navy: 'bg-navy/[0.06] text-navy',
  coral: 'bg-coralsoft text-coraldim',
  ok: 'bg-ok/10 text-ok',
  warn: 'bg-warn/10 text-warn',
  stop: 'bg-stop/10 text-stop',
}

export function StatCard({ icon: Icon, label, value, sub, tone = 'navy' }) {
  return (
    <div className="card px-5 py-4">
      <div className="flex items-center justify-between gap-2">
        <p className="eyebrow">{label}</p>
        {Icon && (
          <span className={`grid place-items-center w-8 h-8 rounded-lg ${STAT_TONES[tone] || STAT_TONES.navy}`}>
            <Icon size={16} strokeWidth={1.9} />
          </span>
        )}
      </div>
      <p className="display text-[2rem] leading-normal text-navy mt-2 tnum">{value ?? '—'}</p>
      {sub && <p className="text-xs text-muted mt-1.5">{sub}</p>}
    </div>
  )
}

// Rejilla responsiva para un strip de StatCards.
export function StatStrip({ children, cols = 4 }) {
  const grid = cols === 3 ? 'lg:grid-cols-3' : 'lg:grid-cols-4'
  return <div className={`grid grid-cols-2 ${grid} gap-3`}>{children}</div>
}

// snake_case / camelCase técnico -> texto legible ("hilo_incompleto" -> "Hilo incompleto").
export function humanize(s) {
  if (!s) return s
  const t = String(s).replace(/[_-]+/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').trim().toLowerCase()
  return t.charAt(0).toUpperCase() + t.slice(1)
}

export function Bar({ label, count, total, mono = false, tone = 'navy' }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  const fill = tone === 'alert' ? 'bg-coral' : 'bg-navy'
  return (
    <div className="flex items-center gap-3 group">
      <span
        className={`w-40 shrink-0 truncate text-sm ${mono ? 'font-mono text-[13px] text-navy' : 'text-ink'}`}
        title={label}
      >
        {label}
      </span>
      <div className="flex-1 h-2 rounded-full bg-[#EDF2F7] overflow-hidden">
        <div
          className={`h-full rounded-full transition-[width] duration-700 ease-out ${fill}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-9 text-right font-mono text-xs text-muted tnum">{count}</span>
    </div>
  )
}

export function Card({ title, action, children, className = '' }) {
  return (
    <section className={`card overflow-hidden ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-line bg-surfacealt">
          <h2 className="display text-[15px] text-navy">{title}</h2>
          {action}
        </div>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  )
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="flex items-start justify-between gap-4 flex-wrap pb-1">
      <div>
        <div className="flex items-center gap-2.5">
          <span className="h-6 w-1 rounded-full bg-coral" aria-hidden="true" />
          <h1 className="display text-[1.75rem] leading-tight text-navy pt-0.5">{title}</h1>
        </div>
        {subtitle && <p className="text-sm text-muted mt-2 ml-3.5 max-w-[65ch]">{subtitle}</p>}
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
