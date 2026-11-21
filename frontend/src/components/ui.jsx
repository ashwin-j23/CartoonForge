import { Component, createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'
import { api, get } from '../api'
import Icon from './icons'

export { Icon }

/* ------------------------------------------------------------------ toasts */
const ToastCtx = createContext(() => {})
const TOAST_ICON = { ok: 'checkCircle', bad: 'alertCircle', info: 'info' }

/** Strip a leading emoji from legacy toast messages so the icon carries the meaning. */
const cleanMsg = (m) => String(m).replace(/^[\p{Extended_Pictographic}️‍\s]+/u, '')

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((msg, kind = 'ok') => {
    const id = Math.random().toString(36).slice(2)
    setItems((x) => [...x.slice(-3), { id, msg: cleanMsg(msg), kind }])
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), kind === 'bad' ? 7000 : 3800)
  }, [])
  const close = (id) => setItems((x) => x.filter((i) => i.id !== id))
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <Icon name={TOAST_ICON[t.kind] || 'info'} size={18} className="toast-ico" />
            <span className="toast-msg">{t.msg}</span>
            <button className="toast-x" onClick={() => close(t.id)} aria-label="Dismiss"><Icon name="x" size={14} /></button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}
export const useToast = () => useContext(ToastCtx)

/* ------------------------------------------------------------- data hooks */
/**
 * Loads `path` and optionally re-polls every `ms` (paused while tab hidden).
 * `ms` may be a function of current data so callers can poll fast only while work is running.
 * `quiet` suppresses error toasts (use for optional / not-yet-deployed endpoints).
 */
export function useApi(path, { ms = 0, quiet = false } = {}) {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(!!path)
  const alive = useRef(true)
  const load = useCallback(async (silent) => {
    if (!path) { setLoading(false); return null }
    try {
      const d = await get(path)
      if (alive.current) { setData(d); setError(null) }
      return d
    } catch (e) {
      if (alive.current) {
        setError(e)
        if (!silent && !quiet && e.status !== 401) toast(e.message, 'bad')
      }
      return null
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [path, quiet, toast])

  useEffect(() => {
    alive.current = true
    setLoading(!!path)
    load(false)
    return () => { alive.current = false }
  }, [load, path])

  const interval = typeof ms === 'function' ? ms(data) : ms
  useEffect(() => {
    if (!interval) return undefined
    const t = setInterval(() => { if (!document.hidden) load(true) }, interval)
    return () => clearInterval(t)
  }, [interval, load])

  return { data, error, loading, reload: load, setData }
}

/** Wraps an async action with busy flag + toasts. */
export function useAction() {
  const toast = useToast()
  const [busy, setBusy] = useState(null)
  const run = useCallback(async (key, fn, okMsg) => {
    setBusy(key)
    try {
      const r = await fn()
      if (okMsg) toast(typeof okMsg === 'function' ? okMsg(r) : okMsg, 'ok')
      return r
    } catch (e) {
      if (e.status !== 401) toast(e.message || String(e), 'bad')
      return undefined
    } finally {
      setBusy(null)
    }
  }, [toast])
  return [busy, run]
}

/* ------------------------------------------------- cached reference data */
const staticCache = new Map()
/** For reference data that rarely changes (categories, cast, psychology, languages, voices, styles). */
export function useStatic(path, { quiet = false } = {}) {
  const toast = useToast()
  const [data, setData] = useState(() => (path ? staticCache.get(path)?.value ?? null : null))
  const [error, setError] = useState(null)
  useEffect(() => {
    if (!path) return undefined
    let alive = true
    let entry = staticCache.get(path)
    if (!entry) {
      entry = { promise: api(path) }
      staticCache.set(path, entry)
      entry.promise.then((v) => { entry.value = v }, () => staticCache.delete(path))
    }
    entry.promise.then((v) => { if (alive) { setData(v); setError(null) } }, (e) => {
      if (!alive) return
      setError(e)
      if (!quiet && e.status !== 401) toast(e.message, 'bad')
    })
    return () => { alive = false }
  }, [path, quiet, toast])
  return quiet ? { data, error } : data
}
export function invalidateStatic(path) { staticCache.delete(path) }

/** Map category id → category */
export function useCategoryMap() {
  const cats = useStatic('/categories')
  const map = {}
  for (const c of cats || []) map[c.id] = c
  return [cats, map]
}

/* ---------------------------------------------------------------- status */
export const STATUS = {
  planned: { label: 'Planned', icon: 'clock', tone: 'neutral', live: true },
  writing: { label: 'Writing', icon: 'pen', tone: 'blue', live: true },
  scripted: { label: 'Scripted', icon: 'file', tone: 'blue' },
  rendering: { label: 'Rendering', icon: 'film', tone: 'violet', live: true },
  review: { label: 'Needs review', icon: 'eye', tone: 'amber' },
  approved: { label: 'Scheduled', icon: 'calendar', tone: 'green' },
  publishing: { label: 'Publishing', icon: 'rocket', tone: 'green', live: true },
  upcoming: { label: 'Upcoming on YouTube', icon: 'clock', tone: 'blue' },
  published: { label: 'Live on YouTube', icon: 'star', tone: 'green' },
  failed: { label: 'Failed', icon: 'alertCircle', tone: 'red' },
  rejected: { label: 'Rejected', icon: 'ban', tone: 'neutral' },
}
export const STATUS_ORDER = ['review', 'failed', 'planned', 'writing', 'scripted', 'rendering', 'approved', 'publishing', 'upcoming', 'published', 'rejected']
/** 'upcoming' = uploaded to YouTube but still private until its time; 'published' = public now. */
export const shownStatus = (e) => (e?.status === 'published' && e.published_at && new Date(e.published_at) > new Date() ? 'upcoming' : e?.status)
export const LIVE_STATUSES = new Set(['planned', 'writing', 'rendering', 'publishing'])
export const isLive = (e) => !!e && (LIVE_STATUSES.has(e.status) || (e.progress && e.progress.pct != null && e.progress.pct < 100))

export function Badge({ tone = 'neutral', icon, children, dot, live, title, className = '', size }) {
  return (
    <span className={`badge t-${tone} ${size === 'sm' ? 'sm' : ''} ${live ? 'live' : ''} ${className}`} title={title}>
      {dot && <span className="badge-dot" />}
      {icon && <Icon name={icon} size={size === 'sm' ? 12 : 13} />}
      {children}
    </span>
  )
}

export function StatusPill({ status, small }) {
  const s = STATUS[status] || { label: status || 'unknown', icon: 'info', tone: 'neutral' }
  return <Badge tone={s.tone} dot={!s.live} live={s.live} size={small ? 'sm' : undefined}>{s.label}</Badge>
}

/** Critic scores may come on a 0–10 or 0–100 scale; infer from the values. */
export function scoreScale(...vals) {
  return vals.some((v) => typeof v === 'number' && v > 10) ? 100 : 10
}
export function fmtScore(v) {
  if (v == null || Number.isNaN(v)) return '—'
  return Number.isInteger(v) ? String(v) : Number(v).toFixed(1)
}

export function ScoreBadge({ score, bar }) {
  if (score == null) return null
  const max = scoreScale(score, bar)
  const tone = bar != null ? (score >= bar ? 'green' : score >= bar * 0.85 ? 'amber' : 'red') : (score / max >= 0.75 ? 'green' : score / max >= 0.6 ? 'amber' : 'red')
  return <Badge tone={tone} icon="star" size="sm" title={`Critic score ${fmtScore(score)} / ${max}`}>{fmtScore(score)}</Badge>
}

export function Progress({ pct, label, tone = 'brand' }) {
  const v = Math.max(0, Math.min(100, Number(pct) || 0))
  return (
    <div className="progress-wrap">
      {label != null && <div className="progress-label"><span>{label}</span><span className="mono">{Math.round(v)}%</span></div>}
      <div className={`progress t-${tone}`} role="progressbar" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100} aria-label={typeof label === 'string' ? label : 'Progress'}>
        <i style={{ width: `${v}%` }} />
      </div>
    </div>
  )
}

export function Bar({ value, max = 100, tone = 'blue', label }) {
  const v = Math.max(0, Math.min(100, ((Number(value) || 0) / (max || 1)) * 100))
  return (
    <div className="hbar" title={label}>
      <i className={`t-${tone}`} style={{ width: `${v}%` }} />
    </div>
  )
}

/* ------------------------------------------------------------- primitives */
export function Spinner({ size = 16 }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-hidden="true" />
}

export function Skeleton({ h = 18, w = '100%', r = 8, count = 1, style }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skel" style={{ height: h, width: w, borderRadius: r, ...style }} />
      ))}
    </>
  )
}

export function SkeletonCards({ n = 6, h = 180, className = 'grid cards' }) {
  return (
    <div className={className}>
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="card skel-card"><Skeleton h={h} r={10} /><Skeleton h={14} w="70%" style={{ marginTop: 12 }} /><Skeleton h={12} w="40%" style={{ marginTop: 8 }} /></div>
      ))}
    </div>
  )
}

function useEscape(open, onClose) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [open, onClose])
}

/** Focus the first focusable element in the panel when it opens; restore on close. */
function useFocusTrap(open, ref) {
  useEffect(() => {
    if (!open || !ref.current) return undefined
    const prev = document.activeElement
    const el = ref.current.querySelector('[data-autofocus]') || ref.current.querySelector('input, select, textarea, button:not(.icon-btn)') || ref.current
    el?.focus?.({ preventScroll: true })
    return () => { prev?.focus?.({ preventScroll: true }) }
  }, [open, ref])
}

export function Modal({ open, title, onClose, children, actions, wide, icon }) {
  const ref = useRef(null)
  const id = useId()
  useEscape(open, onClose)
  useFocusTrap(open, ref)
  if (!open) return null
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.() }}>
      <div ref={ref} tabIndex={-1} className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={id}>
        <div className="modal-head">
          {icon && <span className="modal-ico"><Icon name={icon} size={18} /></span>}
          <h3 id={id}>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </div>
        <div className="modal-body">{children}</div>
        {actions && <div className="modal-foot">{actions}</div>}
      </div>
    </div>
  )
}

export function Drawer({ open, title, sub, onClose, children, footer, width = 560 }) {
  const ref = useRef(null)
  const id = useId()
  useEscape(open, onClose)
  useFocusTrap(open, ref)
  if (!open) return null
  return (
    <div className="overlay drawer-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.() }}>
      <aside ref={ref} tabIndex={-1} className="drawer" style={{ '--drawer-w': `${width}px` }} role="dialog" aria-modal="true" aria-labelledby={id}>
        <div className="drawer-head">
          <div className="drawer-title">
            <h3 id={id}>{title}</h3>
            {sub && <div className="drawer-sub">{sub}</div>}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </div>
        <div className="drawer-body">{children}</div>
        {footer && <div className="drawer-foot">{footer}</div>}
      </aside>
    </div>
  )
}

export function Toggle({ checked, onChange, label, hint, disabled }) {
  return (
    <label className={`toggle ${disabled ? 'disabled' : ''}`}>
      <input type="checkbox" role="switch" checked={!!checked} disabled={disabled} onChange={(e) => onChange?.(e.target.checked)} />
      <span className="track"><span className="thumb" /></span>
      {(label || hint) && (
        <span className="toggle-text">
          {label && <b>{label}</b>}
          {hint && <small>{hint}</small>}
        </span>
      )}
    </label>
  )
}

/** Segmented control. options: [[value, label, icon?]] */
export function Seg({ value, options, onChange, size, label }) {
  return (
    <div className={`seg ${size || ''}`} role="radiogroup" aria-label={label}>
      {options.map(([v, l, ic]) => (
        <button type="button" key={String(v)} className={value === v ? 'on' : ''} onClick={() => onChange(v)} role="radio" aria-checked={value === v}>
          {ic && <Icon name={ic} size={15} />}{l}
        </button>
      ))}
    </div>
  )
}

export function Field({ label, hint, children, counter, className = '' }) {
  return (
    <label className={`field ${className}`}>
      {(label || counter) && <span className="field-label"><span>{label}</span>{counter}</span>}
      {children}
      {hint && <small className="hint">{hint}</small>}
    </label>
  )
}

/** Multi-select chips. options: [{value, label}] */
export function ChipSelect({ options, value = [], onChange, max }) {
  const set = new Set(value)
  return (
    <div className="chips">
      {options.map((o) => {
        const on = set.has(o.value)
        return (
          <button type="button" key={o.value} className={`chip ${on ? 'on' : ''}`} aria-pressed={on}
            onClick={() => {
              if (on) onChange(value.filter((v) => v !== o.value))
              else if (!max || value.length < max) onChange([...value, o.value])
            }}>
            {on && <Icon name="check" size={13} strokeWidth={2.4} />}{o.label}
          </button>
        )
      })}
    </div>
  )
}

export function TagInput({ value = [], onChange, placeholder = 'Type a tag and press Enter' }) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const parts = draft.split(',').map((t) => t.trim()).filter(Boolean)
    if (parts.length) onChange([...new Set([...value, ...parts])])
    setDraft('')
  }
  return (
    <div className="tag-input">
      {value.map((t) => (
        <span className="tag" key={t}>{t}
          <button type="button" onClick={() => onChange(value.filter((x) => x !== t))} aria-label={`Remove ${t}`}><Icon name="x" size={12} /></button>
        </span>
      ))}
      <input value={draft} placeholder={value.length ? '' : placeholder} onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add() }
          else if (e.key === 'Backspace' && !draft && value.length) onChange(value.slice(0, -1))
        }} onBlur={add} />
    </div>
  )
}

/** Tabs. tabs: [[id, label, badge?, icon?]] */
export function Tabs({ tabs, value, onChange, className = '' }) {
  const refs = useRef([])
  const onKey = (e, i) => {
    const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    if (!d) return
    e.preventDefault()
    const j = (i + d + tabs.length) % tabs.length
    onChange(tabs[j][0]); refs.current[j]?.focus()
  }
  return (
    <div className={`tabs ${className}`} role="tablist">
      {tabs.map(([id, label, badge, icon], i) => (
        <button key={id} ref={(el) => { refs.current[i] = el }} role="tab" aria-selected={value === id} tabIndex={value === id ? 0 : -1}
          className={value === id ? 'on' : ''} onClick={() => onChange(id)} onKeyDown={(e) => onKey(e, i)}>
          {icon && <Icon name={icon} size={15} />}
          <span>{label}</span>
          {badge != null && badge !== false && <span className="tab-badge">{badge}</span>}
        </button>
      ))}
    </div>
  )
}

export function Empty({ icon = 'sparkles', emoji, title, children, action, compact }) {
  return (
    <div className={`empty ${compact ? 'compact' : ''}`}>
      <div className="empty-art" aria-hidden="true">{emoji ? <span className="empty-emoji">{emoji}</span> : <Icon name={icon} size={26} />}</div>
      {title && <h4>{title}</h4>}
      {children && <p>{children}</p>}
      {action && <div className="empty-action">{action}</div>}
    </div>
  )
}

export function PageHead({ title, sub, children, eyebrow, icon }) {
  return (
    <header className="page-head">
      <div className="page-head-text">
        {eyebrow && <div className="eyebrow">{icon && <Icon name={icon} size={14} />}{eyebrow}</div>}
        <h1>{title}</h1>
        {sub && <p className="sub">{sub}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  )
}

export function Stat({ label, value, icon, tone = 'brand', sub, to }) {
  return (
    <div className={`stat t-${tone}`}>
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        {icon && <span className="stat-ico"><Icon name={icon} size={16} /></span>}
      </div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
      {to}
    </div>
  )
}

export function SectionTitle({ title, sub, children, icon }) {
  return (
    <div className="section-title">
      <div>
        <h2>{icon && <Icon name={icon} size={18} />}{title}</h2>
        {sub && <p className="muted small">{sub}</p>}
      </div>
      {children && <div className="row">{children}</div>}
    </div>
  )
}

/** <img> that swaps to a fallback node when it fails to load. */
export function SafeImg({ src, alt = '', fallback = null, className, ...rest }) {
  const [bad, setBad] = useState(false)
  useEffect(() => { setBad(false) }, [src])
  if (!src || bad) return fallback
  return <img src={src} alt={alt} className={className} loading="lazy" decoding="async" onError={() => setBad(true)} {...rest} />
}

/* ------------------------------------------------------------ formatting */
export const fmtNum = (n) => {
  if (n == null || Number.isNaN(Number(n))) return '—'
  n = Number(n)
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M'
  if (n >= 1e4) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'K'
  return n.toLocaleString()
}

export const fmtUsd = (n) => {
  if (n == null || Number.isNaN(Number(n))) return '—'
  n = Number(n)
  if (n === 0) return '$0'
  return n < 10 ? `$${n.toFixed(2)}` : `$${Math.round(n).toLocaleString()}`
}

export function fmtDur(sec) {
  if (sec == null || Number.isNaN(Number(sec))) return '—'
  sec = Math.max(0, Math.round(Number(sec)))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`
}

export function fmtDate(iso, opts) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString(undefined, opts || { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

export function ago(iso) {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return String(iso)
  const s = (Date.now() - t) / 1000
  if (s < 0) return 'in ' + until(iso)
  if (s < 45) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  if (s < 86400 * 30) return `${Math.floor(s / 86400)}d ago`
  return fmtDate(iso, { month: 'short', day: 'numeric', year: 'numeric' })
}

export function until(iso) {
  const s = (new Date(iso).getTime() - Date.now()) / 1000
  if (s <= 0) return 'now'
  if (s < 3600) return `${Math.ceil(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`
}

/** ISO → value for <input type="datetime-local"> in local time */
export function toLocalInput(iso) {
  const d = iso ? new Date(iso) : new Date()
  if (Number.isNaN(d.getTime())) return ''
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

export const titleCase = (s) => String(s || '').replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

/* --------------------------------------------------------- error boundary */
export class ErrorBoundary extends Component {
  constructor(p) { super(p); this.state = { err: null } }
  static getDerivedStateFromError(err) { return { err } }
  componentDidUpdate(prev) { if (prev.resetKey !== this.props.resetKey && this.state.err) this.setState({ err: null }) }
  render() {
    if (this.state.err) {
      return (
        <div className="page">
          <Empty icon="alert" title="This page tripped over something"
            action={<button className="btn" onClick={() => this.setState({ err: null })}><Icon name="refresh" size={16} />Try again</button>}>
            {String(this.state.err.message || this.state.err)}
          </Empty>
        </div>
      )
    }
    return this.props.children
  }
}
