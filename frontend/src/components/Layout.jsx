import { useState, useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { LayoutDashboard, Inbox, Sparkles, Building2, Table2, FolderTree, Menu, X } from 'lucide-react'
import { metaApi } from '../lib/api'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/inbox', label: 'Inbox', Icon: Inbox, countKey: 'emails' },
  { to: '/classifications', label: 'Classifications', Icon: Sparkles, countKey: 'classified' },
  { to: '/lenders', label: 'Lenders', Icon: Building2, countKey: 'pendingLenders' },
  { to: '/waivers', label: 'Waiver matrix', Icon: Table2 },
  { to: '/sharepoint', label: 'SharePoint', Icon: FolderTree },
]

// Pulso: sparkline de distribución de confianza (real) + contadores vivos.
// Elemento firma del rail: la salud del pipeline, siempre a la vista.
function NavPulse({ stats }) {
  if (!stats) return null
  const conf = stats.classifications_by_confidence || {}
  const bars = [
    { key: 'low', v: conf.low || 0, cls: 'bg-white/25' },
    { key: 'medium', v: conf.medium || 0, cls: 'bg-coral/60' },
    { key: 'high', v: conf.high || 0, cls: 'bg-coral' },
  ]
  const max = Math.max(1, ...bars.map((b) => b.v))
  const pending = Object.values(stats.pending_reviews_by_stage || {}).reduce((a, b) => a + b, 0)

  return (
    <div className="mx-3 mb-2 rounded-lg bg-white/[0.04] border border-white/10 px-3 py-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-label text-white/40">Pulse</span>
        <span className="font-mono text-[10px] text-coral tnum" title="Average confidence">
          {Math.round((stats.avg_confidence || 0) * 100)}%
        </span>
      </div>
      <div className="flex items-end gap-1 h-8 mb-2.5">
        {bars.map((b) => (
          <div key={b.key} className="flex-1 flex flex-col justify-end" title={`${b.key} confidence: ${b.v}`}>
            <div
              className={`${b.cls} rounded-sm transition-all duration-500`}
              style={{ height: `${Math.max(6, (b.v / max) * 100)}%` }}
            />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-1 text-center">
        <PulseStat n={stats.total_emails} label="emails" />
        <PulseStat n={stats.total_classified} label="classified" />
        <PulseStat n={pending} label="review" tone={pending > 0 ? 'coral' : 'dim'} />
      </div>
    </div>
  )
}

function PulseStat({ n, label, tone = 'dim' }) {
  return (
    <div>
      <div className={`font-mono text-sm tnum ${tone === 'coral' ? 'text-coral' : 'text-white/85'}`}>{n ?? '—'}</div>
      <div className="text-[9px] uppercase tracking-wider text-white/35">{label}</div>
    </div>
  )
}

function HealthDot() {
  const [health, setHealth] = useState(null)
  useEffect(() => {
    let alive = true
    const tick = () => metaApi.health().then((h) => alive && setHealth(h)).catch(() => alive && setHealth({ status: 'down' }))
    tick()
    const id = setInterval(tick, 15000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const up = health?.status === 'healthy'
  const llm = health?.llm?.enabled
  return (
    <div className="px-4 py-3 border-t border-white/10 text-[11px] font-mono text-white/50 space-y-1.5">
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full ${up ? 'bg-ok' : health ? 'bg-stop' : 'bg-white/30'}`} />
        <span>{up ? 'backend online' : health ? 'backend down' : 'checking…'}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full ${llm ? 'bg-coral' : 'bg-white/20'}`} />
        <span>{llm ? 'llm on' : 'llm off · rules'}</span>
      </div>
    </div>
  )
}

export default function Layout() {
  const [stats, setStats] = useState(null)
  useEffect(() => {
    let alive = true
    const tick = () => metaApi.stats().then((s) => alive && setStats(s)).catch(() => {})
    tick()
    const id = setInterval(tick, 15000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const [navOpen, setNavOpen] = useState(false)

  const counts = {
    emails: stats?.total_emails,
    classified: stats?.total_classified,
    pendingLenders: stats?.lenders_by_status?.POR_APROBAR,
  }

  return (
    <div className="min-h-screen flex bg-paper">
      {/* Overlay móvil */}
      {navOpen && (
        <div className="fixed inset-0 bg-navyink/40 z-30 md:hidden" onClick={() => setNavOpen(false)} />
      )}

      <aside className={`w-60 bg-navy text-white flex flex-col shrink-0 shadow-rail h-screen z-40
        fixed md:sticky top-0 transition-transform duration-200
        ${navOpen ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0`}>
        <div className="px-5 py-5 border-b border-white/10 flex items-start justify-between">
          <div>
            <img
              src="/acento-logo.png"
              alt="Acento Real Estate Partners"
              className="w-full max-w-[180px] h-auto"
            />
            <p className="text-[11px] text-coral font-mono tracking-wider mt-2.5">WAIVER · CONTROL</p>
          </div>
          <button onClick={() => setNavOpen(false)} className="md:hidden text-white/60 hover:text-white" aria-label="Close menu">
            <X size={20} />
          </button>
        </div>

        <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
          {NAV.map((n) => {
            const c = n.countKey ? counts[n.countKey] : undefined
            return (
              <NavLink
                key={n.to}
                to={n.to}
                onClick={() => setNavOpen(false)}
                className={({ isActive }) =>
                  `group flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                    isActive
                      ? 'bg-white/10 text-white border-l-2 border-coral -ml-[2px] pl-[calc(0.75rem-2px)]'
                      : 'text-white/70 hover:text-white hover:bg-white/[0.06] border-l-2 border-transparent -ml-[2px] pl-[calc(0.75rem-2px)]'
                  }`
                }
              >
                <n.Icon size={17} strokeWidth={1.75} className="w-5 text-white/45 group-hover:text-coral shrink-0 transition-colors" />
                <span className="font-medium flex-1">{n.label}</span>
                {typeof c === 'number' && (
                  <span className="font-mono text-[11px] tnum text-white/40 group-hover:text-coral transition-colors">{c}</span>
                )}
              </NavLink>
            )
          })}
        </nav>

        <NavPulse stats={stats} />
        <HealthDot />
      </aside>

      <main className="flex-1 min-w-0">
        {/* Topbar móvil */}
        <div className="md:hidden sticky top-0 z-20 flex items-center gap-3 bg-navy text-white px-4 py-3 shadow-rail">
          <button onClick={() => setNavOpen(true)} aria-label="Open menu" className="text-white/80 hover:text-white">
            <Menu size={22} />
          </button>
          <span className="text-[11px] text-coral font-mono tracking-wider">WAIVER · CONTROL</span>
        </div>
        <Outlet />
      </main>
    </div>
  )
}
