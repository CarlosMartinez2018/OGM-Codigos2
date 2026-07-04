import { useState, useEffect, useCallback } from 'react'
import { emailsApi } from '../lib/api'
import { PageHeader, Loading, Empty, ErrorBox, Field, DetailBlock, Stamp } from '../components/ui'
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
            <Field label="Recibido" value={data.received_date ? data.received_date.slice(0, 10) : '—'} mono />
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

export default function EmailsPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)

  const load = useCallback((term) => {
    setLoading(true)
    emailsApi.list({ limit: 100, search: term })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load('') }, [load])

  const onSearch = (e) => { e.preventDefault(); load(search) }

  return (
    <div className="p-8 space-y-6 max-w-6xl">
      <PageHeader
        title="Bandeja de producción"
        subtitle={`${data.total} correos ingestados.`}
        actions={
          <form onSubmit={onSearch} className="flex gap-2">
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Asunto o remitente…" className="field w-64" />
            <button className="btn btn-ghost">Buscar</button>
          </form>
        }
      />

      <ErrorBox message={error} />

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
              {data.items.map((e) => (
                <tr key={e.id} className="cursor-pointer" onClick={() => setSelected(e.id)}>
                  <td className="max-w-md truncate text-ink" title={e.subject}>{e.subject || '(sin asunto)'}</td>
                  <td className="text-muted truncate max-w-[15rem]" title={e.sender}>{e.sender}</td>
                  <td><span className="token">{e.sender_domain}</span></td>
                  <td className="text-right font-mono text-xs text-muted whitespace-nowrap tnum">
                    {e.received_date ? e.received_date.slice(0, 10) : '—'}
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr><td colSpan={4}><Empty>Sin correos.</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <EmailDrawer id={selected} open={selected !== null} onClose={() => setSelected(null)} />
    </div>
  )
}
