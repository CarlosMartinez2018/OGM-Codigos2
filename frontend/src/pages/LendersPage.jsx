import { useState, useEffect, useCallback } from 'react'
import { lendersApi } from '../lib/api'
import { Badge, Spinner, ErrorBox } from '../components/ui'

export default function LendersPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(null) // domain en proceso

  const load = useCallback((statusFilter) => {
    setLoading(true)
    lendersApi.list({ status: statusFilter })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load('') }, [load])

  const act = async (domain, action) => {
    setBusy(domain)
    setError('')
    try {
      if (action === 'approve') await lendersApi.approve(domain)
      else await lendersApi.reject(domain)
      load(status)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Lenders</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {data.total} dominios en domain_lender_map. Aprobar reprocesa sus correos.
          </p>
        </div>
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); load(e.target.value) }}
          className="px-3 py-2 rounded-lg border border-slate-200 text-sm"
        >
          <option value="">Todos los estados</option>
          <option value="APROBADO">APROBADO</option>
          <option value="POR_APROBAR">POR_APROBAR</option>
          <option value="NO_APROBADO">NO_APROBADO</option>
        </select>
      </div>

      <ErrorBox message={error} />

      {loading ? (
        <div className="flex items-center gap-2 text-slate-400"><Spinner /> Cargando…</div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-2 font-semibold">Dominio</th>
                <th className="text-left px-4 py-2 font-semibold">Lender</th>
                <th className="text-left px-4 py-2 font-semibold">Estado</th>
                <th className="text-right px-4 py-2 font-semibold">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((l) => (
                <tr key={l.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-2 font-mono text-slate-700">{l.domain}</td>
                  <td className="px-4 py-2 text-slate-700">{l.lender_name}</td>
                  <td className="px-4 py-2"><Badge tone={l.status}>{l.status}</Badge></td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">
                    {busy === l.domain ? (
                      <Spinner />
                    ) : (
                      <div className="inline-flex gap-2">
                        {l.status !== 'APROBADO' && (
                          <button
                            onClick={() => act(l.domain, 'approve')}
                            className="px-2.5 py-1 rounded-md bg-emerald-600 text-white text-xs hover:bg-emerald-700"
                          >
                            Aprobar
                          </button>
                        )}
                        {l.status !== 'NO_APROBADO' && (
                          <button
                            onClick={() => act(l.domain, 'reject')}
                            className="px-2.5 py-1 rounded-md bg-red-100 text-red-700 text-xs hover:bg-red-200"
                          >
                            Rechazar
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-6 text-center text-slate-400">Sin lenders.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
