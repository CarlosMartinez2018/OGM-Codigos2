// Cliente API — contrato 1:1 con api.py (FastAPI, router /api/v1).
const BASE = '/api/v1'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  if (res.status === 204) return null
  return res.json()
}

function qs(params = {}) {
  const clean = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  )
  const s = new URLSearchParams(clean).toString()
  return s ? `?${s}` : ''
}

// GET /health, GET /stats
export const metaApi = {
  health: () => request('/health'),
  stats: () => request('/stats'),
}

// GET /lenders  ·  POST /lenders/{domain}/approve|reject
export const lendersApi = {
  list: (params = {}) => request(`/lenders${qs(params)}`),
  approve: (domain) => request(`/lenders/${encodeURIComponent(domain)}/approve`, { method: 'POST' }),
  reject: (domain) => request(`/lenders/${encodeURIComponent(domain)}/reject`, { method: 'POST' }),
}

// GET /emails
export const emailsApi = {
  list: (params = {}) => request(`/emails${qs(params)}`),
}

// GET /reviews
export const reviewsApi = {
  list: (params = {}) => request(`/reviews${qs(params)}`),
}

// GET /classifications  ·  POST /classify/run
export const classificationsApi = {
  list: (params = {}) => request(`/classifications${qs(params)}`),
  run: (limit = 0, reclassify = false) =>
    request(`/classify/run${qs({ limit, reclassify })}`, { method: 'POST' }),
}
