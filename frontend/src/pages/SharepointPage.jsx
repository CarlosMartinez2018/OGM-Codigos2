import { useState, useEffect, useCallback } from 'react'
import { sharepointApi } from '../lib/api'
import { fmtDate } from '../lib/dates'
import { PageHeader, Stamp, Spinner, Loading, Empty, ErrorBox } from '../components/ui'

function humanSize(b) {
  if (b == null) return '—'
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0, n = b
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${u[i]}`
}

export default function SharepointPage() {
  const [drives, setDrives] = useState([])
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [q, setQ] = useState('')
  const [drive, setDrive] = useState('')

  const load = useCallback((query, dr) => {
    setLoading(true)
    Promise.all([
      sharepointApi.list({ q: query, drive: dr, limit: 300 }),
      sharepointApi.drives(),
    ])
      .then(([files, dv]) => { setData(files); setDrives(dv.items || []) })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load('', '') }, [load])

  const sync = async () => {
    setSyncing(true); setError(''); setMsg('')
    try {
      const r = await sharepointApi.sync()
      setMsg(`Sync OK · ${r.files_added} nuevos · ${r.files_updated} actualizados · ${r.items_seen} items · ${r.took_seconds}s`)
      load(q, drive)
    } catch (e) { setError(e.message) } finally { setSyncing(false) }
  }

  const onSearch = (e) => { e.preventDefault(); load(q, drive) }

  return (
    <div className="p-8 space-y-5 max-w-6xl">
      <PageHeader
        title="SharePoint"
        subtitle={`${data.total} archivos indexados${drives.length ? ` · ${drives.length} bibliotecas` : ''}.`}
        actions={
          <button onClick={sync} disabled={syncing} className="btn btn-primary">
            {syncing && <Spinner className="border-white/40 border-t-white" />} Sincronizar
          </button>
        }
      />

      {msg && <div className="text-sm text-ok bg-ok/10 ring-1 ring-inset ring-ok/25 rounded-md px-4 py-2">{msg}</div>}
      <ErrorBox message={error} />

      <form onSubmit={onSearch} className="flex flex-wrap gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por nombre o ruta…" className="field w-72" />
        <select value={drive} onChange={(e) => { setDrive(e.target.value); load(q, e.target.value) }} className="field">
          <option value="">Todas las bibliotecas</option>
          {drives.map((d) => <option key={d.drive_name} value={d.drive_name}>{d.drive_name} ({d.files})</option>)}
        </select>
        <button className="btn btn-ghost">Buscar</button>
      </form>

      {loading ? (
        <Loading />
      ) : (
        <div className="card overflow-hidden">
          <table className="ledger">
            <thead>
              <tr>
                <th>Archivo</th>
                <th>Biblioteca</th>
                <th>Tipo</th>
                <th className="text-right">Tamaño</th>
                <th className="text-right">Modificado</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((f) => (
                <tr key={f.id}>
                  <td className="max-w-md truncate text-ink" title={f.path}>
                    {f.web_url
                      ? <a href={f.web_url} target="_blank" rel="noreferrer" className="text-navy hover:text-coral hover:underline">{f.name}</a>
                      : f.name}
                  </td>
                  <td className="text-muted">{f.drive_name}</td>
                  <td>{f.file_extension ? <Stamp tone="neutral">{f.file_extension}</Stamp> : <span className="text-faint">—</span>}</td>
                  <td className="text-right font-mono text-xs text-muted tnum">{humanSize(f.size)}</td>
                  <td className="text-right font-mono text-xs text-muted whitespace-nowrap tnum">
                    {fmtDate(f.sp_modified_at)}
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr><td colSpan={5}><Empty>Sin archivos. Pulsa Sincronizar para indexar SharePoint.</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
