import { useEffect } from 'react'

// Diálogo centrado. Cierra con overlay o Esc.
export default function Modal({ open, onClose, title, children, width = 'max-w-lg' }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-navy/40" onClick={onClose} />
      <div className={`relative w-full ${width} bg-surface rounded-xl shadow-rail`} role="dialog" aria-modal="true">
        <header className="flex items-center justify-between px-6 py-4 border-b border-line">
          <h2 className="text-base font-semibold text-navy">{title}</h2>
          <button onClick={onClose} className="text-muted hover:text-navy text-xl leading-none" aria-label="Cerrar">×</button>
        </header>
        {children}
      </div>
    </div>
  )
}
