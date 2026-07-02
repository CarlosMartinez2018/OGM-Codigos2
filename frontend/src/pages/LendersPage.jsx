import { useState, useEffect, useCallback } from 'react'
import { lendersApi } from '../lib/api'
import { Stamp, stampTone, PageHeader, Spinner, Loading, Empty, ErrorBox } from '../components/ui'

export default function LendersPage() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(null)

  const load = useCallback((s) => {
    setLoading(true)
    lendersApi.list({ status: s })
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
    <div className="p-8 space-y-6 max-w-6xl">
      <PageHeader
        title="Lenders"
        subtitle={`${data.total} dominios. Aprobar reprocesa sus correos por el pipeline.`}
        actions={
          <select
            value={status}
            onChange={(e) => { setStatus(e.target.value); load(e.target.value) }}
            className="field"
          >
            <option value="">Todos los estados</option>
            <option value="APROBADO">Aprobados</option>
            <option value="POR_APROBAR">Por aprobar</option>
            <option value="NO_APROBADO">Rechazados</option>
          </select>
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
                <th>Dominio</th>
                <th>Lender</th>
                <th>Estado</th>
                <th className="text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((l) => (
                <tr key={l.id}>
                  <td><span className="token">{l.domain}</span></td>
                  <td className="text-ink">{l.lender_name}</td>
                  <td><Stamp tone={stampTone(l.status)}>{l.status}</Stamp></td>
                  <td className="text-right whitespace-nowrap">
                    {busy === l.domain ? (
                      <Spinner />
                    ) : (
                      <div className="inline-flex gap-2">
                        {l.status !== 'APROBADO' && (
                          <button onClick={() => act(l.domain, 'approve')} className="btn btn-ok">
                            Aprobar
                          </button>
                        )}
                        {l.status !== 'NO_APROBADO' && (
                          <button onClick={() => act(l.domain, 'reject')} className="btn btn-danger">
                            Rechazar
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr><td colSpan={4}><Empty>Sin lenders.</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
