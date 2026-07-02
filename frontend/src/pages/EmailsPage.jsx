import { useState, useEffect, useCallback } from 'react'
import { emailsApi } from '../lib/api'
import { PageHeader, Loading, Empty, ErrorBox } from '../components/ui'

export default function EmailsPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

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
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Asunto o remitente…"
              className="field w-64"
            />
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
                <tr key={e.id}>
                  <td className="max-w-md truncate text-ink" title={e.subject}>
                    {e.subject || '(sin asunto)'}
                  </td>
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
    </div>
  )
}
