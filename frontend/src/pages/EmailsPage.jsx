import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, Mail, Sparkles, AlertTriangle, Paperclip } from 'lucide-react'
import { emailsApi, metaApi } from '../lib/api'
import { fmtDate, fmtDateTime } from '../lib/dates'
import { PageHeader, Loading, Empty, ErrorBox, Field, DetailBlock, Stamp, IconButton, StatCard, StatStrip } from '../components/ui'
import Drawer from '../components/Drawer'

function EmailDrawer({ id, open, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !id) return
    setLoading(true)
    emailsApi.get(id).then(setData).catch(() => setData(null)).finally(() => setLoading(false))
  }, [open, id])

  return (
    <Drawer open={open} onClose={onClose} title={data?.subject || 'Detalle del correo'}>
      {loading ? <Loading /> : data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Remitente" value={data.sender} mono />
            <Field label="Dominio" value={data.sender_domain} mono />
            <Field label="Recibido" value={fmtDateTime(data.received_date)} mono />
            <div>
              <p className="eyebrow mb-1">Adjuntos</p>
              {data.has_attachments
                ? <span className="text-sm text-ink">{data.attachment_names.length}</span>
                : <span className="text-sm text-faint">ninguno</span>}
            </div>
          </div>

          {data.to_recipients?.length > 0 && (
            <div>
              <p className="eyebrow mb-1.5">Para</p>
              <div className="flex flex-wrap gap-1.5">
                {data.to_recipients.map((r) => <span key={r} className="token bg-ink/[0.03] px-2 py-0.5 rounded">{r}</span>)}
              </div>
            </div>
          )}

          {data.attachment_names?.length > 0 && (
            <div>
              <p className="eyebrow mb-1.5">Nombres de adjuntos</p>
              <div className="flex flex-wrap gap-1.5">
                {data.attachment_names.map((a) => <Stamp key={a} tone="neutral">{a}</Stamp>)}
              </div>
            </div>
          )}

          <DetailBlock title="Cuerpo del correo">
            <pre className="text-xs leading-relaxed whitespace-pre-wrap text-ink/90 font-sans max-h-96 overflow-y-auto">
              {data.body_text?.slice(0, 6000) || 'Sin contenido.'}
            </pre>
          </DetailBlock>

          <p className="token text-faint break-all">{data.message_id}</p>
        </div>
      )}
    </Drawer>
  )
}

const PAGE = 50

export default function EmailsPage() {
  const [data, setData] = useState({ total: 0, items: [], offset: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [term, setTerm] = useState('')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState(null)
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [stats, setStats] = useState(null)
  const [reloading, setReloading] = useState(false)

  const refreshStats = useCallback(() => { metaApi.stats().then(setStats).catch(() => {}) }, [])
  useEffect(() => { refreshStats() }, [refreshStats])

  const reloadFromOutlook = async () => {
    setReloading(true); setError('')
    try {
      await emailsApi.reload(false)
      load(term, 0)
      refreshStats()
    } catch (e) { setError(e.message) } finally { setReloading(false) }
  }

  const load = useCallback((q, off) => {
    setLoading(true)
    emailsApi.list({ limit: PAGE, offset: off, search: q })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(term, offset) }, [load, term, offset])

  const onSearch = (e) => { e.preventDefault(); setOffset(0); setTerm(search) }

  const from = data.total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE, data.total)

  const pendingReviews = stats?.pending_reviews_by_stage
    ? Object.values(stats.pending_reviews_by_stage).reduce((a, n) => a + n, 0)
    : 0
  const withAttachments = data.items.filter((e) => e.has_attachments).length

  const visible = data.items.filter((e) => {
    if (!e.received_date) return true
    const d = e.received_date.slice(0, 10) // YYYY-MM-DD del ISO
    if (fromDate && d < fromDate) return false
    if (toDate && d > toDate) return false
    return true
  })

  return (
    <div className="p-8 space-y-6 max-w-6xl">
      <PageHeader
        title="Bandeja de producción"
        subtitle={`${data.total} correos ingestados.`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <form onSubmit={onSearch} className="flex gap-2">
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Asunto o remitente…" className="field w-64" />
              <button className="btn btn-ghost">Buscar</button>
            </form>
            <label className="flex items-center gap-1.5 text-xs text-muted">
              <span className="eyebrow">Desde</span>
              <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} max={toDate || undefined} className="field w-40" />
            </label>
            <label className="flex items-center gap-1.5 text-xs text-muted">
              <span className="eyebrow">Hasta</span>
              <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} min={fromDate || undefined} className="field w-40" />
            </label>
            <IconButton icon={RefreshCw} label={reloading ? 'Recargando…' : 'Recargar'} onClick={reloadFromOutlook} />
          </div>
        }
      />

      <ErrorBox message={error} />

      <StatStrip>
        <StatCard icon={Mail} tone="navy" label="Total correos" value={stats?.total_emails ?? data.total} sub="ingestados en producción" />
        <StatCard icon={Sparkles} tone="coral" label="Clasificados" value={stats?.total_classified ?? 0} sub="por reglas del pre-filtrado" />
        <StatCard icon={AlertTriangle} tone="warn" label="Por revisar" value={pendingReviews} sub="en cola de revisión" />
        <StatCard icon={Paperclip} tone="ok" label="Con adjuntos" value={withAttachments} sub="en esta página" />
      </StatStrip>

      {loading ? (
        <Loading />
      ) : (
        <div className="card overflow-hidden">
          <table className="ledger">
            <thead>
              <tr>
                <th>Asunto</th>
                <th>Remitente</th>
                <th>Dominio</th>
                <th className="text-right">Recibido</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((e) => (
                <tr key={e.id} className="cursor-pointer" onClick={() => setSelected(e.id)}>
                  <td className="max-w-md truncate text-ink" title={e.subject}>{e.subject || '(sin asunto)'}</td>
                  <td className="text-muted truncate max-w-[15rem]" title={e.sender}>{e.sender}</td>
                  <td><span className="token">{e.sender_domain}</span></td>
                  <td className="text-right font-mono text-xs text-muted whitespace-nowrap tnum">
                    {fmtDate(e.received_date)}
                  </td>
                </tr>
              ))}
              {visible.length === 0 && (
                <tr><td colSpan={4}><Empty>Sin correos.</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {!loading && data.total > 0 && (
        <div className="flex items-center justify-between text-xs text-muted">
          <span className="font-mono tnum">{from}–{to} de {data.total}</span>
          <div className="flex gap-2">
            <button
              className="btn btn-ghost"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
            >
              Anterior
            </button>
            <button
              className="btn btn-ghost"
              disabled={to >= data.total}
              onClick={() => setOffset(offset + PAGE)}
            >
              Siguiente
            </button>
          </div>
        </div>
      )}

      <EmailDrawer id={selected} open={selected !== null} onClose={() => setSelected(null)} />
    </div>
  )
}
