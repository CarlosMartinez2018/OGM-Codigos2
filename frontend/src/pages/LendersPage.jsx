import { useState, useEffect, useCallback, useMemo } from 'react'
import { lendersApi } from '../lib/api'
import Tabs from '../components/Tabs'
import { Stamp, stampTone, PageHeader, Spinner, Loading, Empty, ErrorBox, StatCard, StatStrip } from '../components/ui'
import { Building2, CheckCircle2, Clock, Ban } from 'lucide-react'

// Campo de estado real (api.py): l.status ∈ APROBADO | POR_APROBAR | NO_APROBADO.
// Blacklist = NO_APROBADO.
const TABS = [
  { key: 'APROBADO', label: 'Approved' },
  { key: 'POR_APROBAR', label: 'To approve' },
  { key: 'NO_APROBADO', label: 'Blacklist' },
]
const STATUS_LABEL = { APROBADO: 'Approved', POR_APROBAR: 'To approve', NO_APROBADO: 'Blacklist' }

export default function LendersPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('POR_APROBAR')
  const [busy, setBusy] = useState(null)

  // Se traen todos los dominios y se filtra en cliente por tab (counts consistentes).
  const load = useCallback(() => {
    setLoading(true)
    lendersApi.list()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const counts = useMemo(() => {
    const c = { APROBADO: 0, POR_APROBAR: 0, NO_APROBADO: 0 }
    for (const l of data.items) if (l.status in c) c[l.status] += 1
    return c
  }, [data.items])

  const visible = useMemo(
    () => data.items.filter((l) => l.status === tab),
    [data.items, tab]
  )

  const act = async (domain, action) => {
    setBusy(domain)
    setError('')
    try {
      if (action === 'approve') await lendersApi.approve(domain)
      else await lendersApi.reject(domain)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="p-8 space-y-6 max-w-6xl">
      <PageHeader
        title="Lenders"
        subtitle={`${data.total} domains. Approving reprocesses their emails through the pipeline.`}
        actions={
          <Tabs
            tabs={TABS.map((t) => ({ ...t, count: counts[t.key] }))}
            active={tab}
            onChange={setTab}
          />
        }
      />

      <StatStrip>
        <StatCard icon={Building2} tone="navy" label="Total" value={data.total} sub="Registered domains" />
        <StatCard icon={CheckCircle2} tone="ok" label="Approved" value={counts.APROBADO} sub="Reprocess their email" />
        <StatCard icon={Clock} tone="warn" label="To approve" value={counts.POR_APROBAR} sub="Pending review" />
        <StatCard icon={Ban} tone="stop" label="Blacklist" value={counts.NO_APROBADO} sub="Not approved" />
      </StatStrip>

      <ErrorBox message={error} />

      {loading ? (
        <Loading />
      ) : (
        <div className="card overflow-x-auto">
          <table className="ledger">
            <thead>
              <tr>
                <th>Domain</th>
                <th>Lender</th>
                <th>Status</th>
                <th className="text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((l) => (
                <tr key={l.id}>
                  <td><span className="token">{l.domain}</span></td>
                  <td className="text-ink">{l.lender_name}</td>
                  <td><Stamp tone={stampTone(l.status)}>{STATUS_LABEL[l.status] || l.status}</Stamp></td>
                  <td className="text-right whitespace-nowrap">
                    {busy === l.domain ? (
                      <Spinner />
                    ) : (
                      <div className="inline-flex gap-2">
                        {l.status !== 'APROBADO' && (
                          <button onClick={() => act(l.domain, 'approve')} className="btn btn-ok">
                            Approve
                          </button>
                        )}
                        {l.status !== 'NO_APROBADO' && (
                          <button onClick={() => act(l.domain, 'reject')} className="btn btn-danger">
                            Reject
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {visible.length === 0 && (
                <tr><td colSpan={4}><Empty>No lenders.</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
