import { useState, useEffect, useCallback } from 'react'
import { Eye, FileText } from 'lucide-react'
import { classificationsApi, metaApi, sharepointApi } from '../lib/api'
import {
  Stamp, stampTone, PageHeader, Spinner, Loading, Empty, ErrorBox, Field, DetailBlock, IconButton,
} from '../components/ui'
import Tabs from '../components/Tabs'
import Drawer from '../components/Drawer'
import Modal from '../components/Modal'

const STATUS_TONE = { classified: 'warn', reviewed: 'ok', corrected: 'neutral', rejected: 'stop' }

// Tabs-container: mapea cada tab al campo `status` real del backend.
// 'classified' = recién clasificado por la IA, pendiente de revisión humana.
const TABS = [
  { key: 'PENDING', label: 'To review', status: 'classified' },
  { key: 'APPROVED', label: 'Approved', status: 'reviewed' },
  { key: 'CORRECTED', label: 'Corrected', status: 'corrected' },
  { key: 'REJECTED', label: 'Rejected', status: 'rejected' },
]

// ── Modal de corrección ─────────────────────────────────────────────
function CorrectModal({ open, onClose, item, onSaved }) {
  const [catalog, setCatalog] = useState([])
  const [lender, setLender] = useState('')
  const [waiver, setWaiver] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    metaApi.lendersAndWaivers().then((d) => setCatalog(d.lenders || [])).catch(() => setCatalog([]))
    setLender(item?.lender || '')
    setWaiver(item?.waiver_type || '')
    setNotes('')
    setError('')
  }, [open, item])

  const waivers = catalog.find((l) => l.name === lender)?.waivers || []

  const submit = async (e) => {
    e.preventDefault()
    if (!lender || !waiver) { setError('Lender and waiver are required.'); return }
    setSaving(true); setError('')
    try {
      await classificationsApi.correct(item.id, {
        corrected_lender: lender, corrected_waiver_type: waiver, reviewed_by: 'operator', notes: notes || undefined,
      })
      onSaved()
      onClose()
    } catch (err) { setError(err.message) } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Correct classification">
      {item && (
        <form onSubmit={submit} className="px-6 py-5 space-y-4">
          <div className="card px-4 py-3 text-sm">
            <p className="eyebrow mb-1.5">Current classification</p>
            <p className="text-ink">{item.lender} · {item.waiver_type}</p>
          </div>
          <div>
            <label className="eyebrow">Correct lender</label>
            <select value={lender} onChange={(e) => { setLender(e.target.value); setWaiver('') }} className="field w-full mt-1">
              <option value="">Select…</option>
              {catalog.map((l) => <option key={l.name} value={l.name}>{l.name}</option>)}
            </select>
          </div>
          <div>
            <label className="eyebrow">Correct waiver</label>
            <select value={waiver} onChange={(e) => setWaiver(e.target.value)} disabled={!lender} className="field w-full mt-1 disabled:opacity-50">
              <option value="">Select…</option>
              {waivers.map((w) => <option key={w} value={w}>{w}</option>)}
            </select>
          </div>
          <div>
            <label className="eyebrow">Notes (optional)</label>
            <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Reason for the correction…" className="field w-full mt-1 resize-none" />
          </div>
          <ErrorBox message={error} />
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn btn-ghost" disabled={saving}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving && <Spinner className="border-white/40 border-t-white" />} Save correction
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}

// ── Modal de rechazo (comentario → contexto IA) ─────────────────────
function RejectModal({ open, onClose, item, onSaved }) {
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { if (open) { setComment(''); setError('') } }, [open])

  const submit = async (e) => {
    e.preventDefault()
    if (!comment.trim()) { setError('The comment is required: it feeds the AI context.'); return }
    setSaving(true); setError('')
    try { await classificationsApi.reject(item.id, comment.trim()); onSaved(); onClose() }
    catch (err) { setError(err.message) } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Reject classification">
      {item && (
        <form onSubmit={submit} className="px-6 py-5 space-y-4">
          <div className="card px-4 py-3 text-sm">
            <p className="eyebrow mb-1.5">Rejected classification</p>
            <p className="text-ink">{item.lender} · {item.waiver_type}</p>
          </div>
          <div>
            <label className="eyebrow">Reason for rejection</label>
            <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)}
              placeholder="Why is it wrong? This text feeds the context so the AI improves…"
              className="field w-full mt-1 resize-none" />
          </div>
          <ErrorBox message={error} />
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn btn-ghost" disabled={saving}>Cancel</button>
            <button type="submit" className="btn btn-danger px-3.5 py-2" disabled={saving}>
              {saving && <Spinner className="border-stop/40 border-t-stop" />} Reject
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}

// ── Visor de PDF inline (proxy de SharePoint) ───────────────────────
function PdfModal({ file, onClose }) {
  return (
    <Modal open={!!file} onClose={onClose} title={file?.name || 'Document'}>
      {file && (
        <div className="px-4 py-4">
          <iframe
            title={file.name}
            src={sharepointApi.contentUrl(file.id)}
            className="w-full h-[70vh] rounded-md border border-line bg-paper"
          />
          <div className="flex justify-end mt-3">
            <a href={file.web_url || sharepointApi.contentUrl(file.id)} target="_blank" rel="noreferrer" className="btn btn-ghost">
              Open in SharePoint
            </a>
          </div>
        </div>
      )}
    </Modal>
  )
}

// ── Drawer de detalle (por qué + acciones) ──────────────────────────
function ClassificationDrawer({ id, open, onClose, onChanged, onCorrect, onReject }) {
  const [pdf, setPdf] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [approving, setApproving] = useState(false)
  const [docs, setDocs] = useState(null)

  const load = useCallback(() => {
    if (!id) return
    setLoading(true)
    setDocs(null)
    classificationsApi.get(id).then(setData).catch(() => setData(null)).finally(() => setLoading(false))
    classificationsApi.documents(id).then(setDocs).catch(() => setDocs(null))
  }, [id])

  useEffect(() => { if (open) load() }, [open, load])

  const approve = async () => {
    setApproving(true)
    try { await classificationsApi.approve(id); onChanged(); load() } finally { setApproving(false) }
  }

  const v = data?.validation_details || {}
  const le = v.lender_evidence || {}
  const we = v.waiver_evidence || {}
  const m = data?.matrix

  return (
    <Drawer open={open} onClose={onClose} title={data?.lender ? `${data.lender} · ${data.waiver_type}` : 'Classification'}>
      {loading || !data ? <Loading /> : (
        <div className="space-y-4">
          {/* Resumen */}
          <div className="flex flex-wrap items-center gap-2">
            <Stamp tone={stampTone(data.confidence_level)}>
              {data.confidence_level} · {Math.round((data.confidence_score ?? 0) * 100)}%
            </Stamp>
            <Stamp tone={STATUS_TONE[data.status] || 'neutral'}>{data.status}</Stamp>
            <span className="font-mono text-[11px] text-faint uppercase tracking-wider">{data.communication_category}</span>
            {data.escalate_for_review && <Stamp tone="stop">escalate</Stamp>}
          </div>

          {/* Por qué se clasificó así */}
          <DetailBlock title="Why — rule evidence">
            <div className="space-y-2.5 text-sm">
              <Field label="Trigger" value={data.trigger_description} />
              {le.matched_by && (
                <Field label="Lender identified by" value={`${le.matched_by}${le.matched_domain ? ` (${le.matched_domain})` : ''}`} mono />
              )}
              {we.matches?.length > 0 && (
                <div>
                  <p className="eyebrow mb-1">Waiver matches (score {we.score})</p>
                  <ul className="list-disc list-inside text-xs text-muted space-y-0.5">
                    {we.matches.map((mm, i) => <li key={i}>{mm}</li>)}
                  </ul>
                </div>
              )}
              {v.prompt_injection_detected && <Stamp tone="stop">prompt injection detected</Stamp>}
            </div>
          </DetailBlock>

          {/* Enriquecimiento desde la matriz */}
          {m && (
            <DetailBlock title="Requirements (lender-waiver matrix)">
              <div className="space-y-2.5">
                <Field label="Evidence (Ops)" value={m.evidence_required_ops} />
                <Field label="Evidence (Insurance)" value={m.evidence_required_insurance} />
                <Field label="Waiver pack" value={m.waiver_pack} />
                <Field label="Actions to automate" value={m.actions_to_automate} />
                {m.documents?.length > 0 && (
                  <div>
                    <p className="eyebrow mb-1.5">Expected documents</p>
                    <div className="flex flex-wrap gap-1.5">
                      {m.documents.map((d) => <Stamp key={d} tone="neutral">{d}</Stamp>)}
                    </div>
                  </div>
                )}
              </div>
            </DetailBlock>
          )}

          {/* Documentos esperados vs SharePoint (match exacto) */}
          {docs && (
            <DetailBlock title={`Documents in SharePoint — ${docs.found}/${docs.total} found`}>
              {docs.documents.length === 0 ? (
                <p className="text-sm text-muted">No expected documents for this waiver.</p>
              ) : (
                <ul className="space-y-1.5">
                  {docs.documents.map((d) => (
                    <li key={d.document} className="flex items-center justify-between gap-3 text-sm">
                      <span className="text-ink min-w-0 truncate" title={d.document}>{d.document}</span>
                      {d.found ? (
                        <div className="flex items-center gap-2 shrink-0">
                          {d.matches[0]?.id && (
                            <button
                              onClick={() => setPdf(d.matches[0])}
                              className="inline-flex items-center gap-1 text-navy hover:text-coral transition-colors"
                              title={`View ${d.matches[0].name}`}
                            >
                              <FileText size={14} /> <span className="text-xs">View</span>
                            </button>
                          )}
                          <Stamp tone="ok">found</Stamp>
                        </div>
                      ) : (
                        <Stamp tone="stop">not found</Stamp>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </DetailBlock>
          )}

          {data.secondary_issues?.length > 0 && (
            <Field label="Secondary issues" value={data.secondary_issues.join(' · ')} />
          )}

          {data.suggested_attachments?.length > 0 && (
            <DetailBlock title="Suggested attachments">
              <div className="space-y-1">
                {data.suggested_attachments.map((p) => <p key={p} className="token break-all">{p}</p>)}
              </div>
            </DetailBlock>
          )}

          {data.suggested_response && (
            <DetailBlock title="Suggested reply">
              <pre className="text-xs whitespace-pre-wrap font-sans text-ink/90 leading-relaxed">{data.suggested_response}</pre>
            </DetailBlock>
          )}

          {data.raw_llm_response && (
            <DetailBlock title="Model reasoning (LLM)">
              <pre className="text-xs whitespace-pre-wrap font-sans text-ink/80 leading-relaxed">{data.raw_llm_response}</pre>
            </DetailBlock>
          )}

          {/* Correo original */}
          {data.email && (
            <DetailBlock title="Original email">
              <div className="space-y-2">
                <Field label="From" value={data.email.sender} mono />
                <Field label="Subject" value={data.email.subject} />
                <pre className="text-xs whitespace-pre-wrap font-sans text-ink/80 leading-relaxed max-h-60 overflow-y-auto mt-1">
                  {data.email.body_text?.slice(0, 4000)}
                </pre>
              </div>
            </DetailBlock>
          )}

          {/* Acciones */}
          {data.status === 'classified' ? (
            <div className="flex gap-2 pt-1">
              <button onClick={approve} disabled={approving} className="btn btn-ok flex-1 py-2 text-sm">
                {approving && <Spinner className="border-white/40 border-t-white" />} Approve
              </button>
              <button onClick={() => onCorrect(data)} className="btn btn-ghost flex-1">Correct</button>
              <button onClick={() => onReject(data)} className="btn btn-danger flex-1 py-2">Reject</button>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-muted card px-4 py-3">
              <Stamp tone={STATUS_TONE[data.status] || 'neutral'}>{data.status}</Stamp>
              {data.reviewed_by && <span>por {data.reviewed_by}</span>}
              {data.correction_notes && <span className="text-faint">· {data.correction_notes}</span>}
            </div>
          )}
        </div>
      )}
      <PdfModal file={pdf} onClose={() => setPdf(null)} />
    </Drawer>
  )
}

// Tarjeta de resumen por banda de confianza (vistazo inmediato + umbral).
function ConfCard({ label, value, threshold, accent, dim }) {
  return (
    <div className={`card px-4 py-3 border-l-[3px] ${accent}`}>
      <div className="flex items-baseline justify-between gap-2">
        <p className="eyebrow">{label}</p>
        <span className="display text-2xl tnum" style={{ color: dim }}>{value ?? 0}</span>
      </div>
      <p className="font-mono text-[11px] text-faint mt-1">{threshold}</p>
    </div>
  )
}

function ConfidenceSummary({ stats }) {
  const c = stats?.classifications_by_confidence || {}
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <ConfCard label="Total" value={stats?.total_classified} threshold="classified by rules" accent="border-navy" dim="#1C2445" />
      <ConfCard label="High" value={c.high} threshold="≥ 85%" accent="border-ok" dim="#0F7B4A" />
      <ConfCard label="Medium" value={c.medium} threshold="60 – 85%" accent="border-warn" dim="#B45309" />
      <ConfCard label="Low" value={c.low} threshold="< 60% · review" accent="border-stop" dim="#B42318" />
    </div>
  )
}

// ── Página ──────────────────────────────────────────────────────────
export default function ClassificationsPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [level, setLevel] = useState('')
  const [tab, setTab] = useState('PENDING')
  const [selected, setSelected] = useState(null)
  const [correcting, setCorrecting] = useState(null)
  const [rejecting, setRejecting] = useState(null)

  const load = useCallback((lvl) => {
    setLoading(true)
    classificationsApi.list({ limit: 100, confidence_level: lvl })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
    metaApi.stats().then(setStats).catch(() => {})
  }, [])

  useEffect(() => { load(level) }, [load, level])

  // Conteos por tab (cliente) sobre la página cargada.
  const counts = TABS.reduce((acc, t) => {
    acc[t.key] = data.items.filter((c) => c.status === t.status).length
    return acc
  }, {})

  const visible = data.items.filter(
    (c) => c.status === TABS.find((t) => t.key === tab)?.status
  )

  return (
    <div className="p-8 space-y-6 max-w-6xl">
      <PageHeader
        title="Classifications"
        subtitle={`${data.total} results. Open one to see the why, approve or correct.`}
        actions={
          <div className="flex gap-2">
            <select value={level} onChange={(e) => setLevel(e.target.value)} className="field">
              <option value="">All confidence</option>
              <option value="high">High (&gt; 85%)</option>
              <option value="medium">Medium (60-85%)</option>
              <option value="low">Low (&lt; 60%)</option>
            </select>
          </div>
        }
      />

      <ConfidenceSummary stats={stats} />

      <Tabs
        tabs={TABS.map((t) => ({ key: t.key, label: t.label, count: counts[t.key] ?? 0 }))}
        active={tab}
        onChange={setTab}
      />

      <ErrorBox message={error} />

      {loading ? (
        <Loading />
      ) : visible.length === 0 ? (
        <Empty>
          {tab === 'REJECTED'
            ? 'No rejected classifications.'
            : 'No classifications in this status.'}
        </Empty>
      ) : (
        <div className="space-y-3">
          {visible.map((c) => (
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
                    {c.escalate_for_review && <Stamp tone="stop">escalate</Stamp>}
                    {c.status !== 'classified' && <Stamp tone={STATUS_TONE[c.status] || 'neutral'}>{c.status}</Stamp>}
                  </div>
                  {c.trigger_description && <p className="text-xs text-muted mt-1.5 truncate max-w-xl">{c.trigger_description}</p>}
                </div>
                <div className="flex items-start gap-4 shrink-0">
                  <div className="text-right space-y-1.5">
                    <Stamp tone={stampTone(c.confidence_level)}>
                      {c.confidence_level} · {Math.round((c.confidence_score ?? 0) * 100)}%
                    </Stamp>
                    <p className="font-mono text-[11px] text-faint uppercase tracking-wider">{c.communication_category}</p>
                  </div>
                  <IconButton icon={Eye} label="View" onClick={() => setSelected(c.id)} />
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      <ClassificationDrawer
        id={selected}
        open={selected !== null}
        onClose={() => setSelected(null)}
        onChanged={() => load(level)}
        onCorrect={(item) => setCorrecting(item)}
        onReject={(item) => setRejecting(item)}
      />
      <CorrectModal
        open={correcting !== null}
        item={correcting}
        onClose={() => setCorrecting(null)}
        onSaved={() => { load(level); setSelected(null) }}
      />
      <RejectModal
        open={rejecting !== null}
        item={rejecting}
        onClose={() => setRejecting(null)}
        onSaved={() => { load(level); setSelected(null) }}
      />
    </div>
  )
}
