import { useState, useEffect, useCallback } from 'react'
import { reviewsApi } from '../lib/api'
import { Stamp, PageHeader, Loading, Empty, ErrorBox } from '../components/ui'

const STAGES = [
  'blacklist', 'lender_nuevo', 'lender_por_aprobar',
  'hilo_incompleto', 'reenvio', 'seguridad_bloqueo', 'duplicado',
]

export default function ReviewsPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [stage, setStage] = useState('')

  const load = useCallback((s) => {
    setLoading(true)
    reviewsApi.list({ limit: 200, status: 'PENDIENTE', stage: s })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load('') }, [load])

  return (
    <div className="p-8 space-y-6 max-w-6xl">
      <PageHeader
        title="Cola de revisión"
        subtitle={`${data.total} correos pendientes — descartados por el pre-filtrado.`}
        actions={
          <select
            value={stage}
            onChange={(e) => { setStage(e.target.value); load(e.target.value) }}
            className="field"
          >
            <option value="">Todas las etapas</option>
            {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        }
      />

      <ErrorBox message={error} />

      {loading ? (
        <Loading />
      ) : (
        <div className="card overflow-hidden">
          <table className="ledger">
            <thead>
              <tr>
                <th>Etapa</th>
                <th>Motivo</th>
                <th>Remitente original</th>
                <th className="text-right">Creado</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id}>
                  <td><Stamp tone="warn">{r.stage}</Stamp></td>
                  <td className="text-muted max-w-lg truncate" title={r.reason}>{r.reason}</td>
                  <td>
                    {r.detected_original_sender
                      ? <span className="token">{r.detected_original_sender}</span>
                      : <span className="text-faint">—</span>}
                  </td>
                  <td className="text-right font-mono text-xs text-muted whitespace-nowrap tnum">
                    {r.created_at ? r.created_at.slice(0, 10) : '—'}
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr><td colSpan={4}><Empty>Cola vacía.</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
