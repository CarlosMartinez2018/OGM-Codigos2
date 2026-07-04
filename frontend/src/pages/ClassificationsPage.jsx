import { useState, useEffect, useCallback } from 'react'
import { Eye } from 'lucide-react'
import { classificationsApi, metaApi } from '../lib/api'
import {
  Stamp, stampTone, PageHeader, Spinner, Loading, Empty, ErrorBox, Field, DetailBlock, IconButton,
} from '../components/ui'
import Tabs from '../components/Tabs'
import Drawer from '../components/Drawer'
import Modal from '../components/Modal'

const STATUS_TONE = { classified: 'warn', reviewed: 'ok', corrected: 'neutral' }

// Tabs-container: mapea cada tab al campo `status` real del backend.
// 'classified' = recién clasificado por la IA, pendiente de revisión humana.
// REJECTED aún no existe en backend (Fase 2) → queda vacío con Empty.
const TABS = [
  { key: 'PENDING', label: 'Por revisar', status: 'classified' },
  { key: 'APPROVED', label: 'Aprobado', status: 'reviewed' },
  { key: 'CORRECTED', label: 'Corregido', status: 'corrected' },
  { key: 'REJECTED', label: 'Rechazado', status: '__rejected__' },
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
    if (!lender || !waiver) { setError('Lender y waiver son obligatorios.'); return }
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
    <Modal open={open} onClose={onClose} title="Corregir clasificación">
      {item && (
        <form onSubmit={submit} className="px-6 py-5 space-y-4">
          <div className="card px-4 py-3 text-sm">
            <p className="eyebrow mb-1.5">Clasificación actual</p>
            <p className="text-ink">{item.lender} · {item.waiver_type}</p>
          </div>
          <div>
            <label className="eyebrow">Lender correcto</label>
            <select value={lender} onChange={(e) => { setLender(e.target.value); setWaiver('') }} className="field w-full mt-1">
              <option value="">Seleccionar…</option>
              {catalog.map((l) => <option key={l.name} value={l.name}>{l.name}</option>)}
            </select>
          </div>
          <div>
            <label className="eyebrow">Waiver correcto</label>
            <select value={waiver} onChange={(e) => setWaiver(e.target.value)} disabled={!lender} className="field w-full mt-1 disabled:opacity-50">
              <option value="">Seleccionar…</option>
              {waivers.map((w) => <option key={w} value={w}>{w}</option>)}
            </select>
          </div>
          <div>
            <label className="eyebrow">Notas (opcional)</label>
            <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Razón de la corrección…" className="field w-full mt-1 resize-none" />
          </div>
          <ErrorBox message={error} />
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn btn-ghost" disabled={saving}>Cancelar</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving && <Spinner className="border-white/40 border-t-white" />} Guardar corrección
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}

// ── Drawer de detalle (por qué + acciones) ──────────────────────────
function ClassificationDrawer({ id, open, onClose, onChanged, onCorrect }) {
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
    <Drawer open={open} onClose={onClose} title={data?.lender ? `${data.lender} · ${data.waiver_type}` : 'Clasificación'}>
      {loading || !data ? <Loading /> : (
        <div className="space-y-4">
          {/* Resumen */}
          <div className="flex flex-wrap items-center gap-2">
            <Stamp tone={stampTone(data.confidence_level)}>
              {data.confidence_level} · {Math.round((data.confidence_score ?? 0) * 100)}%
            </Stamp>
            <Stamp tone={STATUS_TONE[data.status] || 'neutral'}>{data.status}</Stamp>
            <span className="font-mono text-[11px] text-faint uppercase tracking-wider">{data.communication_category}</span>
            {data.escalate_for_review && <Stamp tone="stop">escalar</Stamp>}
          </div>

          {/* Por qué se clasificó así */}
          <DetailBlock title="Por qué — evidencia de reglas">
            <div className="space-y-2.5 text-sm">
              <Field label="Trigger" value={data.trigger_description} />
              {le.matched_by && (
                <Field label="Lender identificado por" value={`${le.matched_by}${le.matched_domain ? ` (${le.matched_domain})` : ''}`} mono />
              )}
              {we.matches?.length > 0 && (
                <div>
                  <p className="eyebrow mb-1">Coincidencias de waiver (score {we.score})</p>
                  <ul className="list-disc list-inside text-xs text-muted space-y-0.5">
                    {we.matches.map((mm, i) => <li key={i}>{mm}</li>)}
                  </ul>
                </div>
              )}
              {v.prompt_injection_detected && <Stamp tone="stop">inyección de prompt detectada</Stamp>}
            </div>
          </DetailBlock>

          {/* Enriquecimiento desde la matriz */}
          {m && (
            <DetailBlock title="Requisitos (matriz lender-waiver)">
              <div className="space-y-2.5">
                <Field label="Evidencia (Ops)" value={m.evidence_required_ops} />
                <Field label="Evidencia (Seguros)" value={m.evidence_required_insurance} />
                <Field label="Waiver pack" value={m.waiver_pack} />
                <Field label="Acciones a automatizar" value={m.actions_to_automate} />
                {m.documents?.length > 0 && (
                  <div>
                    <p className="eyebrow mb-1.5">Documentos esperados</p>
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
            <DetailBlock title={`Documentos en SharePoint — ${docs.found}/${docs.total} encontrados`}>
              {docs.documents.length === 0 ? (
                <p className="text-sm text-muted">Sin documentos esperados para este waiver.</p>
              ) : (
                <ul className="space-y-1.5">
                  {docs.documents.map((d) => (
                    <li key={d.document} className="flex items-center justify-between gap-3 text-sm">
                      <span className="text-ink">{d.document}</span>
                      {d.found ? (
                        d.matches[0]?.web_url
                          ? <a href={d.matches[0].web_url} target="_blank" rel="noreferrer"><Stamp tone="ok">encontrado</Stamp></a>
                          : <Stamp tone="ok">encontrado</Stamp>
                      ) : (
                        <Stamp tone="stop">no encontrado</Stamp>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </DetailBlock>
          )}

          {data.secondary_issues?.length > 0 && (
            <Field label="Issues secundarios" value={data.secondary_issues.join(' · ')} />
          )}

          {data.suggested_attachments?.length > 0 && (
            <DetailBlock title="Adjuntos sugeridos">
              <div className="space-y-1">
                {data.suggested_attachments.map((p) => <p key={p} className="token break-all">{p}</p>)}
              </div>
            </DetailBlock>
          )}

          {data.suggested_response && (
            <DetailBlock title="Borrador de respuesta">
              <pre className="text-xs whitespace-pre-wrap font-sans text-ink/90 leading-relaxed">{data.suggested_response}</pre>
            </DetailBlock>
          )}

          {data.raw_llm_response && (
            <DetailBlock title="Razonamiento del modelo (LLM)">
              <pre className="text-xs whitespace-pre-wrap font-sans text-ink/80 leading-relaxed">{data.raw_llm_response}</pre>
            </DetailBlock>
          )}

          {/* Correo original */}
          {data.email && (
            <DetailBlock title="Correo original">
              <div className="space-y-2">
                <Field label="De" value={data.email.sender} mono />
                <Field label="Asunto" value={data.email.subject} />
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
                {approving && <Spinner className="border-white/40 border-t-white" />} Aprobar
              </button>
              <button onClick={() => onCorrect(data)} className="btn btn-ghost flex-1">Corregir</button>
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
      <ConfCard label="Total" value={stats?.total_classified} threshold="clasificados por reglas" accent="border-navy" dim="#1C2445" />
      <ConfCard label="Alta" value={c.high} threshold="≥ 85%" accent="border-ok" dim="#0F7B4A" />
      <ConfCard label="Media" value={c.medium} threshold="60 – 85%" accent="border-warn" dim="#B45309" />
      <ConfCard label="Baja" value={c.low} threshold="< 60% · revisar" accent="border-stop" dim="#B42318" />
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
        title="Clasificaciones"
        subtitle={`${data.total} resultados. Abre una para ver el porqué, aprobar o corregir.`}
        actions={
          <div className="flex gap-2">
            <select value={level} onChange={(e) => setLevel(e.target.value)} className="field">
              <option value="">Toda confianza</option>
              <option value="high">Alta</option>
              <option value="medium">Media</option>
              <option value="low">Baja</option>
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
            ? 'Sin clasificaciones rechazadas.'
            : 'Sin clasificaciones en este estado.'}
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
                    {c.escalate_for_review && <Stamp tone="stop">escalar</Stamp>}
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
                  <IconButton icon={Eye} label="Ver" onClick={() => setSelected(c.id)} />
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
      />
      <CorrectModal
        open={correcting !== null}
        item={correcting}
        onClose={() => setCorrecting(null)}
        onSaved={() => { load(level); setSelected(null) }}
      />
    </div>
  )
}
