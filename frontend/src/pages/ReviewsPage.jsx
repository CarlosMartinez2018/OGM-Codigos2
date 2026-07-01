import { useState, useEffect, useCallback } from 'react'
import { reviewsApi } from '../lib/api'
import { Badge, Spinner, ErrorBox } from '../components/ui'

const STAGES = [
  'blacklist', 'lender_nuevo', 'lender_por_aprobar',
  'hilo_incompleto', 'reenvio', 'seguridad_bloqueo', 'duplicado',
]

export default function ReviewsPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [stage, setStage] = useState('')

  const load = useCallback((stageFilter) => {
    setLoading(true)
    reviewsApi.list({ limit: 200, status: 'PENDIENTE', stage: stageFilter })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load('') }, [load])

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Cola de revisión</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {data.total} correos PENDIENTE (descartados por el preflight).
          </p>
        </div>
        <select
          value={stage}
          onChange={(e) => { setStage(e.target.value); load(e.target.value) }}
          className="px-3 py-2 rounded-lg border border-slate-200 text-sm"
        >
          <option value="">Todas las etapas</option>
          {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <ErrorBox message={error} />

      {loading ? (
        <div className="flex items-center gap-2 text-slate-400"><Spinner /> Cargando…</div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-2 font-semibold">Etapa</th>
                <th className="text-left px-4 py-2 font-semibold">Motivo</th>
                <th className="text-left px-4 py-2 font-semibold">Remitente orig.</th>
                <th className="text-left px-4 py-2 font-semibold">Creado</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-2"><Badge tone="PENDIENTE">{r.stage}</Badge></td>
                  <td className="px-4 py-2 text-slate-600 max-w-lg truncate" title={r.reason}>{r.reason}</td>
                  <td className="px-4 py-2 text-slate-500">{r.detected_original_sender || '—'}</td>
                  <td className="px-4 py-2 text-slate-500 whitespace-nowrap">
                    {r.created_at ? r.created_at.slice(0, 10) : '—'}
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-6 text-center text-slate-400">Cola vacía.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
