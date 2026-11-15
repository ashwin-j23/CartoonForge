import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { get, put } from '../api'
import Icon from '../components/icons'
import { AnimationPicker, EstimateBox, StylePicker, useAIVideo } from '../components/looks'
import {
  ago, Badge, ChipSelect, Empty, Field, fmtUsd, PageHead, Seg, Skeleton, Spinner, Toggle, useAction, useApi, useStatic, useToast,
} from '../components/ui'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const KEY_GROUPS = [
  ['AI writers', 'bot', 'Any one is enough; more providers = more resilience when one is rate-limited.',
    ['GEMINI_API_KEY', 'GROQ_API_KEY', 'NVIDIA_API_KEY', 'CEREBRAS_API_KEY', 'OPENROUTER_API_KEY', 'MISTRAL_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY']],
  ['AI video', 'sparkles', 'Google Veo uses GEMINI_API_KEY (above). Kling runs through fal.ai; Runway uses its own key. Only needed for AI hero shots or full AI animation.', ['FAL_KEY', 'RUNWAY_API_KEY']],
  ['Voice', 'mic', 'Optional premium voices. Without it the studio uses free neural voices.', ['ELEVENLABS_API_KEY']],
  ['YouTube', 'tv', 'OAuth client from Google Cloud Console. The refresh token is filled in by Channel → Connect.', ['YT_CLIENT_ID', 'YT_CLIENT_SECRET', 'YT_REFRESH_TOKEN']],
  ['Trends', 'trending', 'A plain YouTube Data API key (Google Cloud → Credentials → API key). Lets the trend scan see this week’s hottest kids videos.', ['YOUTUBE_API_KEY']],
]
const SECTIONS = [
  ['channel', 'Channel', 'tv'], ['schedule', 'Schedule', 'calendar'], ['episodes', 'Episodes', 'film'], ['looks', 'Look & animation', 'palette'],
  ['growth', 'Growth', 'rocket'], ['voice', 'Voice & sound', 'mic'], ['quality', 'Quality & safety', 'shield'], ['ai', 'AI providers', 'bot'],
  ['keys', 'Keys', 'key'], ['deploy', 'Deploy', 'cloud'],
]

const tzList = (() => { try { return Intl.supportedValuesOf('timeZone') } catch { return [] } })()
const rateNum = (r) => { const m = /^([+-]?\d+(?:\.\d+)?)%?$/.exec(String(r ?? '').trim()); return m ? Number(m[1]) : 0 }
const rateStr = (n) => `${n >= 0 ? '+' : ''}${n}%`

function Section({ id, title, icon, desc, children, aside }) {
  return (
    <section className="card set-section" id={`set-${id}`}>
      <div className="set-head">
        <div>
          <h2>{icon && <Icon name={icon} size={18} />}{title}</h2>
          {desc && <p className="muted small">{desc}</p>}
        </div>
        {aside}
      </div>
      <div className="set-grid">{children}</div>
    </section>
  )
}

function Keys() {
  const { data, setData } = useApi('/keys')
  const [vals, setVals] = useState({})
  const [busy, run] = useAction()
  const known = new Set(KEY_GROUPS.flatMap((g) => g[3]))
  const extra = Object.keys(data || {}).filter((k) => !known.has(k))
  const groups = extra.length ? [...KEY_GROUPS, ['Other', 'key', '', extra]] : KEY_GROUPS
  const save = async (body, msg) => {
    const r = await run('keys', () => put('/keys', body), msg)
    if (r !== undefined) {
      setVals((v) => { const n = { ...v }; Object.keys(body).forEach((k) => delete n[k]); return n })
      if (r && typeof r === 'object' && !Array.isArray(r) && Object.values(r)[0]?.set !== undefined) setData(r)
      else setData(await get('/keys').catch(() => data))
    }
  }
  const pending = Object.fromEntries(Object.entries(vals).filter(([, v]) => v.trim()))
  const n = Object.keys(pending).length
  return (
    <Section id="keys" title="Keys" icon="key" desc="Stored encrypted on the server. Values are never shown again — only a short preview. Leave a field empty to keep what’s saved."
      aside={<button className="btn primary" disabled={!n || !!busy} onClick={() => save(pending, 'Keys saved')}>{busy ? <Spinner /> : <Icon name="save" size={15} />}Save {n || ''} key{n === 1 ? '' : 's'}</button>}>
      {!data ? <div className="wide"><Skeleton h={36} count={5} style={{ marginBottom: 8 }} /></div> : groups.map(([title, icon, desc, keys]) => (
        <div className="key-group wide" key={title}>
          <h4><Icon name={icon} size={15} />{title}</h4>
          {desc && <p className="muted small">{desc}</p>}
          {keys.map((k) => {
            const info = data[k] || {}
            return (
              <div className="key-row" key={k}>
                <div className="key-name"><code>{k}</code>
                  {info.set ? <Badge tone="green" size="sm" icon="check">{info.preview || 'set'}{info.source ? ` · ${info.source}` : ''}</Badge> : <Badge size="sm">not set</Badge>}
                </div>
                <input type="password" autoComplete="new-password" placeholder={info.set ? 'Enter a new value to replace' : 'Paste key'} value={vals[k] || ''}
                  onChange={(e) => setVals({ ...vals, [k]: e.target.value })} aria-label={k} />
                {info.set && info.source !== 'env' ? (
                  <button className="btn ghost sm" disabled={!!busy} onClick={() => save({ [k]: '' }, `${k} removed`)} title="Remove saved key">Remove</button>
                ) : <span />}
              </div>
            )
          })}
        </div>
      ))}
    </Section>
  )
}

function Providers({ order, onChange }) {
  const { data: llm, reload } = useApi('/llm', { ms: 20000 })
  const names = useMemo(() => {
    const all = (llm || []).map((p) => p.name)
    const base = (order || []).filter(Boolean)
    return [...base, ...all.filter((n) => !base.includes(n))]
  }, [order, llm])
  const info = Object.fromEntries((llm || []).map((p) => [p.name, p]))
  const move = (i, d) => { const n = [...names]; const j = i + d; if (j < 0 || j >= n.length) return; [n[i], n[j]] = [n[j], n[i]]; onChange(n) }
  return (
    <Section id="ai" title="AI providers" icon="bot" desc="The writer tries providers in this order and falls back on errors or rate limits. Unconfigured providers are skipped."
      aside={<button className="btn ghost sm" onClick={() => reload()}><Icon name="refresh" size={14} />Refresh</button>}>
      <div className="wide scroll-x">
        <table className="table providers">
          <thead><tr><th>Order</th><th>Provider</th><th>Model</th><th>Status</th><th className="num">OK / Fail</th><th>Last error</th></tr></thead>
          <tbody>
            {names.map((n, i) => {
              const p = info[n] || { name: n }
              const cooling = p.cooldown_until && new Date(p.cooldown_until) > new Date()
              return (
                <tr key={n} className={p.configured === false ? 'dim' : ''}>
                  <td className="order">
                    <button className="icon-btn sm" onClick={() => move(i, -1)} disabled={i === 0} aria-label={`Move ${n} up`}><Icon name="arrowUp" size={14} /></button>
                    <span>{i + 1}</span>
                    <button className="icon-btn sm" onClick={() => move(i, 1)} disabled={i === names.length - 1} aria-label={`Move ${n} down`}><Icon name="arrowDown" size={14} /></button>
                  </td>
                  <td><b>{p.label || n}</b></td>
                  <td className="mono small">{p.model || '—'}</td>
                  <td>{p.configured === false ? <Badge size="sm">no key</Badge> : cooling ? <Badge size="sm" tone="amber" title={p.cooldown_until}>cooling {ago(p.cooldown_until)}</Badge> : <Badge size="sm" tone="green" dot>ready</Badge>}</td>
                  <td className="num">{p.ok ?? 0} / {p.fail ?? 0}</td>
                  <td className="muted tiny clamp2" title={p.last_error || ''}>{p.last_error || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

function Deploy() {
  const { data, error, loading, reload } = useApi('/deploy', { quiet: true })
  const list = data?.checklist || []
  const done = list.filter((c) => c.done).length
  return (
    <Section id="deploy" title="Deploy" icon="cloud" desc="Where the studio runs and what’s left to set up."
      aside={data && <button className="btn ghost sm" onClick={() => reload()}><Icon name="refresh" size={14} />Re-check</button>}>
      <div className="wide">
        {loading && !data ? <Skeleton h={40} count={3} style={{ marginBottom: 8 }} /> : error ? (
          <Empty compact icon="cloud" title={error.status === 404 ? 'Deploy info isn’t available yet' : 'Couldn’t load deploy info'}>
            {error.status === 404 ? 'This server doesn’t expose /api/deploy yet — it appears after the backend update.' : error.message}
          </Empty>
        ) : (
          <>
            <div className="kv-row">
              <div><span>Target</span><b>{data.target || '—'}</b></div>
              <div><span>Database</span><b>{data.db || '—'}</b></div>
              <div><span>Worker</span><b>{data.worker || '—'}</b></div>
              <div><span>Checklist</span><b>{done}/{list.length}</b></div>
            </div>
            {list.length > 0 && (
              <ul className="checklist">
                {list.map((c, i) => (
                  <li key={i} className={c.done ? 'done' : ''}>
                    <span className="tick" aria-label={c.done ? 'done' : 'to do'}>{c.done && <Icon name="check" size={13} strokeWidth={2.6} />}</span>
                    <div><b>{c.title}</b>{c.detail && <p className="muted small">{c.detail}</p>}</div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </Section>
  )
}

export default function Settings() {
  const toast = useToast()
  const { data: saved, setData: setSaved, loading } = useApi('/settings')
  const cats = useStatic('/categories')
  const psych = useStatic('/psychology')
  const langs = useStatic('/languages')
  const voices = useStatic('/voices')
  const { info: ai } = useAIVideo()
  const [d, setD] = useState(null)
  const [busy, run] = useAction()
  const [active, setActive] = useState('channel')
  useEffect(() => { if (saved) setD(structuredClone(saved)) }, [saved])

  useEffect(() => {
    if (!d) return undefined
    const els = SECTIONS.map(([id]) => document.getElementById(`set-${id}`)).filter(Boolean)
    const io = new IntersectionObserver((entries) => {
      const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
      if (vis) setActive(vis.target.id.replace('set-', ''))
    }, { rootMargin: '-15% 0px -70% 0px' })
    els.forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [!!d]) // eslint-disable-line react-hooks/exhaustive-deps

  const changed = useMemo(() => {
    if (!d || !saved) return {}
    const out = {}
    for (const k of Object.keys(d)) if (JSON.stringify(d[k]) !== JSON.stringify(saved[k])) out[k] = d[k]
    return out
  }, [d, saved])
  const dirty = Object.keys(changed).length > 0

  if (loading && !saved) return <div className="page"><Skeleton h={40} w={260} /><Skeleton h={200} r={14} count={3} style={{ marginTop: 16 }} /></div>
  if (!d) return <div className="page"><Empty icon="settings" title="Settings unavailable">The server didn’t return settings.</Empty></div>

  const set = (k) => (v) => setD((x) => ({ ...x, [k]: v }))
  const ev = (k, fn = (x) => x) => (e) => set(k)(fn(e.target.value))
  const save = async () => {
    const r = await run('save', () => put('/settings', changed), 'Settings saved')
    if (r) {
      const dropped = Object.keys(changed).filter((k) => !(k in r))
      setSaved(r)
      if (dropped.length) {
        toast(`The server didn’t accept: ${dropped.join(', ')} (needs the backend update).`, 'info')
        setD({ ...structuredClone(r) })
      }
    }
  }
  const kill = async (on) => {
    const r = await run('kill', () => put('/settings', { kill_switch: on }), on ? 'Kill switch ON — the studio is paused' : 'Kill switch off — the studio is running')
    if (r) setSaved(r)
  }
  const bands = Object.entries(psych?.bands || {})
  const mix = d.category_mix || {}
  const go = (id) => { setActive(id); document.getElementById(`set-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  const providers = ai?.providers || []

  return (
    <div className="page settings">
      <PageHead title="Settings" sub="How the studio plans, writes, renders and publishes." />

      <section className={`kill ${saved.kill_switch ? 'on' : ''}`}>
        <span className="kill-ico"><Icon name="power" size={22} /></span>
        <div className="kill-text">
          <h2>{saved.kill_switch ? 'Kill switch is ON — everything is paused' : 'Studio is running'}</h2>
          <p>{saved.kill_switch ? 'No writing, rendering or publishing will happen until you turn it off.' : 'Flip this to immediately stop all generation and publishing (e.g. if something looks wrong).'}</p>
        </div>
        <button className={`btn ${saved.kill_switch ? 'primary' : 'danger'}`} disabled={busy === 'kill'} onClick={() => kill(!saved.kill_switch)}>
          {busy === 'kill' ? <Spinner /> : <Icon name={saved.kill_switch ? 'play' : 'power'} size={15} />}{saved.kill_switch ? 'Resume studio' : 'Stop everything'}
        </button>
      </section>

      <div className="set-layout">
        <nav className="set-nav" aria-label="Settings sections">
          {SECTIONS.map(([id, l, icon]) => (
            <a key={id} href={`#set-${id}`} className={active === id ? 'on' : ''} onClick={(e) => { e.preventDefault(); go(id) }}><Icon name={icon} size={15} />{l}</a>
          ))}
        </nav>

        <div className="set-body">
          <Section id="channel" title="Channel" icon="tv">
            <Field label="Channel name"><input value={d.channel_name || ''} onChange={ev('channel_name')} /></Field>
            <Field label="YouTube handle" hint="Used for the subscribe link and hashtag in every description">
              <input value={d.channel_handle || ''} onChange={ev('channel_handle')} placeholder="@HoppyAndFriends" />
            </Field>
            <Field label="Tagline"><input value={d.channel_tagline || ''} onChange={ev('channel_tagline')} placeholder="Little lessons that grow big smiles" /></Field>
            <Field label="Main language">
              <select value={d.language || ''} onChange={ev('language')}>
                {!langs?.some((l) => l.code === d.language) && <option value={d.language}>{d.language}</option>}
                {(langs || []).map((l) => <option key={l.code} value={l.code}>{l.name}{l.native && l.native !== l.name ? ` — ${l.native}` : ''}</option>)}
              </select>
            </Field>
            <Field label="Timezone" hint="Posting times are in this zone">
              <input list="tz-list" value={d.timezone || ''} onChange={ev('timezone')} />
              <datalist id="tz-list">{tzList.map((t) => <option key={t} value={t} />)}</datalist>
            </Field>
          </Section>

          <Section id="schedule" title="Schedule" icon="calendar">
            <div className="wide toggles">
              <Toggle checked={d.autopilot} onChange={set('autopilot')} label="Autopilot" hint="Episodes that clear the quality bar and safety gate are approved and scheduled without waiting for you." />
              <Toggle checked={d.auto_generate} onChange={set('auto_generate')} label="Auto-generate" hint="Keep the pipeline topped up so every posting slot has an episode." />
            </div>
            <Field label={<>Episodes per day <b className="accent">{d.episodes_per_day ?? 3}</b></>} hint="Long episodes a day — one per posting time. Shorts ride along.">
              <input type="range" min={1} max={4} value={d.episodes_per_day ?? 3} onChange={ev('episodes_per_day', Number)} />
            </Field>
            <Field label="Posting times" hint="Local times, comma-separated (breakfast, nap/lunch, after school).">
              <input defaultValue={(d.post_times || []).join(', ')} key={(saved.post_times || []).join(',')} onChange={(e) => set('post_times')(e.target.value.split(',').map((x) => x.trim()).filter((x) => /^\d{1,2}:\d{2}$/.test(x)))} placeholder="07:00, 12:30, 17:30" />
            </Field>
            <div className="field wide">
              <span className="field-label"><span>Posting days</span></span>
              <ChipSelect options={DAYS.map((l, i) => ({ value: i, label: l }))} value={d.post_days || []} onChange={(v) => set('post_days')([...v].sort((a, b) => a - b))} />
            </div>
            <Field label={<>Trend share <b className="accent">{Math.round((d.trend_share ?? 0.6) * 100)}%</b></>} hint="Share of new episodes taken from Trends (the rest keeps the balanced category mix).">
              <input type="range" min={0} max={1} step={0.05} value={d.trend_share ?? 0.6} onChange={ev('trend_share', Number)} />
            </Field>
            <Field label={<>Variety guard <b className="accent">{Math.round((d.variety_max ?? 0.32) * 100)}%</b></>} hint="Rewrite a script if more than this share of its lines repeats a recent episode. YouTube demonetises repetitive channels.">
              <input type="range" min={0.15} max={0.6} step={0.01} value={d.variety_max ?? 0.32} onChange={ev('variety_max', Number)} />
            </Field>
          </Section>

          <Section id="episodes" title="Episodes" icon="film">
            <Field label={<>Target length <b className="accent">{d.target_minutes} min</b></>}>
              <input type="range" min={10} max={15} value={d.target_minutes || 12} onChange={ev('target_minutes', Number)} />
            </Field>
            <div className="field">
              <span className="field-label"><span>Default age band</span></span>
              {bands.length ? <Seg value={d.age_band} onChange={set('age_band')} size="sm" options={bands.map(([id, b]) => [id, b.label || id])} label="Default age band" />
                : <input value={d.age_band || ''} onChange={ev('age_band')} />}
            </div>
            <div className="field wide">
              <span className="field-label"><span>Pace <span className="muted">— how fast the picture moves (cuts, zooms, motion)</span></span></span>
              <div className="option-grid">
                {(Object.keys(psych?.paces || {}).length ? [...Object.entries(psych.paces), ...(psych.paces.auto ? [] : [['auto', {}]])] : [['calm', {}], ['lively', {}], ['rapid', {}], ['auto', {}]]).map(([id, p]) => (
                  <button type="button" key={id} className={`option ${(d.pace || 'auto') === id ? 'on' : ''}`} onClick={() => set('pace')(id)} aria-pressed={(d.pace || 'auto') === id}>
                    <b>{p.label || id}</b>
                    {Array.isArray(p.shot) && <span className="tiny muted">shots {p.shot[0]}–{p.shot[1]} s</span>}
                    <span className="small">{id === 'auto' && !p.note ? 'Let the optimizer learn it from retention.' : p.note}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="wide toggles">
              <Toggle checked={d.optimizer} onChange={set('optimizer')} label="Optimizer" hint="Learn pace, length, thumbnail, title and art style from YouTube retention, and favour what works." />
            </div>
            <Field label={<>Explore rate <b className="accent">{Math.round((d.explore_rate ?? 0) * 100)}%</b></>} hint="Share of episodes that try a non-best option so the optimizer keeps learning.">
              <input type="range" min={0} max={0.5} step={0.01} value={d.explore_rate ?? 0.15} onChange={ev('explore_rate', Number)} disabled={!d.optimizer} />
            </Field>
            <div className="field wide">
              <span className="field-label"><span>Category mix <span className="muted">— how often the planner picks each (0 = never)</span></span></span>
              <div className="mix">
                {(cats || []).map((c) => {
                  const total = Object.values(mix).reduce((a, b) => a + (Number(b) || 0), 0) || 1
                  const w = Number(mix[c.id] ?? 0)
                  return (
                    <div className="mix-row" key={c.id}>
                      <span className="mix-name">{c.emoji} {c.name}</span>
                      <input type="range" min={0} max={5} step={0.5} value={w} onChange={(e) => set('category_mix')({ ...mix, [c.id]: Number(e.target.value) })} aria-label={`${c.name} weight`} />
                      <span className="mix-v">{w} <small className="muted">{Math.round((w / total) * 100)}%</small></span>
                    </div>
                  )
                })}
              </div>
            </div>
          </Section>

          <Section id="looks" title="Look & animation" icon="palette" desc="Defaults for new episodes. Every episode can override these in Create, or be restyled later."
            aside={<Link to="/looks" className="btn ghost sm">Browse looks<Icon name="arrowRight" size={14} /></Link>}>
            <div className="field wide">
              <span className="field-label"><span>Default art style</span></span>
              <StylePicker value={d.art_style || 'auto'} onChange={set('art_style')} compact />
            </div>
            <Field label="3D cartoon quality" hint="Used by the “3D cartoon” look (Blender). On CPU a 12-minute episode takes hours; an NVIDIA GPU is far faster.">
              <select value={d.render_3d_quality || 'standard'} onChange={ev('render_3d_quality')}>
                <option value="draft">Draft — 960×540, 12 fps (fastest)</option>
                <option value="standard">Standard — 1280×720, 12 fps</option>
                <option value="high">High — 1920×1080, 24 fps (GPU recommended)</option>
              </select>
            </Field>
            <Field label="3D render device" hint="Auto uses the GPU when Blender can see one.">
              <select value={d.render_3d_engine || 'auto'} onChange={ev('render_3d_engine')}>
                <option value="auto">Auto</option>
                <option value="cycles">Cycles (path traced)</option>
                <option value="eevee">EEVEE (GPU only, fastest)</option>
              </select>
            </Field>
            <div className="wide toggles">
              <Toggle checked={d.ai_backgrounds} onChange={set('ai_backgrounds')} label="AI-illustrated backgrounds" hint="Each story place painted by an AI image model (Gemini or OpenAI key, a few cents per image). Characters stay code-drawn so they never change." />
            </div>
            <div className="field wide">
              <span className="field-label"><span>Default animation</span></span>
              <AnimationPicker value={d.animation || 'code'} onChange={set('animation')} info={ai} />
            </div>
            <Field label="AI video provider" hint={ai?.recommended ? `Recommended: ${providers.find((p) => p.id === ai.recommended)?.label || ai.recommended}` : 'Auto picks the best configured provider.'}>
              <select value={d.ai_video_provider || 'auto'} onChange={ev('ai_video_provider')}>
                <option value="auto">Auto (best configured)</option>
                {(providers.length ? providers : [{ id: 'veo', label: 'Google Veo' }, { id: 'kling', label: 'Kling (fal.ai)' }, { id: 'runway', label: 'Runway' }]).map((p) => (
                  <option key={p.id} value={p.id}>{p.label}{p.configured === false ? ' — no key' : ''}</option>
                ))}
              </select>
            </Field>
            <Field label="Budget cap per episode (USD)" hint="AI video spending stops here; remaining shots keep the code animation.">
              <div className="input-prefix"><span>$</span><input type="number" min={0} step={1} value={d.ai_video_budget_usd ?? 5} onChange={ev('ai_video_budget_usd', Number)} /></div>
            </Field>
            <Field label={<>Hero shots per episode <b className="accent">{d.ai_video_hero_shots ?? 6}</b></>} hint="Opening tease, story climaxes and the song start. 4–8 works well.">
              <input type="range" min={2} max={12} step={1} value={d.ai_video_hero_shots ?? 6} onChange={ev('ai_video_hero_shots', Number)} />
            </Field>
            <div className="field">
              <span className="field-label"><span>Cost at {d.target_minutes || 12} min</span></span>
              <EstimateBox mode={d.animation || 'code'} minutes={d.target_minutes || 12} provider={d.ai_video_provider} info={ai} budget={d.animation !== 'code' ? d.ai_video_budget_usd : null} />
            </div>
            {providers.length > 0 && (
              <div className="wide scroll-x">
                <table className="table">
                  <thead><tr><th>Provider</th><th>Key</th><th className="num">$/s</th><th>Clip lengths</th><th>Best for</th></tr></thead>
                  <tbody>
                    {providers.map((p) => (
                      <tr key={p.id} className={p.configured ? '' : 'dim'}>
                        <td><b>{p.label}</b>{ai?.recommended === p.id && <> <Badge size="sm" tone="brand">recommended</Badge></>}{ai?.active === p.id && <> <Badge size="sm" tone="green" dot>active</Badge></>}<div className="muted tiny mono">{p.model}</div></td>
                        <td>{p.configured ? <Badge size="sm" tone="green" icon="check">{p.key}</Badge> : <Badge size="sm">{p.key} not set</Badge>}</td>
                        <td className="num mono">{p.usd_per_s != null ? fmtUsd(p.usd_per_s) : '—'}</td>
                        <td className="small">{Array.isArray(p.clip_s) ? (p.clip_s.length === 2 ? `${p.clip_s[0]}–${p.clip_s[1]} s` : `${p.clip_s.join(', ')} s`) : '—'}</td>
                        <td className="small muted">{p.best_for || p.note || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section id="growth" title="Growth" icon="rocket" desc="Grow without pushing kids: grown-ups get one gentle subscribe line; Shorts and compilations do the discovery work.">
            <div className="wide toggles">
              <Toggle checked={d.growth_cta} onChange={set('growth_cta')} label="Grown-up subscribe line" hint="One parent-directed subscribe line at the end of each episode, plus the description and end card. Never aimed at kids." />
            </div>
            <Field label="Subscribe line" hint="Spoken once, at the very end, to grown-ups." className="wide">
              <input value={d.cta_line || ''} onChange={ev('cta_line')} disabled={!d.growth_cta} placeholder="Grown-ups, subscribe for a new adventure every week!" />
            </Field>
            <div className="wide toggles">
              <Toggle checked={d.shorts_from_episodes} onChange={set('shorts_from_episodes')} label="Cut Shorts from episodes" hint="Automatically make a vertical Short from each published episode." />
              <Toggle checked={d.compilation_weekly} onChange={set('compilation_weekly')} label="Weekly compilation" hint="Stitch past episodes into a long-form compilation once a week." />
            </div>
            <Field label={<>Compilation length <b className="accent">{d.compilation_minutes ?? 45} min</b></>}>
              <input type="range" min={20} max={90} step={5} value={d.compilation_minutes ?? 45} onChange={ev('compilation_minutes', Number)} disabled={!d.compilation_weekly} />
            </Field>
            <Field label="Compilation day">
              <select value={d.compilation_weekday ?? 5} onChange={ev('compilation_weekday', Number)} disabled={!d.compilation_weekly}>
                {DAYS.map((l, i) => <option key={i} value={i}>{l}</option>)}
              </select>
            </Field>
          </Section>

          <Section id="voice" title="Voice & sound" icon="mic">
            <Field label={<>Voice speed <b className="accent">{rateStr(rateNum(d.voice_rate))}</b></>} hint="Slower is kinder for little ears; the age band sets the target pace.">
              <input type="range" min={-20} max={10} value={rateNum(d.voice_rate)} onChange={(e) => set('voice_rate')(rateStr(Number(e.target.value)))} />
            </Field>
            <div className="field">
              <span className="field-label"><span>Render quality</span></span>
              <Seg value={Number(d.render_scale) < 0.9 ? 0.667 : 1} onChange={set('render_scale')} size="sm" options={[[1, '1080p · best'], [0.667, '720p · faster']]} label="Render quality" />
            </div>
            <div className="wide toggles">
              <Toggle checked={d.music} onChange={set('music')} label="Background music" hint="Soft, gentle music under the voices." />
              <Toggle checked={d.captions_burned} onChange={set('captions_burned')} label="Burned-in captions" hint="Big, friendly words on screen help early readers." />
            </div>
            <Field label={<>Music level <b className="accent">{Math.round((d.music_level ?? 0) * 100)}%</b></>}>
              <input type="range" min={0} max={0.4} step={0.01} value={d.music_level ?? 0.12} onChange={ev('music_level', Number)} disabled={!d.music} />
            </Field>
            {voices?.length > 0 && (
              <div className="field wide">
                <span className="field-label"><span>Voice library <span className="muted">— assigned per character on the Characters page</span></span></span>
                <details className="voice-lib">
                <summary>Browse {voices.length} voices</summary>
                <div className="voices">
                  {voices.map((v) => (
                    <div className="voice" key={v.id}>
                      <div><b>{v.label}</b><div className="muted tiny">{v.gender} · {v.lang} · <code>{v.id}</code></div></div>
                      {v.sample && <audio controls preload="none" src={v.sample} />}
                    </div>
                  ))}
                </div>
                </details>
              </div>
            )}
          </Section>

          <Section id="quality" title="Quality & safety" icon="shield">
            <Field label="Quality bar" hint="Minimum critic score; below it the writer revises.">
              <input type="number" step="0.5" min={0} value={d.quality_bar ?? ''} onChange={ev('quality_bar', Number)} />
            </Field>
            <Field label="Max revisions" hint="Rewrites before giving up and sending to review.">
              <input type="number" min={0} max={10} value={d.max_revisions ?? ''} onChange={ev('max_revisions', Number)} />
            </Field>
            <Field label="Daily LLM budget" hint="Max LLM calls (or spend, per backend) per day.">
              <input type="number" min={0} step="any" value={d.llm_daily_budget ?? ''} onChange={ev('llm_daily_budget', Number)} />
            </Field>
            <div className="field">
              <span className="field-label"><span>YouTube privacy</span></span>
              <Seg value={d.youtube_privacy} onChange={set('youtube_privacy')} size="sm" label="YouTube privacy" options={[['public', 'Public', 'globe'], ['unlisted', 'Unlisted', 'link'], ['private', 'Private', 'lock']]} />
            </div>
            <div className="wide locked">
              <Toggle checked disabled label="Made for kids (locked)" hint="Required by COPPA and YouTube policy for children’s content — comments and the notification bell are off, which is why the show never asks kids to comment." />
            </div>
          </Section>

          <Providers order={d.provider_order} onChange={set('provider_order')} />
          <Keys />
          <Deploy />
        </div>
      </div>

      {dirty && (
        <div className="save-bar" role="region" aria-label="Unsaved changes">
          <span><Icon name="edit" size={15} /><b>{Object.keys(changed).length} unsaved change{Object.keys(changed).length === 1 ? '' : 's'}</b> <small className="muted">{Object.keys(changed).join(', ')}</small></span>
          <div className="row">
            <button className="btn ghost" onClick={() => setD(structuredClone(saved))}>Discard</button>
            <button className="btn primary" onClick={save} disabled={busy === 'save'}>{busy === 'save' ? <Spinner /> : <Icon name="save" size={15} />}Save settings</button>
          </div>
        </div>
      )}
    </div>
  )
}
