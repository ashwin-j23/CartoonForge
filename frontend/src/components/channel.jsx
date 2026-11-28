import { useEffect, useState } from 'react'
import Icon from './icons'

/**
 * Two YouTube channels, one studio: the English channel (Hoppy Hop Hop) and the dubbed one (Hoppy Hop Hop World).
 * Every list, card and calendar entry carries `channel` ('en' | 'world'); the switch in the sidebar filters all pages.
 */
export const CHANNELS = {
  en: { label: 'Hoppy Hop Hop', short: 'English', emoji: '🐸', tone: 'en' },
  world: { label: 'Hoppy Hop Hop World', short: 'World', emoji: '🌍', tone: 'world' },
}
const KEY = 'cf.channel'
const EVT = 'cf:channel'

const read = () => {
  try { const v = localStorage.getItem(KEY); return v === 'en' || v === 'world' ? v : 'all' } catch { return 'all' }
}

/** The channel filter shared by every page ('all' | 'en' | 'world'), remembered on this device. */
export function useChannel() {
  const [ch, setCh] = useState(read)
  useEffect(() => {
    const on = () => setCh(read())
    window.addEventListener(EVT, on)
    window.addEventListener('storage', on)
    return () => { window.removeEventListener(EVT, on); window.removeEventListener('storage', on) }
  }, [])
  const set = (v) => {
    try { localStorage.setItem(KEY, v) } catch { /* private mode: this page only */ }
    setCh(v)
    window.dispatchEvent(new Event(EVT))
  }
  return [ch, set]
}

export const chOf = (it) => (it?.channel === 'world' || it?.kind === 'dub' ? 'world' : 'en')
export const inChannel = (it, ch) => ch === 'all' || chOf(it) === ch
/** Where a row opens: a dub opens its English episode, on the dub's language. */
export const itemLink = (it) => (chOf(it) === 'world' ? `/episodes/${it.episode_id}?dub=${it.lang}` : `/episodes/${it.id}`)

export function ChannelSwitch({ compact }) {
  const [ch, set] = useChannel()
  const opts = [['all', 'All', null], ['en', compact ? 'English' : CHANNELS.en.label, CHANNELS.en.emoji], ['world', compact ? 'World' : CHANNELS.world.label, CHANNELS.world.emoji]]
  return (
    <div className={`ch-switch ${compact ? 'compact' : ''}`} role="radiogroup" aria-label="Which YouTube channel">
      {!compact && <span className="ch-switch-label">Channel</span>}
      {opts.map(([v, l, e]) => (
        <button key={v} type="button" role="radio" aria-checked={ch === v} className={`ch-opt ${v} ${ch === v ? 'on' : ''}`} onClick={() => set(v)}>
          {e ? <span aria-hidden="true">{e}</span> : <Icon name="layers" size={14} />}<span>{l}</span>
        </button>
      ))}
    </div>
  )
}

/** Which channel a video is on: green 🐸 EN or purple 🌍 + language code. */
export function ChannelBadge({ it, size, full }) {
  const w = chOf(it) === 'world'
  const c = CHANNELS[w ? 'world' : 'en']
  const lang = w ? (it.lang ? it.lang.toUpperCase().slice(0, 2) : 'All languages') : 'EN'
  return (
    <span className={`ch-badge ${c.tone} ${size || ''}`} title={`${c.label}${w && it.lang_name ? ` · ${it.lang_name}` : ''}`}>
      <span aria-hidden="true">{c.emoji}</span>{full ? `${c.label} · ` : ''}{w ? (full && it.lang_native ? it.lang_native : lang) : (full ? 'English' : lang)}
    </span>
  )
}
