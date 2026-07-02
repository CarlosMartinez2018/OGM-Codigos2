import { useState, useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Seal } from './ui'
import { metaApi } from '../lib/api'

const NAV = [
  { to: '/dashboard', label: 'Panel', code: '00' },
  { to: '/inbox', label: 'Bandeja', code: '01' },
  { to: '/classifications', label: 'Clasificaciones', code: '02' },
  { to: '/reviews', label: 'Cola de revisión', code: '03' },
  { to: '/lenders', label: 'Lenders', code: '04' },
  { to: '/waivers', label: 'Matriz waivers', code: '05' },
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
        <span className={`w-1.5 h-1.5 rounded-full ${llm ? 'bg-brass' : 'bg-white/20'}`} />
        <span>{llm ? 'llm on' : 'llm off · reglas'}</span>
      </div>
    </div>
  )
}

export default function Layout() {
  return (
    <div className="min-h-screen flex bg-paper">
      <aside className="w-60 bg-navy text-white flex flex-col shrink-0 shadow-rail sticky top-0 h-screen">
        <div className="px-4 py-5 flex items-center gap-3 border-b border-white/10">
          <Seal />
          <div className="leading-tight">
            <p className="font-semibold tracking-tight">Acento Partners</p>
            <p className="text-[11px] text-brass font-mono tracking-wider">WAIVER · CONTROL</p>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-0.5">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? 'bg-white/10 text-white border-l-2 border-brass -ml-[2px] pl-[calc(0.75rem-2px)]'
                    : 'text-white/70 hover:text-white hover:bg-white/[0.06] border-l-2 border-transparent -ml-[2px] pl-[calc(0.75rem-2px)]'
                }`
              }
            >
              <span className="font-mono text-[11px] text-white/35 group-hover:text-brass w-5">{n.code}</span>
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
