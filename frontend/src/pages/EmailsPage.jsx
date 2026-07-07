import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, Mail, Sparkles, AlertTriangle, Paperclip, Trash2 } from 'lucide-react'
import { emailsApi, inboxApi, metaApi, reviewsApi, settingsApi, classificationsApi, sharepointApi } from '../lib/api'
import { fmtDate, fmtDateTime } from '../lib/dates'
import { PageHeader, Loading, Empty, ErrorBox, Field, DetailBlock, Stamp, Spinner, IconButton, StatCard, StatStrip, stageLabel } from '../components/ui'
import Tabs from '../components/Tabs'
import Drawer from '../components/Drawer'
import Modal from '../components/Modal'

// Estado unificado del correo -> etiqueta + tono de sello.
const ESTADO = {
  clasificada: { label: 'AI classified', tone: 'warn' },
  por_revisar: { label: 'To review', tone: 'warn' },
  descartado: { label: 'Discarded', tone: 'neutral' },
  contestado: { label: 'Answered', tone: 'ok' },
  aprobado: { label: 'Approved', tone: 'ok' },
  rechazado: { label: 'Rejected', tone: 'stop' },
  sin_procesar: { label: 'Unprocessed', tone: 'neutral' },
}

const INBOX_TABS = [
  { key: 'general', label: 'General' },
  { key: 'clasificados', label: 'Classified' },
  { key: 'por_revisar', label: 'To review' },
  { key: 'descartado', label: 'Discarded' },
  { key: 'contestado', label: 'Answered' },
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
    if (sel.length) parts.push(`\n[SharePoint attachments]: ${sel.map((f) => f.name).join(', ')}`)
    if (signature.trim()) parts.push(`\n--\n${signature.trim()}`)
    try {
      await reviewsApi.answer(review.id, parts.join('\n'))
      onSaved(); onClose()
    } catch (e) { setError(e.message) } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Reply (draft)">
      {email && (
        <div className="px-6 py-5 space-y-3">
          {/* Cabecera estilo correo */}
          <div className="card px-4 py-3 text-sm space-y-1 bg-surfacealt">
            <div className="flex gap-2"><span className="eyebrow w-16">To</span><span className="text-ink">{email.sender}</span></div>
            <div className="flex gap-2"><span className="eyebrow w-16">Subject</span><span className="text-ink">RE: {email.subject}</span></div>
          </div>
          <div>
            <label className="eyebrow">Message</label>
            <textarea rows={9} value={body} onChange={(e) => setBody(e.target.value)}
              placeholder="Write the reply… (suggested draft if available)"
              className="field w-full mt-1 resize-none font-sans" />
          </div>
          <div>
            <label className="eyebrow">Attachments from SharePoint</label>

            {/* Seleccionados */}
            {sel.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {sel.map((f) => (
                  <span key={f.id} className="chip bg-coralsoft text-coraldim">
                    <Paperclip size={11} /> <span className="max-w-[12rem] truncate">{f.name}</span>
                    <button onClick={() => removeFile(f.id)} className="ml-0.5 hover:text-stop" title="Remove">×</button>
                  </span>
                ))}
              </div>
            )}

            {/* Documentos identificados por el clasificador */}
            {ident.length > 0 && (
              <div className="mt-2">
                <p className="text-[11px] text-faint mb-1">Identified for this waiver:</p>
                <div className="flex flex-wrap gap-1.5">
                  {ident.map((m) => (
                    <button key={m.id} onClick={() => addFile(m)}
                      className="chip bg-navy/[0.05] text-navy hover:bg-coralsoft hover:text-coraldim transition-colors"
                      title={`Add ${m.name}`}>
                      + <span className="max-w-[12rem] truncate">{m.name}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Buscar cualquier archivo del SharePoint identificado */}
            <form onSubmit={searchSp} className="flex gap-2 mt-2">
              <input value={spq} onChange={(e) => setSpq(e.target.value)}
                placeholder="Search SharePoint…" className="field flex-1" />
              <button className="btn btn-ghost" type="submit">Search</button>
            </form>
            {spResults.length > 0 && (
              <ul className="mt-1.5 border border-line rounded-md divide-y divide-line max-h-40 overflow-y-auto">
                {spResults.map((f) => (
                  <li key={f.id}>
                    <button onClick={() => addFile(f)} className="w-full text-left px-3 py-1.5 text-sm hover:bg-surfacealt flex items-center justify-between gap-2">
                      <span className="truncate">{f.name}</span>
                      <span className="text-[11px] text-faint shrink-0">+ add</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <label className="eyebrow">Signature</label>
            <textarea rows={2} value={signature} onChange={(e) => setSignature(e.target.value)}
              className="field w-full mt-1 resize-none text-xs" />
          </div>
          <ErrorBox message={error} />
          <p className="text-[11px] text-faint">Saved as a draft and marks the email ANSWERED. Not sent: a human sends it from Outlook.</p>
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={onClose} className="btn btn-ghost" disabled={saving}>Cancel</button>
            <button onClick={save} className="btn btn-primary" disabled={saving}>
              {saving && <Spinner className="border-white/40 border-t-white" />} Save draft
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
    try { await reviewsApi.discard(review.id, 'Discarded from the inbox'); onChanged(); onClose() }
    finally { setBusy(false) }
  }

  return (
    <Drawer open={open} onClose={onClose} title={data?.subject || 'Email details'}>
      {loading ? <Loading /> : data && (
        <div className="space-y-4">
          {item?.review && (
            <div className="card px-4 py-3 bg-warn/[0.06] border-warn/25">
              <p className="eyebrow mb-1">Why it's under review</p>
              <p className="text-sm text-ink">{item.review.reason || stageLabel(item.review.stage)}</p>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <Field label="Sender" value={data.sender} mono />
            <Field label="Domain" value={data.sender_domain} mono />
            <Field label="Received" value={fmtDateTime(data.received_date)} mono />
            <div>
              <p className="eyebrow mb-1">Attachments</p>
              {data.has_attachments
                ? <span className="text-sm text-ink">{data.attachment_names.length}</span>
                : <span className="text-sm text-faint">none</span>}
            </div>
          </div>

          {data.to_recipients?.length > 0 && (
            <div>
              <p className="eyebrow mb-1.5">To</p>
              <div className="flex flex-wrap gap-1.5">
                {data.to_recipients.map((r) => <span key={r} className="token bg-ink/[0.03] px-2 py-0.5 rounded">{r}</span>)}
              </div>
            </div>
          )}

          {data.attachment_names?.length > 0 && (
            <div>
              <p className="eyebrow mb-1.5">Attachment names</p>
              <div className="flex flex-wrap gap-1.5">
                {data.attachment_names.map((a) => <Stamp key={a} tone="neutral">{a}</Stamp>)}
              </div>
            </div>
          )}

          {thread?.count > 1 && (
            <DetailBlock title={`Conversation thread — ${thread.count} iterations`}>
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

          <DetailBlock title="Email body">
            <pre className="text-xs leading-relaxed whitespace-pre-wrap text-ink/90 font-sans max-h-96 overflow-y-auto">
              {data.body_text?.slice(0, 6000) || 'No content.'}
            </pre>
          </DetailBlock>

          {isPending && (
            <div className="flex gap-2 pt-1">
              <button onClick={() => setComposing(true)} className="btn btn-primary flex-1">Reply</button>
              <button onClick={discard} disabled={busy} className="btn btn-danger flex-1 py-2">
                {busy && <Spinner className="border-stop/40 border-t-stop" />} Discard
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

  return (
    <div className="p-8 space-y-6 max-w-6xl">
      <PageHeader
        title="Production inbox"
        subtitle={`${data.total} emails${hasDateFilter || term ? ' (filtered)' : ' ingested'}.`}
        actions={
          <IconButton icon={RefreshCw} label={reloading ? 'Reloading…' : 'Reload emails'} onClick={reloadFromOutlook} />
        }
      />

      <ErrorBox message={error} />

      {/* Toolbar de filtros (separado de "Recargar correos") */}
      <div className="flex flex-wrap items-end gap-3">
        <form onSubmit={onSearch} className="flex gap-2">
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Subject or sender…" className="field w-64" />
          <button className="btn btn-ghost">Search</button>
        </form>
        <div className="flex items-end gap-2">
          <label className="flex flex-col gap-1 text-xs text-muted">
            <span className="eyebrow">From</span>
            <input type="date" value={fromDate} onChange={(e) => changeFrom(e.target.value)} max={toDate || undefined} className="field w-40" />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            <span className="eyebrow">To</span>
            <input type="date" value={toDate} onChange={(e) => changeTo(e.target.value)} min={fromDate || undefined} className="field w-40" />
          </label>
          {hasDateFilter && (
            <button onClick={clearDates} className="btn btn-ghost" title="Clear date filter">Clear</button>
          )}
        </div>
      </div>

      {/* Tarjetas y tabs salen del MISMO conteo del servidor: la suma de
          Classified + Discarded + To review (+ Answered) da General. */}
      <StatStrip>
        <StatCard icon={Mail} tone="navy" label="General" value={data.counts?.general ?? data.total} sub="all emails" />
        <StatCard icon={Sparkles} tone="coral" label="Classified" value={data.counts?.clasificados ?? 0} sub="lender + waiver identified" />
        <StatCard icon={AlertTriangle} tone="warn" label="To review" value={data.counts?.por_revisar ?? 0} sub="needs human review" />
        <StatCard icon={Trash2} tone="neutral" label="Discarded" value={data.counts?.descartado ?? 0} sub="auto-discarded by rules" />
      </StatStrip>

      <Tabs
        tabs={INBOX_TABS.map((t) => ({ ...t, count: data.counts?.[t.key] }))}
        active={tab}
        onChange={changeTab}
      />

      {loading ? (
        <Loading />
      ) : (
        <div className="card overflow-x-auto">
          <table className="ledger">
            <thead>
              <tr>
                <th>Subject</th>
                <th>Sender</th>
                <th>Domain</th>
                <th>Status</th>
                <th className="text-right">Received</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((e) => {
                const est = ESTADO[e.estado] || ESTADO.sin_procesar
                return (
                  <tr key={e.id} className="cursor-pointer" onClick={() => setSelected(e)}>
                    <td className="max-w-md text-ink">
                      <span className="flex items-center gap-1.5 min-w-0">
                        {e.has_attachments && (
                          <Paperclip size={13} className="shrink-0 text-muted" aria-label="Has attachments" />
                        )}
                        <span className="truncate" title={e.subject}>{e.subject || '(no subject)'}</span>
                      </span>
                    </td>
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
                <tr><td colSpan={5}><Empty>No emails in this status.</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {!loading && data.total > 0 && (
        <div className="flex items-center justify-between text-xs text-muted">
          <span className="font-mono tnum">{from}–{to} of {data.total}</span>
          <div className="flex gap-2">
            <button
              className="btn btn-ghost"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
            >
              Previous
            </button>
            <button
              className="btn btn-ghost"
              disabled={to >= data.total}
              onClick={() => setOffset(offset + PAGE)}
            >
              Next
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
