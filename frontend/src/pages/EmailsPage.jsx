import { useState, useEffect, useCallback } from 'react'
import { emailsApi } from '../lib/api'
import { Spinner, ErrorBox } from '../components/ui'

export default function EmailsPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  const load = useCallback((searchTerm) => {
    setLoading(true)
    emailsApi.list({ limit: 100, search: searchTerm })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load('') }, [load])

  const onSearch = (e) => {
    e.preventDefault()
    load(search)
  }

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Inbox</h1>
        <p className="text-sm text-slate-500 mt-0.5">{data.total} correos en production_emails.</p>
      </div>

      <form onSubmit={onSearch} className="flex gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar por asunto o remitente…"
          className="flex-1 max-w-md px-3 py-2 rounded-lg border border-slate-200 text-sm"
        />
        <button className="px-4 py-2 rounded-lg bg-slate-800 text-white text-sm">Buscar</button>
      </form>

      <ErrorBox message={error} />

      {loading ? (
        <div className="flex items-center gap-2 text-slate-400"><Spinner /> Cargando…</div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-2 font-semibold">Asunto</th>
                <th className="text-left px-4 py-2 font-semibold">Remitente</th>
                <th className="text-left px-4 py-2 font-semibold">Dominio</th>
                <th className="text-left px-4 py-2 font-semibold">Recibido</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((e) => (
                <tr key={e.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-2 max-w-md truncate" title={e.subject}>{e.subject || '(sin asunto)'}</td>
                  <td className="px-4 py-2 text-slate-600 truncate max-w-[16rem]" title={e.sender}>{e.sender}</td>
                  <td className="px-4 py-2 text-slate-500">{e.sender_domain}</td>
                  <td className="px-4 py-2 text-slate-500 whitespace-nowrap">
                    {e.received_date ? e.received_date.slice(0, 10) : '—'}
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-6 text-center text-slate-400">Sin correos.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
