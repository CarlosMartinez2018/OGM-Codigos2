import { useState, useEffect, useCallback } from 'react'
import { sharepointApi } from '../lib/api'
import { fmtDate } from '../lib/dates'
import { PageHeader, Stamp, Spinner, Loading, Empty, ErrorBox, StatCard, StatStrip } from '../components/ui'
import { Files, FolderTree, HardDrive } from 'lucide-react'

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
  const [stats, setStats] = useState({ files: 0, folders: 0, drives: 0 })
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

  const loadStats = useCallback(() => {
    Promise.all([
      sharepointApi.list({ only_files: true, limit: 1 }),
      sharepointApi.list({ only_files: false, limit: 1 }),
      sharepointApi.drives(),
    ])
      .then(([f, all, dv]) => setStats({
        files: f.total || 0,
        folders: Math.max((all.total || 0) - (f.total || 0), 0),
        drives: dv.total ?? (dv.items || []).length,
      }))
      .catch(() => {})
  }, [])

  useEffect(() => { load('', ''); loadStats() }, [load, loadStats])

  const sync = async () => {
    setSyncing(true); setError(''); setMsg('')
    try {
      const r = await sharepointApi.sync()
      setMsg(`Sync OK · ${r.files_added} new · ${r.files_updated} updated · ${r.items_seen} items · ${r.took_seconds}s`)
      load(q, drive); loadStats()
    } catch (e) { setError(e.message) } finally { setSyncing(false) }
  }

  const onSearch = (e) => { e.preventDefault(); load(q, drive) }

  return (
    <div className="p-8 space-y-5 max-w-6xl">
      <PageHeader
        title="SharePoint"
        subtitle={`${data.total} indexed files${drives.length ? ` · ${drives.length} libraries` : ''}.`}
        actions={
          <button onClick={sync} disabled={syncing} className="btn btn-primary">
            {syncing && <Spinner className="border-white/40 border-t-white" />} Sync
          </button>
        }
      />

      <StatStrip cols={3}>
        <StatCard icon={Files} tone="navy" label="Files" value={stats.files} sub="indexed documents" />
        <StatCard icon={FolderTree} tone="coral" label="Folders" value={stats.folders} sub="containers" />
        <StatCard icon={HardDrive} tone="ok" label="Drives" value={stats.drives} sub="libraries" />
      </StatStrip>

      {msg && <div className="text-sm text-ok bg-ok/10 ring-1 ring-inset ring-ok/25 rounded-md px-4 py-2">{msg}</div>}
      <ErrorBox message={error} />

      <form onSubmit={onSearch} className="flex flex-wrap gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or path…" className="field w-72" />
        <select value={drive} onChange={(e) => { setDrive(e.target.value); load(q, e.target.value) }} className="field">
          <option value="">All libraries</option>
          {drives.map((d) => <option key={d.drive_name} value={d.drive_name}>{d.drive_name} ({d.files})</option>)}
        </select>
        <button className="btn btn-ghost">Search</button>
      </form>

      {loading ? (
        <Loading />
      ) : (
        <div className="card overflow-x-auto">
          <table className="ledger">
            <thead>
              <tr>
                <th>File</th>
                <th>Library</th>
                <th>Type</th>
                <th className="text-right">Size</th>
                <th className="text-right">Modified</th>
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
                <tr><td colSpan={5}><Empty>No files. Click Sync to index SharePoint.</Empty></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
