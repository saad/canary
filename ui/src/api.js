async function json(url, opts) {
  const res = await fetch(url, opts)
  if (!res.ok) throw new Error(`${url} → ${res.status}`)
  return res.json()
}

const post = (url, body) => json(url, { method: 'POST', body: JSON.stringify(body) })

export const api = {
  cases: () => json('/api/cases'),
  status: () => json('/api/status'),
  audit: () => json('/api/audit'),
  c1case: (id) => post('/api/c1case', { id }),
  approve: (id) => post('/api/case/approve', { id }),
  update: (id, note) => post('/api/case/update', { id, note }),
  close: (id, note) => post('/api/case/close', { id, note }),
  fom: (question) => post('/api/fom', { question }),
  inject: () => post('/api/inject', {}),
}

export const SOURCE_LABELS = {
  irs: 'IRS',
  ncua: 'NCUA',
  nacha: 'NACHA',
  federal_register: 'FedReg',
  fedreg: 'FedReg',
}

export function sourceOf(c) {
  return (c.item_id || '').split(':')[0]
}

export function relAge(ts) {
  if (!ts) return ''
  const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000)
  if (s < 60) return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}

export function fmtTs(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
