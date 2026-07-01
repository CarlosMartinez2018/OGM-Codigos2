import { useState, useEffect, useCallback } from 'react'
import { metaApi, classificationsApi } from '../lib/api'
import { Kpi, Bar, Spinner, ErrorBox } from '../components/ui'

export default function DashboardPage() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    metaApi.stats()
      .then(setStats)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const runClassification = async () => {
    setRunning(true)
    setError('')
    try {
      await classificationsApi.run(0, false)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  const byLender = stats?.classifications_by_lender
    ? Object.entries(stats.classifications_by_lender).sort((a, b) => b[1] - a[1]).slice(0, 8)
    : []
  const byStage = stats?.pending_reviews_by_stage
    ? Object.entries(stats.pending_reviews_by_stage).sort((a, b) => b[1] - a[1])
    : []
  const byStatus = stats?.lenders_by_status ? Object.entries(stats.lenders_by_status) : []
  const pendingReviews = byStage.reduce((acc, [, n]) => acc + n, 0)
  const totalCls = stats?.total_classified ?? 0

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">Actividad del pipeline de clasificación.</p>
        </div>
        <button
          onClick={runClassification}
          disabled={running}
          className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
        >
          {running && <Spinner />} Clasificar pendientes
        </button>
      </div>

      <ErrorBox message={error} />

      {loading ? (
        <div className="flex items-center gap-2 text-slate-400"><Spinner /> Cargando…</div>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Kpi label="Correos" value={stats?.total_emails ?? 0} sub="en production_emails" />
            <Kpi label="Clasificados" value={totalCls} sub="sobrevivientes del preflight" />
            <Kpi label="Confianza prom." value={stats?.avg_confidence != null ? `${Math.round(stats.avg_confidence * 100)}%` : '—'} />
            <Kpi label="En revisión" value={pendingReviews} sub="cola email_reviews (PENDIENTE)" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <section className="bg-white rounded-xl border border-slate-200 p-5">
              <h2 className="text-sm font-semibold text-slate-800 mb-4">Clasificaciones por lender</h2>
              {byLender.length === 0 ? (
                <p className="text-sm text-slate-400">Sin datos aún.</p>
              ) : (
                <div className="space-y-3">
                  {byLender.map(([name, count]) => (
                    <Bar key={name} label={name} count={count} total={totalCls} color="bg-blue-600" />
                  ))}
                </div>
              )}
            </section>

            <section className="bg-white rounded-xl border border-slate-200 p-5">
              <h2 className="text-sm font-semibold text-slate-800 mb-4">Cola de revisión por etapa</h2>
              {byStage.length === 0 ? (
                <p className="text-sm text-slate-400">Cola vacía.</p>
              ) : (
                <div className="space-y-3">
                  {byStage.map(([stage, count]) => (
                    <Bar key={stage} label={stage} count={count} total={pendingReviews} color="bg-amber-500" />
                  ))}
                </div>
              )}
            </section>
          </div>

          <section className="bg-white rounded-xl border border-slate-200 p-5">
            <h2 className="text-sm font-semibold text-slate-800 mb-4">Lenders por estado</h2>
            <div className="flex flex-wrap gap-6">
              {byStatus.map(([status, count]) => (
                <div key={status}>
                  <p className="text-2xl font-bold text-slate-900">{count}</p>
                  <p className="text-xs text-slate-400">{status}</p>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  )
}
