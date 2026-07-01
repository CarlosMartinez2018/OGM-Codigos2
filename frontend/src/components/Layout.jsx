import { NavLink, Outlet } from 'react-router-dom'

const NAV = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/inbox', label: 'Inbox' },
  { to: '/classifications', label: 'Clasificaciones' },
  { to: '/reviews', label: 'Cola de revisión' },
  { to: '/lenders', label: 'Lenders' },
]

export default function Layout() {
  return (
    <div className="min-h-screen flex">
      <aside className="w-56 bg-white border-r border-slate-200 flex flex-col shrink-0">
        <div className="px-5 py-5 border-b border-slate-100">
          <p className="font-bold text-slate-900 leading-tight">OGM Lenders</p>
          <p className="text-xs text-slate-400">Clasificador de waivers</p>
        </div>
        <nav className="p-3 space-y-1">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `block px-3 py-2 rounded-lg text-sm font-medium ${
                  isActive ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-50'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="flex-1 min-w-0">
        <Outlet />
      </main>
    </div>
  )
}
