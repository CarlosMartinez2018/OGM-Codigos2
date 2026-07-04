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
