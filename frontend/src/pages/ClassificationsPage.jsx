import { useState, useEffect, useCallback } from 'react'
import { classificationsApi } from '../lib/api'
import { Badge, Spinner, ErrorBox } from '../components/ui'

export default function ClassificationsPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [level, setLevel] = useState('')

  const load = useCallback((confidenceLevel) => {
    setLoading(true)
    classificationsApi.list({ limit: 100, confidence_level: confidenceLevel })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load('') }, [load])

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Clasificaciones</h1>
          <p className="text-sm text-slate-500 mt-0.5">{data.total} resultados.</p>
        </div>
        <select
          value={level}
          onChange={(e) => { setLevel(e.target.value); load(e.target.value) }}
          className="px-3 py-2 rounded-lg border border-slate-200 text-sm"
        >
          <option value="">Toda confianza</option>
          <option value="high">high</option>
          <option value="medium">medium</option>
          <option value="low">low</option>
        </select>
      </div>

      <ErrorBox message={error} />

      {loading ? (
        <div className="flex items-center gap-2 text-slate-400"><Spinner /> Cargando…</div>
      ) : (
        <div className="space-y-3">
          {data.items.map((c) => (
            <div key={c.id} className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-slate-900">{c.lender}</span>
                    <span className="text-slate-400">·</span>
                    <span className="text-slate-700">{c.waiver_type}</span>
                    {c.escalate_for_review && <Badge tone="NO_APROBADO">escalar</Badge>}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">{c.trigger_description}</p>
                  {c.secondary_issues?.length > 0 && (
                    <p className="text-xs text-slate-400 mt-1">
                      Secundarios: {c.secondary_issues.join(', ')}
                    </p>
                  )}
                  {c.documents_expected?.length > 0 && (
                    <p className="text-xs text-slate-400 mt-1">
                      Docs: {c.documents_expected.join(', ')}
                    </p>
                  )}
                </div>
                <div className="text-right shrink-0 space-y-1">
                  <Badge tone={c.confidence_level}>
                    {c.confidence_level} · {Math.round((c.confidence_score ?? 0) * 100)}%
                  </Badge>
                  <p className="text-[10px] text-slate-400">{c.communication_category}</p>
                  {c.suggested_attachments?.length > 0 && (
                    <p className="text-[10px] text-slate-400">{c.suggested_attachments.length} adjunto(s)</p>
                  )}
                </div>
              </div>
            </div>
          ))}
          {data.items.length === 0 && (
            <p className="text-center text-slate-400 py-6">Sin clasificaciones.</p>
          )}
        </div>
      )}
    </div>
  )
}
