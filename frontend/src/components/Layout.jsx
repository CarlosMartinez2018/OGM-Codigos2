import { useState, useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { LayoutDashboard, Inbox, Sparkles, Building2, Table2, FolderTree } from 'lucide-react'
import { metaApi } from '../lib/api'

const NAV = [
  { to: '/dashboard', label: 'Panel', Icon: LayoutDashboard },
  { to: '/inbox', label: 'Bandeja', Icon: Inbox },
  { to: '/classifications', label: 'Clasificaciones', Icon: Sparkles },
  { to: '/lenders', label: 'Lenders', Icon: Building2 },
  { to: '/waivers', label: 'Matriz waivers', Icon: Table2 },
  { to: '/sharepoint', label: 'SharePoint', Icon: FolderTree },
]

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
        <span>{up ? 'backend online' : health ? 'backend down' : 'checando…'}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full ${llm ? 'bg-coral' : 'bg-white/20'}`} />
        <span>{llm ? 'llm on' : 'llm off · reglas'}</span>
      </div>
    </div>
  )
}

export default function Layout() {
  return (
    <div className="min-h-screen flex bg-paper">
      <aside className="w-60 bg-navy text-white flex flex-col shrink-0 shadow-rail sticky top-0 h-screen">
        <div className="px-5 py-5 border-b border-white/10">
          <img
            src="/acento-logo.png"
            alt="Acento Real Estate Partners"
            className="w-full max-w-[180px] h-auto"
          />
          <p className="text-[11px] text-coral font-mono tracking-wider mt-2.5">WAIVER · CONTROL</p>
        </div>

        <nav className="flex-1 p-3 space-y-0.5">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? 'bg-white/10 text-white border-l-2 border-coral -ml-[2px] pl-[calc(0.75rem-2px)]'
                    : 'text-white/70 hover:text-white hover:bg-white/[0.06] border-l-2 border-transparent -ml-[2px] pl-[calc(0.75rem-2px)]'
                }`
              }
            >
              <n.Icon size={17} strokeWidth={1.75} className="w-5 text-white/45 group-hover:text-coral shrink-0" />
              <span className="font-medium">{n.label}</span>
            </NavLink>
          ))}
        </nav>

        <HealthDot />
      </aside>

      <main className="flex-1 min-w-0">
        <Outlet />
      </main>
    </div>
  )
}
