import { useState, useEffect, useCallback } from 'react'
import { waiversApi } from '../lib/api'
import { PageHeader, Stamp, Spinner, Loading, Empty, ErrorBox, StatCard, StatStrip } from '../components/ui'
import { Table2, Building2, FileText } from 'lucide-react'
import Modal from '../components/Modal'

const EMPTY = {
  lender: '', waiver_type: '', triggers: '',
  evidence_required_ops: '', evidence_required_insurance: '',
  actions_to_automate: '', waiver_pack: '', documentsText: '',
}

function toForm(w) {
  return {
    lender: w.lender, waiver_type: w.waiver_type, triggers: w.triggers || '',
    evidence_required_ops: w.evidence_required_ops || '',
    evidence_required_insurance: w.evidence_required_insurance || '',
    actions_to_automate: w.actions_to_automate || '',
    waiver_pack: w.waiver_pack || '',
    documentsText: (w.documents || []).join('\n'),
  }
}

function WaiverModal({ open, onClose, editing, onSaved }) {
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setForm(editing ? toForm(editing) : EMPTY)
    setError('')
  }, [open, editing])

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    if (!form.lender.trim() || !form.waiver_type.trim()) { setError('Lender y waiver type son obligatorios.'); return }
    setSaving(true); setError('')
    const payload = {
      lender: form.lender, waiver_type: form.waiver_type, triggers: form.triggers,
      evidence_required_ops: form.evidence_required_ops,
      evidence_required_insurance: form.evidence_required_insurance,
      actions_to_automate: form.actions_to_automate, waiver_pack: form.waiver_pack,
      documents: form.documentsText.split('\n').map((d) => d.trim()).filter(Boolean),
    }
    try {
      if (editing) await waiversApi.update(editing.id, payload)
      else await waiversApi.create(payload)
      onSaved()
      onClose()
    } catch (err) { setError(err.message) } finally { setSaving(false) }
  }

  const T = ({ label, k, area }) => (
    <div>
      <label className="eyebrow">{label}</label>
      {area
        ? <textarea rows={2} value={form[k]} onChange={set(k)} className="field w-full mt-1 resize-none" />
        : <input value={form[k]} onChange={set(k)} className="field w-full mt-1" />}
    </div>
  )

  return (
    <Modal open={open} onClose={onClose} title={editing ? 'Editar waiver' : 'Nuevo waiver'} width="max-w-2xl">
      <form onSubmit={submit} className="px-6 py-5 space-y-3 max-h-[70vh] overflow-y-auto">
        <div className="grid grid-cols-2 gap-3">
          <T label="Lender" k="lender" />
          <T label="Waiver type" k="waiver_type" />
        </div>
        <T label="Triggers" k="triggers" area />
        <T label="Evidencia (Ops)" k="evidence_required_ops" area />
        <T label="Evidencia (Seguros)" k="evidence_required_insurance" area />
        <T label="Waiver pack" k="waiver_pack" area />
        <T label="Acciones a automatizar" k="actions_to_automate" area />
        <div>
          <label className="eyebrow">Documentos esperados (uno por línea)</label>
          <textarea rows={4} value={form.documentsText} onChange={set('documentsText')} className="field w-full mt-1 resize-none font-mono text-xs" />
        </div>
        <ErrorBox message={error} />
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="btn btn-ghost" disabled={saving}>Cancelar</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving && <Spinner className="border-white/40 border-t-white" />} Guardar
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default function WaiversPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    waiversApi.list()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const del = async (w) => {
    if (!confirm(`¿Borrar el waiver "${w.waiver_type}" de ${w.lender}?`)) return
    setError('')
    try { await waiversApi.delete(w.id); load() } catch (e) { setError(e.message) }
  }

  const openNew = () => { setEditing(null); setModalOpen(true) }
  const openEdit = (w) => { setEditing(w); setModalOpen(true) }

  return (
    <div className="p-8 space-y-6 max-w-6xl">
      <PageHeader
        title="Matriz de waivers"
        subtitle={`${data.total} combinaciones lender · waiver (knowledge base del clasificador).`}
        actions={<button onClick={openNew} className="btn btn-coral">+ Nuevo waiver</button>}
      />

      {!loading && data.items.length > 0 && (
        <StatStrip cols={3}>
          <StatCard icon={Table2} tone="navy" label="Total waivers" value={data.items.length} sub="combinaciones lender · waiver" />
          <StatCard icon={Building2} tone="coral" label="Lenders cubiertos" value={new Set(data.items.map((w) => w.lender)).size} sub="lenders distintos" />
          <StatCard icon={FileText} tone="ok" label="Documentos" value={data.items.reduce((n, w) => n + (w.documents?.length || 0), 0)} sub="esperados en total" />
        </StatStrip>
      )}

      <ErrorBox message={error} />

      {loading ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <Empty>Sin waivers configurados.</Empty>
      ) : (
        <div className="space-y-3">
          {data.items.map((w) => (
            <article key={w.id} className="card overflow-hidden border-l-2 border-navy">
              <div className="px-5 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-navy">{w.lender}</span>
                      <span className="text-faint">·</span>
                      <span className="text-ink">{w.waiver_type}</span>
                    </div>
                    {w.triggers && <p className="text-xs text-muted mt-1.5 max-w-2xl">{w.triggers}</p>}
                    {w.documents?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {w.documents.map((d) => <Stamp key={d} tone="neutral">{d}</Stamp>)}
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button onClick={() => openEdit(w)} className="btn btn-ghost text-xs px-2.5 py-1">Editar</button>
                    <button onClick={() => del(w)} className="btn btn-danger">Borrar</button>
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      <WaiverModal open={modalOpen} editing={editing} onClose={() => setModalOpen(false)} onSaved={load} />
    </div>
  )
}
