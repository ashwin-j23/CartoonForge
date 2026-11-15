import { useEffect, useMemo, useState } from 'react'
import { api, styleImg } from '../api'
import Icon from './icons'
import { Badge, fmtUsd, SafeImg, Skeleton, Spinner, useStatic } from './ui'

/* ------------------------------------------------------------- art styles */
export const AUTO_STYLE = {
  id: 'auto', label: 'Auto', auto: true,
  note: 'Tests looks that suit each age band on real viewers and keeps whatever holds children best.',
  best_for: 'Every age band',
}

const BAND_AGES = { toddler: '1-3', preschool: '3-5', early: '5-8', big: '8-12' }
function bestForFromBands(bands) {
  if (!Array.isArray(bands) || !bands.length) return ''
  const nums = bands.flatMap((b) => (BAND_AGES[b] || '').split('-').map(Number)).filter((n) => !Number.isNaN(n) && n)
  return nums.length ? `Ages ${Math.min(...nums)}-${Math.max(...nums)}` : bands.join(', ')
}

/** Art styles from GET /api/styles, falling back to /api/psychology → styles on older backends. */
export function useStyles() {
  const { data, error } = useStatic('/styles', { quiet: true })
  const psych = useStatic(error ? '/psychology' : null, { quiet: true })
  return useMemo(() => {
    let list = null
    if (Array.isArray(data)) list = data
    else if (data && typeof data === 'object' && !Array.isArray(data)) list = Object.entries(data).map(([id, s]) => ({ id, ...s }))
    else if (psych.data?.styles) list = Object.entries(psych.data.styles).map(([id, s]) => ({ id, ...s }))
    const styles = list?.map((s) => ({
      ...s,
      label: s.label || s.id,
      preview_url: s.preview_url || styleImg(s.id),
      best_for: s.best_for || bestForFromBands(s.bands),
    })) || null
    return { styles, loading: !styles && !(error && psych.error), map: Object.fromEntries((styles || []).map((s) => [s.id, s])) }
  }, [data, error, psych.data, psych.error])
}

export function StyleThumb({ style, className = '' }) {
  if (!style || style.auto || style.id === 'auto') {
    return (
      <div className={`style-thumb auto ${className}`} aria-hidden="true">
        <div className="auto-mosaic"><i /><i /><i /><i /></div>
        <span className="auto-ico"><Icon name="sparkles" size={26} /></span>
      </div>
    )
  }
  return (
    <div className={`style-thumb ${className}`}>
      <SafeImg src={style.preview_url || styleImg(style.id)} alt={`${style.label} sample frame`}
        fallback={<div className="style-ph"><Icon name="image" size={24} /></div>} />
    </div>
  )
}

/**
 * Big visual art-style picker.
 * props: value, onChange, band (age band id to flag suitable looks), defaultId (channel default), includeAuto, compact
 */
export function StylePicker({ value, onChange, band, defaultId, includeAuto = true, compact = false }) {
  const { styles, loading } = useStyles()
  if (loading) {
    return <div className={`style-grid ${compact ? 'compact' : ''}`}>{Array.from({ length: compact ? 6 : 8 }).map((_, i) => <Skeleton key={i} h={compact ? 150 : 230} r={14} />)}</div>
  }
  if (!styles?.length && !includeAuto) return <p className="muted">No art styles available.</p>
  const all = [...(includeAuto ? [AUTO_STYLE] : []), ...(styles || [])]
  return (
    <div className={`style-grid ${compact ? 'compact' : ''}`} role="radiogroup" aria-label="Art style">
      {all.map((s) => {
        const on = (value || 'auto') === s.id
        const fits = !band || s.auto || !Array.isArray(s.bands) || s.bands.includes(band)
        return (
          <button type="button" key={s.id} role="radio" aria-checked={on} onClick={() => onChange(s.id)}
            className={`style-card ${on ? 'on' : ''} ${fits ? '' : 'unfit'}`}>
            <StyleThumb style={s} />
            <span className="style-check" aria-hidden="true"><Icon name="check" size={14} strokeWidth={2.6} /></span>
            <span className="style-info">
              <span className="style-name">
                <b>{s.label}</b>
                {defaultId && defaultId === s.id && <Badge tone="brand" size="sm">Channel default</Badge>}
              </span>
              {!compact && s.note && <span className="style-note">{s.note}</span>}
              <span className="style-meta">
                {s.best_for && <span>{s.best_for}</span>}
                {s.stepped && <span title="Animated on twos, like real stop-motion">Stop-motion</span>}
                {!fits && <span className="warn-text">Not tuned for this age</span>}
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}

export function StyleBadge({ id, rendered, map, size }) {
  if (!id && !rendered) return null
  const name = (x) => map?.[x]?.label || x
  const label = (!id || id === 'auto') ? (rendered ? `Auto · ${name(rendered)}` : 'Auto look') : name(id)
  return <Badge tone="pink" icon="palette" size={size} title="Art style">{label}</Badge>
}

/* --------------------------------------------------------- AI animation */
export const ANIMATION_MODES = [
  { id: 'code', label: 'Code animation', icon: 'code', tone: 'green',
    note: 'The CartoonForge renderer only. Free, with exact lip-sync and counting.', cost: 'Free' },
  { id: 'hero', label: 'AI hero shots', icon: 'sparkles', tone: 'violet',
    note: 'The code render plus 4–8 AI-animated hero shots: the opening tease, story climaxes and the song start.', cost: '≈ $1–5 / episode' },
  { id: 'full', label: 'Full AI animation', icon: 'wand', tone: 'pink',
    note: 'Every shot re-animated by the AI video model from the code frame, so characters stay on model. Voices and music stay ours; a budget cap stops spending.', cost: '≈ $25–300 / episode' },
]
export const MODE_MAP = Object.fromEntries(ANIMATION_MODES.map((m) => [m.id, m]))

export function AnimationBadge({ mode, size }) {
  if (!mode) return null
  const m = MODE_MAP[mode] || { label: mode, icon: 'film', tone: 'neutral' }
  return <Badge tone={m.tone} icon={m.icon} size={size}>{m.label}</Badge>
}

/** GET /api/aivideo (optional endpoint). */
export function useAIVideo() {
  const { data, error } = useStatic('/aivideo', { quiet: true })
  return { info: data, error, unavailable: !!error }
}

/** Live cost estimate from /api/aivideo/estimate (debounced). */
export function useEstimate(mode, minutes, provider) {
  const [st, setSt] = useState({ data: null, loading: false, error: null })
  useEffect(() => {
    if (!mode) return undefined
    if (mode === 'code') { setSt({ data: { usd: 0, clips: 0, seconds: 0 }, loading: false, error: null }); return undefined }
    let alive = true
    setSt((s) => ({ ...s, loading: true }))
    const q = new URLSearchParams({ mode, minutes: String(minutes || 12) })
    if (provider && provider !== 'auto') q.set('provider', provider)
    const h = setTimeout(() => {
      api(`/aivideo/estimate?${q}`).then(
        (d) => { if (alive) setSt({ data: d, loading: false, error: null }) },
        (e) => { if (alive) setSt({ data: null, loading: false, error: e }) },
      )
    }, 250)
    return () => { alive = false; clearTimeout(h) }
  }, [mode, minutes, provider])
  return st
}

export function AnimationPicker({ value, onChange, info, compact }) {
  const modes = ANIMATION_MODES.map((m) => {
    const srv = info?.modes?.find?.((x) => x.id === m.id)
    return { ...m, label: srv?.label || m.label, note: srv?.note || m.note, est: info?.estimate?.[m.id] }
  })
  return (
    <div className={`mode-grid ${compact ? 'compact' : ''}`} role="radiogroup" aria-label="Animation mode">
      {modes.map((m) => {
        const on = value === m.id
        return (
          <button type="button" key={m.id} role="radio" aria-checked={on} className={`mode-card t-${m.tone} ${on ? 'on' : ''}`} onClick={() => onChange(m.id)}>
            <span className="mode-top">
              <span className="mode-ico"><Icon name={m.icon} size={20} /></span>
              <span className="mode-cost">{m.est != null ? (m.id === 'code' ? 'Free' : `≈ ${fmtUsd(m.est)}`) : m.cost}</span>
            </span>
            <b className="mode-name">{m.label}</b>
            {!compact && <span className="mode-note">{m.note}</span>}
          </button>
        )
      })}
    </div>
  )
}

export function EstimateBox({ mode, minutes, provider, info, budget }) {
  const { data, loading, error } = useEstimate(mode, minutes, provider)
  const active = info?.providers?.find?.((p) => p.id === (provider && provider !== 'auto' ? provider : info?.active))
  const noProvider = info && !info.active && mode !== 'code'
  const capped = budget != null && data?.usd != null && Number(budget) > 0 && data.usd > Number(budget)
  return (
    <div className={`estimate ${mode === 'code' ? 'free' : ''}`}>
      <div className="estimate-main">
        <span className="estimate-label">Estimated AI video cost</span>
        <span className="estimate-value">
          {loading ? <Spinner size={18} /> : mode === 'code' ? '$0.00' : data?.usd != null ? fmtUsd(data.usd) : '—'}
        </span>
      </div>
      <div className="estimate-meta">
        {mode === 'code' && <span>Rendered by CartoonForge only — no AI video spend.</span>}
        {mode !== 'code' && data && <span>{data.clips ?? '?'} clips · {data.seconds ?? '?'} s of AI video{active ? ` · ${active.label}` : ''}</span>}
        {mode !== 'code' && error && <span>Live estimate unavailable ({error.status === 404 ? 'endpoint not deployed yet' : error.message}).</span>}
        {capped && <span className="warn-text">Above your budget cap of {fmtUsd(budget)} — remaining shots fall back to code animation.</span>}
        {noProvider && <span className="warn-text"><Icon name="alert" size={13} /> No AI video provider is configured — add a key in Settings → Keys.</span>}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ colour palettes (render/palette.py)
   Research-based: Filmora's kids palettes + The Straits Times' palettes measured on real kids' shows. */
export const AUTO_PALETTE = { id: 'auto', name: 'Auto', group: 'auto', mood: 'Picked per episode from its topic and the viewers’ age', colors: ['#ff595e', '#ffca3a', '#8ac926', '#1982c4', '#bdb2ff'] }
export const PALETTE_GROUPS = [['playful', 'Playful'], ['pastel', 'Pastel'], ['bold', 'Bold'], ['educational', 'Educational'], ['measured', 'Measured on real shows']]

export function usePalettes() {
  const { data, error } = useStatic('/palettes', { quiet: true })
  const list = data?.palettes || []
  const map = Object.fromEntries(list.map((p) => [p.id, p]))
  return { data, list, map, loading: !data && !error }
}

export function Swatches({ colors = [], size = 'md', title }) {
  return (
    <span className={`swatches ${size}`} title={title}>
      {colors.map((c, i) => <span key={`${c}-${i}`} style={{ background: c }} />)}
    </span>
  )
}

export function PaletteBadge({ id, rendered, map }) {
  const p = map?.[rendered || id] || (id === 'auto' ? AUTO_PALETTE : null)
  if (!p) return null
  const label = id === 'auto' && rendered && map?.[rendered] ? `Auto · ${map[rendered].name}` : p.name
  return <span className="badge t-neutral palette-badge" title={p.mood}><Swatches colors={p.colors.slice(0, 5)} size="xs" />{label}</span>
}

export function PalettePicker({ value, onChange, list = [], includeAuto = true }) {
  const all = includeAuto ? [AUTO_PALETTE, ...list] : list
  return (
    <div className="palette-pick" role="radiogroup" aria-label="Colour palette">
      {all.map((p) => (
        <button type="button" key={p.id} role="radio" aria-checked={value === p.id} className={`palette-opt ${value === p.id ? 'on' : ''}`}
          onClick={() => onChange(p.id)} title={p.mood}>
          <Swatches colors={p.colors.slice(0, 6)} size="sm" />
          <span className="palette-opt-name">{p.name}</span>
        </button>
      ))}
    </div>
  )
}
