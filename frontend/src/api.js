const TOKEN_KEY = 'ks_token'
export const LOGOUT_EVENT = 'ks:logout'

export const auth = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } },
  set: (t) => { try { localStorage.setItem(TOKEN_KEY, t) } catch { /* private mode */ } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ } },
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

function detailText(d, fallback) {
  if (!d) return fallback
  if (typeof d === 'string') return d
  // FastAPI validation errors: [{loc, msg, type}]
  if (Array.isArray(d)) return d.map((x) => (x && x.msg) || JSON.stringify(x)).join('; ')
  return JSON.stringify(d)
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' }
  const t = auth.get()
  if (t) headers.Authorization = `Bearer ${t}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let res
  try {
    res = await fetch(`/api${path}`, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined })
  } catch {
    throw new ApiError(0, 'Cannot reach the studio server — is the backend running?')
  }
  if (res.status === 401 && path !== '/login') {
    auth.clear()
    window.dispatchEvent(new Event(LOGOUT_EVENT))
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try { const j = await res.json(); msg = detailText(j.detail, msg) } catch { /* not JSON */ }
    throw new ApiError(res.status, msg)
  }
  if (res.status === 204) return null
  const text = await res.text()
  if (!text) return null
  try { return JSON.parse(text) } catch { return text }
}

export const get = (p) => api(p)
export const post = (p, body = {}) => api(p, { method: 'POST', body })
export const put = (p, body) => api(p, { method: 'PUT', body })
export const patch = (p, body) => api(p, { method: 'PATCH', body })
export const del = (p) => api(p, { method: 'DELETE' })

/** URL for <img>/<video> tags that can't send headers: appends ?token= */
export function authedUrl(path) {
  const full = path.startsWith('/api') ? path : `/api${path}`
  const sep = full.includes('?') ? '&' : '?'
  return `${full}${sep}token=${encodeURIComponent(auth.get() || '')}`
}

/** Character art (public endpoint). Works for every library character. */
export function castImg(id, { emotion = 'happy', arms, size, style } = {}) {
  const q = new URLSearchParams({ emotion })
  if (arms) q.set('arms', arms)
  if (size) q.set('size', String(size))
  if (style && style !== 'auto') q.set('style', style)
  return `/api/cast/${encodeURIComponent(id)}.png?${q}`
}

/** Sample frame of an art style (public endpoint). */
export function styleImg(id) {
  return `/api/styles/${encodeURIComponent(id)}.png`
}

/** Media URLs returned by the backend may be relative (/media/...) or absolute. */
export function mediaUrl(u) {
  if (!u) return null
  if (/^https?:\/\//.test(u) || u.startsWith('/')) return u
  return `/${u}`
}
