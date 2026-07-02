import { useState, useEffect, useCallback } from 'react'
import { metaApi, classificationsApi } from '../lib/api'
import { Kpi, Bar, Card, PageHeader, Spinner, Loading, Empty, ErrorBox } from '../components/ui'

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
    <div className="p-8 space-y-7 max-w-6xl">
      <PageHeader
        title="Panel de control"
        subtitle="Actividad del pipeline de clasificación de waivers."
        actions={
          <button onClick={runClassification} disabled={running} className="btn btn-primary">
            {running && <Spinner className="border-white/40 border-t-white" />}
            Clasificar pendientes
          </button>
        }
      />

      <ErrorBox message={error} />

      {loading ? (
        <Loading />
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Kpi label="Correos" value={stats?.total_emails ?? 0} sub="en bandeja de producción" />
            <Kpi label="Clasificados" value={totalCls} sub="sobrevivientes del pre-filtrado" />
            <Kpi
              label="Confianza media"
              value={stats?.avg_confidence != null ? `${Math.round(stats.avg_confidence * 100)}%` : '—'}
            />
            <Kpi
              label="En revisión"
              value={pendingReviews}
              sub="cola manual pendiente"
              tone={pendingReviews > 0 ? 'stop' : 'brass'}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <Card title="Clasificaciones por lender">
              {byLender.length === 0 ? (
                <Empty>Sin datos de clasificación aún.</Empty>
              ) : (
                <div className="space-y-3">
                  {byLender.map(([name, count]) => (
                    <Bar key={name} label={name} count={count} total={totalCls} />
                  ))}
                </div>
              )}
            </Card>

            <Card title="Cola de revisión por etapa">
              {byStage.length === 0 ? (
                <Empty>Cola vacía.</Empty>
              ) : (
                <div className="space-y-3">
                  {byStage.map(([stage, count]) => (
                    <Bar key={stage} label={stage} count={count} total={pendingReviews} mono />
                  ))}
                </div>
              )}
            </Card>
          </div>

          <Card title="Lenders por estado">
            <div className="grid grid-cols-3 divide-x divide-line">
              {byStatus.map(([status, count]) => (
                <div key={status} className="px-4 first:pl-0">
                  <p className="text-3xl font-mono font-medium text-navy tnum">{count}</p>
                  <p className="eyebrow mt-1.5">{status}</p>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
