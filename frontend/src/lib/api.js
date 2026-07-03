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

// GET /health, GET /stats, GET /lenders-and-waivers
export const metaApi = {
  health: () => request('/health'),
  stats: () => request('/stats'),
  lendersAndWaivers: () => request('/lenders-and-waivers'),
}

// GET /lenders  ·  POST /lenders/{domain}/approve|reject
export const lendersApi = {
  list: (params = {}) => request(`/lenders${qs(params)}`),
  approve: (domain) => request(`/lenders/${encodeURIComponent(domain)}/approve`, { method: 'POST' }),
  reject: (domain) => request(`/lenders/${encodeURIComponent(domain)}/reject`, { method: 'POST' }),
}

// GET /emails · GET /emails/{id}
export const emailsApi = {
  list: (params = {}) => request(`/emails${qs(params)}`),
  get: (id) => request(`/emails/${id}`),
}

// GET /reviews(/{id}) · discard · answer
export const reviewsApi = {
  list: (params = {}) => request(`/reviews${qs(params)}`),
  get: (id) => request(`/reviews/${id}`),
  discard: (id, note) => request(`/reviews/${id}/discard`, { method: 'POST', body: JSON.stringify({ note }) }),
  answer: (id, note) => request(`/reviews/${id}/answer`, { method: 'POST', body: JSON.stringify({ note }) }),
}

// GET /classifications(/{id}) · POST /classify/run · approve · correct
export const classificationsApi = {
  list: (params = {}) => request(`/classifications${qs(params)}`),
  get: (id) => request(`/classifications/${id}`),
  documents: (id) => request(`/classifications/${id}/documents`),
  run: (limit = 0, reclassify = false) =>
    request(`/classify/run${qs({ limit, reclassify })}`, { method: 'POST' }),
  approve: (id, reviewedBy = 'operator') =>
    request(`/classifications/${id}/approve${qs({ reviewed_by: reviewedBy })}`, { method: 'POST' }),
  correct: (id, payload) =>
    request(`/classifications/${id}/correct`, { method: 'POST', body: JSON.stringify(payload) }),
}

// SharePoint (inventario)
export const sharepointApi = {
  status: () => request('/sharepoint/status'),
  drives: () => request('/sharepoint/drives'),
  list: (params = {}) => request(`/sharepoint/files${qs(params)}`),
  sync: () => request('/sharepoint/sync', { method: 'POST' }),
}

// Matriz lender-waiver (CRUD)
export const waiversApi = {
  list: (params = {}) => request(`/waivers${qs(params)}`),
  create: (payload) => request('/waivers', { method: 'POST', body: JSON.stringify(payload) }),
  update: (id, payload) => request(`/waivers/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  delete: (id) => request(`/waivers/${id}`, { method: 'DELETE' }),
}
