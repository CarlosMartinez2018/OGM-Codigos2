import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, Mail, Sparkles, AlertTriangle, Paperclip } from 'lucide-react'
import { emailsApi, inboxApi, metaApi, reviewsApi, settingsApi, classificationsApi, sharepointApi } from '../lib/api'
import { fmtDate, fmtDateTime } from '../lib/dates'
import { PageHeader, Loading, Empty, ErrorBox, Field, DetailBlock, Stamp, Spinner, IconButton, StatCard, StatStrip } from '../components/ui'
import Tabs from '../components/Tabs'
import Drawer from '../components/Drawer'
import Modal from '../components/Modal'

// Estado unificado del correo -> etiqueta + tono de sello.
const ESTADO = {
  clasificada: { label: 'Clasificada IA', tone: 'warn' },
  por_revisar: { label: 'Por revisar', tone: 'warn' },
  descartado: { label: 'Descartado', tone: 'neutral' },
  contestado: { label: 'Contestado', tone: 'ok' },
  aprobado: { label: 'Aprobado', tone: 'ok' },
  rechazado: { label: 'Rechazado', tone: 'stop' },
  sin_procesar: { label: 'Sin procesar', tone: 'neutral' },
}

const INBOX_TABS = [
  { key: 'general', label: 'General' },
  { key: 'por_revisar', label: 'Por revisar' },
  { key: 'descartado', label: 'Descartado' },
  { key: 'contestado', label: 'Contestado' },
]

// Composer de respuesta — estetica Outlook. SOLO diseño: guarda el borrador
// localmente y marca CONTESTADO. No envia ni conecta con Outlook.
function ComposerModal({ open, onClose, email, review, classificationId, onSaved }) {
  const [body, setBody] = useState('')
  const [sel, setSel] = useState([])          // adjuntos elegidos: {id, name}
  const [ident, setIdent] = useState([])      // documentos identificados (match del clasificador)
  const [spq, setSpq] = useState('')          // busqueda en SharePoint
  const [spResults, setSpResults] = useState([])
  const [signature, setSignature] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setError(''); setSel([]); setSpq(''); setSpResults([]); setIdent([])
    setBody(email?.suggested_response || '')
    settingsApi.getSignature().then((s) => setSignature(s.signature || '')).catch(() => setSignature(''))
    if (classificationId) {
      classificationsApi.documents(classificationId)
        .then((d) => setIdent((d.documents || []).flatMap((x) => x.found ? x.matches : []).filter((m) => m.id)))
        .catch(() => setIdent([]))
    }
  }, [open, email, classificationId])

  const addFile = (f) => setSel((s) => s.some((x) => x.id === f.id) ? s : [...s, { id: f.id, name: f.name }])
  const removeFile = (id) => setSel((s) => s.filter((x) => x.id !== id))

  const searchSp = async (e) => {
    e.preventDefault()
    if (!spq.trim()) { setSpResults([]); return }
    try { const r = await sharepointApi.list({ q: spq.trim(), limit: 8 }); setSpResults(r.items || []) }
    catch { setSpResults([]) }
  }

  const save = async () => {
    if (!review?.id) return
    setSaving(true); setError('')
    const parts = [body.trim()]
    if (sel.length) parts.push(`\n[Adjuntos SharePoint]: ${sel.map((f) => f.name).join(', ')}`)
    if (signature.trim()) parts.push(`\n--\n${signature.trim()}`)
    try {
      await reviewsApi.answer(review.id, parts.join('\n'))
      onSaved(); onClose()
    } catch (e) { setError(e.message) } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Responder (borrador)">
      {email && (
        <div className="px-6 py-5 space-y-3">
          {/* Cabecera estilo correo */}
          <div className="card px-4 py-3 text-sm space-y-1 bg-surfacealt">
            <div className="flex gap-2"><span className="eyebrow w-16">Para</span><span className="text-ink">{email.sender}</span></div>
            <div className="flex gap-2"><span className="eyebrow w-16">Asunto</span><span className="text-ink">RE: {email.subject}</span></div>
          </div>
          <div>
            <label className="eyebrow">Mensaje</label>
            <textarea rows={9} value={body} onChange={(e) => setBody(e.target.value)}
              placeholder="Escribe la respuesta… (borrador sugerido si existe)"
              className="field w-full mt-1 resize-none font-sans" />
          </div>
          <div>
            <label className="eyebrow">Adjuntos desde SharePoint</label>

            {/* Seleccionados */}
            {sel.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {sel.map((f) => (
                  <span key={f.id} className="chip bg-coralsoft text-coraldim">
                    <Paperclip size={11} /> <span className="max-w-[12rem] truncate">{f.name}</span>
                    <button onClick={() => removeFile(f.id)} className="ml-0.5 hover:text-stop" title="Quitar">×</button>
                  </span>
                ))}
              </div>
            )}

            {/* Documentos identificados por el clasificador */}
            {ident.length > 0 && (
              <div className="mt-2">
                <p className="text-[11px] text-faint mb-1">Identificados para este waiver:</p>
                <div className="flex flex-wrap gap-1.5">
                  {ident.map((m) => (
                    <button key={m.id} onClick={() => addFile(m)}
                      className="chip bg-navy/[0.05] text-navy hover:bg-coralsoft hover:text-coraldim transition-colors"
                      title={`Agregar ${m.name}`}>
                      + <span className="max-w-[12rem] truncate">{m.name}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Buscar cualquier archivo del SharePoint identificado */}
            <form onSubmit={searchSp} className="flex gap-2 mt-2">
              <input value={spq} onChange={(e) => setSpq(e.target.value)}
                placeholder="Buscar en SharePoint…" className="field flex-1" />
              <button className="btn btn-ghost" type="submit">Buscar</button>
            </form>
            {spResults.length > 0 && (
              <ul className="mt-1.5 border border-line rounded-md divide-y divide-line max-h-40 overflow-y-auto">
                {spResults.map((f) => (
                  <li key={f.id}>
                    <button onClick={() => addFile(f)} className="w-full text-left px-3 py-1.5 text-sm hover:bg-surfacealt flex items-center justify-between gap-2">
                      <span className="truncate">{f.name}</span>
                      <span className="text-[11px] text-faint shrink-0">+ agregar</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <label className="eyebrow">Firma</label>
            <textarea rows={2} value={signature} onChange={(e) => setSignature(e.target.value)}
              className="field w-full mt-1 resize-none text-xs" />
          </div>
          <ErrorBox message={error} />
          <p className="text-[11px] text-faint">Se guarda como borrador y marca el correo CONTESTADO. No se envía: el envío lo hace un humano desde Outlook.</p>
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={onClose} className="btn btn-ghost" disabled={saving}>Cancelar</button>
            <button onClick={save} className="btn btn-primary" disabled={saving}>
              {saving && <Spinner className="border-white/40 border-t-white" />} Guardar borrador
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function EmailDrawer({ item, open, onClose, onChanged }) {
  const id = item?.id
  const review = item?.review
  const isPending = review?.status === 'PENDIENTE'
  const [data, setData] = useState(null)
  const [thread, setThread] = useState(null)
  const [loading, setLoading] = useState(false)
  const [composing, setComposing] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open || !id) return
    setLoading(true); setThread(null)
    emailsApi.get(id).then(setData).catch(() => setData(null)).finally(() => setLoading(false))
    emailsApi.thread(id).then(setThread).catch(() => setThread(null))
  }, [open, id])

  const discard = async () => {
    if (!review?.id) return
    setBusy(true)
    try { await reviewsApi.discard(review.id, 'Descartado desde la bandeja'); onChanged(); onClose() }
    finally { setBusy(false) }
  }

  return (
    <Drawer open={open} onClose={onClose} title={data?.subject || 'Detalle del correo'}>
      {loading ? <Loading /> : data && (
        <div className="space-y-4">
          {item?.review && (
            <div className="card px-4 py-3 bg-warn/[0.06] border-warn/25">
              <p className="eyebrow mb-1">Por qué está en revisión</p>
              <p className="text-sm text-ink">{item.review.reason || item.review.stage}</p>
            </div>
          )}
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

          {thread?.count > 1 && (
            <DetailBlock title={`Hilo de conversación — ${thread.count} iteraciones`}>
              <ol className="relative border-l border-line ml-1 space-y-3">
                {thread.items.map((it) => (
                  <li key={it.id} className={`pl-4 relative ${it.is_current ? '' : 'opacity-80'}`}>
                    <span className={`absolute -left-[5px] top-1.5 w-2 h-2 rounded-full ${it.is_current ? 'bg-coral' : 'bg-line'}`} />
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-ink truncate">{it.sender}</span>
                      <span className="font-mono text-[11px] text-faint tnum shrink-0">{fmtDateTime(it.received_date)}</span>
                    </div>
                    <p className="text-[11px] text-muted truncate">{it.subject}</p>
                  </li>
                ))}
              </ol>
            </DetailBlock>
          )}

          <DetailBlock title="Cuerpo del correo">
            <pre className="text-xs leading-relaxed whitespace-pre-wrap text-ink/90 font-sans max-h-96 overflow-y-auto">
              {data.body_text?.slice(0, 6000) || 'Sin contenido.'}
            </pre>
          </DetailBlock>

          {isPending && (
            <div className="flex gap-2 pt-1">
              <button onClick={() => setComposing(true)} className="btn btn-primary flex-1">Contestar</button>
              <button onClick={discard} disabled={busy} className="btn btn-danger flex-1 py-2">
                {busy && <Spinner className="border-stop/40 border-t-stop" />} Descartar
              </button>
            </div>
          )}

          <p className="token text-faint break-all">{data.message_id}</p>
        </div>
      )}
      <ComposerModal
        open={composing}
        onClose={() => setComposing(false)}
        email={data}
        review={review}
        classificationId={item?.classification?.id}
        onSaved={() => { onChanged(); onClose() }}
      />
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
  const [tab, setTab] = useState('general')
  const [selected, setSelected] = useState(null)
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [stats, setStats] = useState(null)
  const [reloading, setReloading] = useState(false)

  const refreshStats = useCallback(() => { metaApi.stats().then(setStats).catch(() => {}) }, [])
  useEffect(() => { refreshStats() }, [refreshStats])

  const load = useCallback((q, off, tb, df, dt) => {
    setLoading(true)
    inboxApi.list({ limit: PAGE, offset: off, search: q, tab: tb, from_date: df, to_date: dt })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(term, offset, tab, fromDate, toDate) }, [load, term, offset, tab, fromDate, toDate])

  const reloadFromOutlook = async () => {
    setReloading(true); setError('')
    try {
      await emailsApi.reload(false)
      setOffset(0)
      load(term, 0, tab, fromDate, toDate)
      refreshStats()
    } catch (e) { setError(e.message) } finally { setReloading(false) }
  }

  const onSearch = (e) => { e.preventDefault(); setOffset(0); setTerm(search) }
  const changeTab = (k) => { setOffset(0); setTab(k) }
  const changeFrom = (v) => { setOffset(0); setFromDate(v) }
  const changeTo = (v) => { setOffset(0); setToDate(v) }
  const clearDates = () => { setOffset(0); setFromDate(''); setToDate('') }
  const hasDateFilter = fromDate || toDate

  const from = data.total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE, data.total)

  const pendingReviews = stats?.pending_reviews_by_stage
    ? Object.values(stats.pending_reviews_by_stage).reduce((a, n) => a + n, 0)
    : 0
  const withAttachments = data.items.filter((e) => e.has_attachments).length

  return (
    <div className="p-8 space-y-6 max-w-6xl">
      <PageHeader
        title="Bandeja de producción"
        subtitle={`${data.total} correos${hasDateFilter || term ? ' (filtrados)' : ' ingestados'}.`}
        actions={
          <IconButton icon={RefreshCw} label={reloading ? 'Recargando…' : 'Recargar correos'} onClick={reloadFromOutlook} />
        }
      />

      <ErrorBox message={error} />

      {/* Toolbar de filtros (separado de "Recargar correos") */}
      <div className="flex flex-wrap items-end gap-3">
        <form onSubmit={onSearch} className="flex gap-2">
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Asunto o remitente…" className="field w-64" />
          <button className="btn btn-ghost">Buscar</button>
        </form>
        <div className="flex items-end gap-2">
          <label className="flex flex-col gap-1 text-xs text-muted">
            <span className="eyebrow">Desde</span>
            <input type="date" value={fromDate} onChange={(e) => changeFrom(e.target.value)} max={toDate || undefined} className="field w-40" />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            <span className="eyebrow">Hasta</span>
            <input type="date" value={toDate} onChange={(e) => changeTo(e.target.value)} min={fromDate || undefined} className="field w-40" />
          </label>
          {hasDateFilter && (
            <button onClick={clearDates} className="btn btn-ghost" title="Quitar filtro de fecha">Limpiar</button>
          )}
        </div>
      </div>

      <StatStrip>
        <StatCard icon={Mail} tone="navy" label="Total correos" value={stats?.total_emails ?? data.total} sub="ingestados en producción" />
        <StatCard icon={Sparkles} tone="coral" label="Clasificados" value={stats?.total_classified ?? 0} sub="por reglas del pre-filtrado" />
        <StatCard icon={AlertTriangle} tone="warn" label="Por revisar" value={pendingReviews} sub="en cola de revisión" />
        <StatCard icon={Paperclip} tone="ok" label="Con adjuntos" value={withAttachments} sub="en esta página" />
      </StatStrip>

      <Tabs
        tabs={INBOX_TABS.map((t) => ({ ...t, count: data.counts?.[t.key] }))}
        active={tab}
        onChange={changeTab}
      />

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
                <th>Estado</th>
                <th className="text-right">Recibido</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((e) => {
                const est = ESTADO[e.estado] || ESTADO.sin_procesar
                return (
                  <tr key={e.id} className="cursor-pointer" onClick={() => setSelected(e)}>
                    <td className="max-w-md truncate text-ink" title={e.subject}>{e.subject || '(sin asunto)'}</td>
                    <td className="text-muted truncate max-w-[13rem]" title={e.sender}>{e.sender}</td>
                    <td><span className="token">{e.sender_domain}</span></td>
                    <td>
                      <Stamp tone={est.tone}>{est.label}</Stamp>
                      {e.classification?.lender && e.classification.lender !== 'UNKNOWN' && (
                        <span className="ml-2 text-[11px] text-faint">{e.classification.lender}</span>
                      )}
                    </td>
                    <td className="text-right font-mono text-xs text-muted whitespace-nowrap tnum">
                      {fmtDate(e.received_date)}
                    </td>
                  </tr>
                )
              })}
              {data.items.length === 0 && (
                <tr><td colSpan={5}><Empty>Sin correos en este estado.</Empty></td></tr>
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

      <EmailDrawer
        item={selected}
        open={selected !== null}
        onClose={() => setSelected(null)}
        onChanged={() => { load(term, offset, tab); refreshStats() }}
      />
    </div>
  )
}
