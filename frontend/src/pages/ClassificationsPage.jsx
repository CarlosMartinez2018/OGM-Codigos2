import { useState, useEffect, useCallback } from 'react'
import { classificationsApi } from '../lib/api'
import { Stamp, stampTone, PageHeader, Loading, Empty, ErrorBox } from '../components/ui'

export default function ClassificationsPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [level, setLevel] = useState('')

  const load = useCallback((lvl) => {
    setLoading(true)
    classificationsApi.list({ limit: 100, confidence_level: lvl })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load('') }, [load])

  return (
    <div className="p-8 space-y-6 max-w-6xl">
      <PageHeader
        title="Clasificaciones"
        subtitle={`${data.total} resultados del clasificador.`}
        actions={
          <select
            value={level}
            onChange={(e) => { setLevel(e.target.value); load(e.target.value) }}
            className="field"
          >
            <option value="">Toda confianza</option>
            <option value="high">Alta</option>
            <option value="medium">Media</option>
            <option value="low">Baja</option>
          </select>
        }
      />

      <ErrorBox message={error} />

      {loading ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <Empty>Sin clasificaciones.</Empty>
      ) : (
        <div className="space-y-3">
          {data.items.map((c) => {
            const conf = Math.round((c.confidence_score ?? 0) * 100)
            return (
              <article
                key={c.id}
                className={`card overflow-hidden border-l-2 ${
                  c.confidence_level === 'high' ? 'border-ok' : c.confidence_level === 'medium' ? 'border-warn' : 'border-stop'
                }`}
              >
                <div className="px-5 py-4 flex items-start justify-between gap-5">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-navy">{c.lender}</span>
                      <span className="text-faint">·</span>
                      <span className="text-ink">{c.waiver_type}</span>
                      {c.escalate_for_review && <Stamp tone="stop">escalar</Stamp>}
                    </div>
                    {c.trigger_description && (
                      <p className="text-xs text-muted mt-1.5">{c.trigger_description}</p>
                    )}
                    {c.secondary_issues?.length > 0 && (
                      <p className="text-xs text-muted mt-1">
                        <span className="eyebrow">Secundarios</span>{' '}
                        {c.secondary_issues.join(' · ')}
                      </p>
                    )}
                    {c.documents_expected?.length > 0 && (
                      <p className="text-xs text-muted mt-1">
                        <span className="eyebrow">Docs</span>{' '}
                        {c.documents_expected.join(' · ')}
                      </p>
                    )}
                  </div>
                  <div className="text-right shrink-0 space-y-1.5">
                    <Stamp tone={stampTone(c.confidence_level)}>
                      {c.confidence_level} · {conf}%
                    </Stamp>
                    <p className="font-mono text-[11px] text-faint uppercase tracking-wider">
                      {c.communication_category}
                    </p>
                    {c.suggested_attachments?.length > 0 && (
                      <p className="font-mono text-[11px] text-brassdim">
                        {c.suggested_attachments.length} adj.
                      </p>
                    )}
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
