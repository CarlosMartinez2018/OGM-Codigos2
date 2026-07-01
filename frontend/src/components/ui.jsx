// Componentes UI minimos reutilizables.

export function Spinner() {
  return (
    <span className="inline-block w-4 h-4 border-2 border-slate-300 border-t-blue-600 rounded-full animate-spin" />
  )
}

const STATUS_STYLES = {
  APROBADO: 'bg-emerald-100 text-emerald-700',
  POR_APROBAR: 'bg-amber-100 text-amber-700',
  NO_APROBADO: 'bg-red-100 text-red-700',
  PENDIENTE: 'bg-amber-100 text-amber-700',
  GESTIONADO: 'bg-slate-100 text-slate-600',
  high: 'bg-emerald-100 text-emerald-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-red-100 text-red-700',
}

export function Badge({ children, tone }) {
  const cls = STATUS_STYLES[tone] || 'bg-slate-100 text-slate-600'
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {children}
    </span>
  )
}

export function Kpi({ label, value, sub }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 px-5 py-4">
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">{label}</p>
      <p className="text-3xl font-bold text-slate-900 mt-1 leading-none">{value ?? '—'}</p>
      {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
    </div>
  )
}

export function Bar({ label, count, total, color = 'bg-blue-500' }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-slate-700 w-40 shrink-0 truncate" title={label}>{label}</span>
      <div className="flex-1 h-2 rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-500 w-8 text-right font-mono">{count}</span>
    </div>
  )
}

export function ErrorBox({ message }) {
  if (!message) return null
  return (
    <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-2 text-sm">
      {message}
    </div>
  )
}
