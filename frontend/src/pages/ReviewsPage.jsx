import { useState, useEffect, useCallback } from 'react'
import { reviewsApi } from '../lib/api'
import { fmtDate, fmtDateTime } from '../lib/dates'
import { Stamp, PageHeader, Spinner, Loading, Empty, ErrorBox, Field, DetailBlock } from '../components/ui'
import Drawer from '../components/Drawer'

// Tabs → grupos de estado.
const TABS = [
  { key: 'PENDIENTE', label: 'Por revisar' },
  { key: 'DESCARTADO', label: 'Descartados' },
  { key: 'CONTESTADO,GESTIONADO', label: 'Contestados' },
]

// Stages para el filtro (lender_nuevo + lender_por_aprobar unificados).
const STAGE_OPTS = [
  { value: '', label: 'Todas las etapas' },
  { value: 'lender_nuevo,lender_por_aprobar', label: 'Lender por aprobar' },
  { value: 'reenvio', label: 'Reenvío' },
  { value: 'hilo_incompleto', label: 'Hilo incompleto' },
  { value: 'duplicado', label: 'Misma conversación' },
  { value: 'seguridad_bloqueo', label: 'Seguridad / bloqueo' },
  { value: 'blacklist', label: 'Blacklist' },
]

// Explicación adicional por etapa (para el operador).
const STAGE_HELP = {
  hilo_incompleto: 'No se encontró en el buzón el correo original del lender para esta conversación, así que no se puede identificar el lender ni el contexto. Falta el mensaje raíz del hilo: ubícalo o responde desde el hilo correcto.',
  duplicado: 'No es un duplicado real: es un reenvío o respuesta sobre el mismo hilo. Revisa la conversación completa abajo para ubicar a qué caso pertenece.',
  reenvio: 'La solicitud llegó reenviada, no directa del lender al buzón.',
  lender_nuevo: 'Dominio sin aprobar. Apruébalo en Lenders para que sus correos se clasifiquen.',
  lender_por_aprobar: 'Dominio pendiente de aprobación. Apruébalo en Lenders.',
  seguridad_bloqueo: 'Contenido cifrado, truncado o bloqueado; no se pudo leer el cuerpo.',
  blacklist: 'Dominio en blacklist (NO_APROBADO): ruido o rechazado.',
}

function ReviewDrawer({ id, open, onClose, onResolved }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')

  const load = useCallback(() => {
    if (!id) return
    setLoading(true)
    reviewsApi.get(id).then(setData).catch(() => setData(null)).finally(() => setLoading(false))
  }, [id])

  useEffect(() => { if (open) { setNote(''); load() } }, [open, load])

  const act = async (kind) => {
    setBusy(kind)
    try {
      if (kind === 'discard') await reviewsApi.discard(id, note || undefined)
      else await reviewsApi.answer(id, note || undefined)
      onResolved()
      onClose()
    } finally { setBusy('') }
  }

  const help = data ? STAGE_HELP[data.stage] : null

  return (
    <Drawer open={open} onClose={onClose} title={data?.subject || 'Correo en revisión'}>
      {loading || !data ? <Loading /> : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Stamp tone={data.internal_forward ? 'neutral' : 'warn'}>
              {data.internal_forward && data.stage === 'reenvio' ? 'Reenvío interno' : data.stage_label}
            </Stamp>
            <Stamp tone={data.status === 'PENDIENTE' ? 'warn' : data.status === 'DESCARTADO' ? 'stop' : 'ok'}>
              {data.status}
            </Stamp>
          </div>

          {/* Motivo + explicación */}
          <DetailBlock title="Motivo del descarte automático">
            <p className="text-sm text-ink">{data.reason}</p>
            {help && <p className="text-xs text-muted mt-2">{help}</p>}
          </DetailBlock>

          {/* Meta */}
          <div className="grid grid-cols-2 gap-4">
            <Field label="Dominio remitente" value={data.sender_domain || '—'} mono />
            <Field label="Remitente" value={data.sender || '(no disponible)'} mono />
            <Field label="Recibido" value={fmtDateTime(data.received_date)} mono />
            <Field label="Remitente original" value={data.detected_original_sender || '—'} mono />
          </div>

          {/* Hilo de conversación */}
          {data.thread?.length > 0 && (
            <DetailBlock title={`Conversación (${data.thread.length} correos)`}>
              <ol className="space-y-2">
                {data.thread.map((e) => (
                  <li key={e.id} className={`text-sm border-l-2 pl-3 ${e.is_current ? 'border-coral' : 'border-line'}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="token">{e.sender_domain || e.sender || '—'}</span>
                      <span className="font-mono text-[11px] text-faint tnum">{fmtDate(e.received_date)}</span>
                    </div>
                    <p className="text-ink truncate">{e.subject || '(sin asunto)'}</p>
                  </li>
                ))}
              </ol>
            </DetailBlock>
          )}

          {/* Cuerpo del correo */}
          {data.email?.body_text && (
            <DetailBlock title="Cuerpo del correo">
              <pre className="text-xs whitespace-pre-wrap font-sans text-ink/90 leading-relaxed max-h-72 overflow-y-auto">
                {data.email.body_text.slice(0, 5000)}
              </pre>
            </DetailBlock>
          )}

          {/* Acciones (solo si pendiente) */}
          {data.status === 'PENDIENTE' ? (
            <div className="space-y-2 pt-1">
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
                placeholder="Nota (opcional): qué se hizo / por qué se descarta…" className="field w-full resize-none" />
              <div className="flex gap-2">
                <button onClick={() => act('answer')} disabled={!!busy} className="btn btn-ok flex-1 py-2 text-sm">
                  {busy === 'answer' && <Spinner className="border-white/40 border-t-white" />} Marcar contestado
                </button>
                <button onClick={() => act('discard')} disabled={!!busy} className="btn btn-danger flex-1 py-2 text-sm">
                  {busy === 'discard' && <Spinner />} Descartar
                </button>
              </div>
            </div>
          ) : (
            <div className="card px-4 py-3 text-sm text-muted">
              <Stamp tone={data.status === 'DESCARTADO' ? 'stop' : 'ok'}>{data.status}</Stamp>
              {data.note && <p className="mt-2">{data.note}</p>}
            </div>
          )}
        </div>
      )}
    </Drawer>
  )
}

export default function ReviewsPage() {
  const [tab, setTab] = useState('PENDIENTE')
  const [stage, setStage] = useState('')
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)

  const load = useCallback((status, st) => {
    setLoading(true)
    reviewsApi.list({ status, stage: st, limit: 300 })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(tab, stage) }, [load, tab, stage])

  return (
    <div className="p-8 space-y-5 max-w-6xl">
      <PageHeader
        title="Cola de revisión"
        subtitle="Correos descartados por el pre-filtrado. Ábrelos para ver el correo, el hilo y descartar o contestar."
        actions={
          <select value={stage} onChange={(e) => setStage(e.target.value)} className="field">
            {STAGE_OPTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        }
      />

      {/* Tabs */}
      <div className="tabs-container flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
              tab === t.key ? 'border-coral text-navy' : 'border-transparent text-muted hover:text-navy'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <ErrorBox message={error} />

      {loading ? (
        <Loading />
      ) : (
        <div className="card overflow-hidden">
          <table className="ledger">
            <thead>
              <tr>
                <th>Etapa</th>
                <th>Dominio</th>
                <th>Asunto</th>
                <th className="text-right">Recibido</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id} className="cursor-pointer" onClick={() => setSelected(r.id)}>
                  <td>
                    <Stamp tone={r.internal_forward && r.stage === 'reenvio' ? 'neutral' : 'warn'}>
                      {r.internal_forward && r.stage === 'reenvio' ? 'Reenvío interno' : r.stage_label}
                    </Stamp>
                  </td>
                  <td><span className="token">{r.sender_domain || '—'}</span></td>
                  <td className="max-w-md truncate text-ink" title={r.subject}>{r.subject || '(sin asunto)'}</td>
                  <td className="text-right font-mono text-xs text-muted whitespace-nowrap tnum">{fmtDate(r.received_date)}</td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr><td colSpan={4}><Empty>Nada en esta pestaña.</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <ReviewDrawer
        id={selected}
        open={selected !== null}
        onClose={() => setSelected(null)}
        onResolved={() => load(tab, stage)}
      />
    </div>
  )
}
