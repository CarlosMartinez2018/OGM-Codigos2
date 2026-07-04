// Formateo de fechas en la zona horaria de los correos: US Eastern.
//
// El backend entrega ISO-8601 en UTC con offset (p.ej. "2026-07-01T18:49:07+00:00").
// Antes se hacia iso.slice(0,10), que muestra la fecha UTC cruda -> desfase con lo
// que ve el usuario. Los correos son de EE.UU. (lenders/servicers), asi que se
// muestran en America/New_York, que maneja EST/EDT (horario de verano) solo.
// OJO: no usar la hora local del navegador: Bogota (UTC-5) != Eastern en verano
// (EDT = UTC-4), lo que corre la fecha 1h.

const TZ = 'America/New_York'

const _dateFmt = new Intl.DateTimeFormat('en-CA', {
  timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
})
const _timeFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false,
})

function _toDate(iso) {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

// Fecha corta en US Eastern: "2026-07-01" (en-CA da YYYY-MM-DD).
export function fmtDate(iso) {
  const d = _toDate(iso)
  return d ? _dateFmt.format(d) : '—'
}

// Fecha + hora en US Eastern: "2026-07-01 14:49 ET".
export function fmtDateTime(iso) {
  const d = _toDate(iso)
  if (!d) return '—'
  return `${_dateFmt.format(d)} ${_timeFmt.format(d)} ET`
}
