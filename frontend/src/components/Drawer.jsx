import { useEffect } from 'react'

// Panel lateral deslizante. Cierra con overlay o Esc.
export default function Drawer({ open, onClose, title, children, width = 'max-w-2xl' }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <div className={`fixed inset-0 z-40 ${open ? '' : 'pointer-events-none'}`} aria-hidden={!open}>
      <div
        className={`absolute inset-0 bg-navy/30 transition-opacity ${open ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
      />
      <aside
        className={`absolute right-0 top-0 h-full w-full ${width} bg-paper shadow-rail flex flex-col transition-transform duration-200 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
        role="dialog"
        aria-modal="true"
      >
        <header className="flex items-start justify-between gap-4 px-6 py-4 border-b border-line bg-surface">
          <h2 className="text-base font-semibold text-navy leading-snug pr-4">{title}</h2>
          <button
            onClick={onClose}
            className="text-muted hover:text-navy text-xl leading-none shrink-0 mt-0.5"
            aria-label="Cerrar"
          >
            ×
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-5">{open && children}</div>
      </aside>
    </div>
  )
}
