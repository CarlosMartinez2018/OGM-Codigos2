import { useState, useEffect, useCallback } from 'react'
import { Mail, Sparkles, AlertTriangle, Building2 } from 'lucide-react'
import { metaApi, classificationsApi } from '../lib/api'
import { StatCard, StatStrip, Bar, Card, PageHeader, Spinner, Loading, Empty, ErrorBox, stageLabel } from '../components/ui'

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
        title="Dashboard"
        subtitle="Waiver classification pipeline activity."
        actions={
          <button onClick={runClassification} disabled={running} className="btn btn-coral">
            {running && <Spinner className="border-white/40 border-t-white" />}
            Classify pending
          </button>
        }
      />

      <ErrorBox message={error} />

      {loading ? (
        <Loading />
      ) : (
        <>
          {/* Hero: estado del pipeline, readout sobre navy — firma del panel */}
          <section className="relative overflow-hidden rounded-2xl bg-navy text-white px-7 py-6"
            style={{ backgroundImage: 'radial-gradient(120% 120% at 100% 0%, rgba(226,102,75,0.20), transparent 55%)' }}>
            <div className="flex flex-wrap items-end justify-between gap-6">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-label text-coral">Batch average confidence</p>
                <p className="display text-6xl leading-tight mt-2 tnum pt-1 pb-1">
                  {stats?.avg_confidence != null ? `${Math.round(stats.avg_confidence * 100)}` : '—'}
                  <span className="text-2xl text-white/50 ml-1">%</span>
                </p>
                <p className="text-sm text-white/60 mt-2.5">
                  {totalCls} of {stats?.total_emails ?? 0} emails classified by rules
                </p>
              </div>
              {/* Distribución de confianza en barras */}
              <div className="flex items-end gap-2 h-20">
                {[['low', 'low', 'bg-white/25'], ['medium', 'medium', 'bg-coral/60'], ['high', 'high', 'bg-coral']].map(([k, lbl, cls]) => {
                  const conf = stats?.classifications_by_confidence || {}
                  const mx = Math.max(1, ...Object.values(conf))
                  const v = conf[k] || 0
                  return (
                    <div key={k} className="flex flex-col items-center gap-1.5 w-12">
                      <span className="font-mono text-xs text-white/70 tnum">{v}</span>
                      <div className={`${cls} w-full rounded-md transition-all duration-700`} style={{ height: `${Math.max(6, (v / mx) * 56)}px` }} />
                      <span className="text-[10px] uppercase tracking-wider text-white/40">{lbl}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          </section>

          <StatStrip>
            <StatCard icon={Mail} tone="navy" label="Emails" value={stats?.total_emails ?? 0} sub="in production inbox" />
            <StatCard icon={Sparkles} tone="coral" label="Classified" value={totalCls} sub="survived the pre-filter" />
            <StatCard icon={Building2} tone="ok" label="Active lenders" value={byStatus.reduce((a, [, n]) => a + n, 0)} sub="mapped domains" />
            <StatCard
              icon={AlertTriangle}
              tone={pendingReviews > 0 ? 'stop' : 'ok'}
              label="Under review"
              value={pendingReviews}
              sub="pending manual queue"
            />
          </StatStrip>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <Card title="Classifications by lender">
              {byLender.length === 0 ? (
                <Empty>No classification data yet.</Empty>
              ) : (
                <div className="space-y-3">
                  {byLender.map(([name, count]) => (
                    <Bar key={name} label={name} count={count} total={totalCls} />
                  ))}
                </div>
              )}
            </Card>

            <Card title="Review queue by stage">
              {byStage.length === 0 ? (
                <Empty>Queue empty.</Empty>
              ) : (
                <div className="space-y-3">
                  {byStage.map(([stage, count]) => (
                    <Bar key={stage} label={stageLabel(stage)} count={count} total={pendingReviews} tone="alert" />
                  ))}
                </div>
              )}
            </Card>
          </div>

          <Card title="Lenders by status">
            <div className="grid grid-cols-3 divide-x divide-line">
              {byStatus.map(([status, count]) => (
                <div key={status} className="px-4 first:pl-0">
                  <p className="display text-4xl text-navy tnum pt-1">{count}</p>
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
