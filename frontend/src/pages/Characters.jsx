import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { castImg, del, get, patch, post } from '../api'
import Icon from '../components/icons'
import { useStyles } from '../components/looks'
import {
  ago, Badge, Drawer, Empty, Field, Modal, PageHead, SafeImg, Seg, Skeleton, SkeletonCards, Spinner, StatusPill, Tabs,
  titleCase, useAction, useApi, useStatic, useToast,
} from '../components/ui'

const EMOTIONS = [['happy', '😊'], ['excited', '🤩'], ['surprised', '😮'], ['thinking', '🤔'], ['sad', '😢'], ['worried', '😟'], ['proud', '😌'], ['sleepy', '😴'], ['calm', '🙂']]
const ARMS = [['down', 'Rest'], ['wave', 'Wave'], ['up', 'Cheer'], ['point', 'Point'], ['clap', 'Clap']]
const TIERS = {
  main: { label: 'Main', tone: 'brand', icon: 'star', note: 'Core cast — in every writer brief.' },
  recurring: { label: 'Recurring', tone: 'blue', icon: 'refresh', note: 'Comes back — in every writer brief.' },
  cameo: { label: 'Cameo', tone: 'neutral', icon: 'user', note: 'Designed for one story; reused if it appears again.' },
}
const TIER_ORDER = ['main', 'recurring', 'cameo']
const EDITABLE = ['name', 'tier', 'personality', 'look', 'catchphrase', 'colors', 'outfit', 'skin', 'hair', 'hair_color', 'species', 'gender', 'age', 'voice', 'pitch']
const CORE_EDITABLE = new Set(['personality', 'catchphrase', 'voice', 'pitch'])

/** Characters store colours as {main|body, accent, ...}; normalise for display and editing. */
const colorsOf = (c) => {
  const v = c?.colors
  if (!v) return { mainKey: 'main' }
  if (Array.isArray(v)) return { main: v[0], accent: v[1], mainKey: 'main' }
  const mainKey = v.main != null ? 'main' : v.body != null ? 'body' : 'main'
  return { main: v[mainKey] ?? Object.values(v)[0], accent: v.accent, mainKey }
}

function TierBadge({ tier, size }) {
  const t = TIERS[tier] || { label: tier || '—', tone: 'neutral', icon: 'user' }
  return <Badge tone={t.tone} icon={t.icon} size={size}>{t.label}</Badge>
}

function originText(c) {
  const o = c.origin || {}
  if (c.core || o.type === 'core') return 'Core cast'
  if (o.story) return `From “${o.story}”${o.book ? ` · ${o.book}` : ''}`
  if (o.book) return `From ${o.book}`
  if (o.type === 'custom') return 'Made by hand'
  if (o.type === 'story') return 'Designed for a story'
  return c.role || ''
}

/** Normalise the old /api/cast shape to a library character. */
const fromCast = (c) => ({ ...c, tier: 'main', core: true, kind: 'cast', origin: { type: 'core' }, appearances: null })

/* -------------------------------------------------------------- automatic expressions
   Portraits act on their own: a little "beat" of feelings with natural, uneven timing (like the episodes), a pose
   that fits each feeling, and a soft cross-fade. Only cards on screen animate; reduced-motion users get a still. */
const POSE = { happy: 'wave', excited: 'up', surprised: 'down', thinking: 'point', sad: 'down', worried: 'down', proud: 'down', sleepy: 'down', calm: 'down' }
const BEATS = [
  ['happy', 'excited', 'happy'],
  ['thinking', 'surprised', 'excited'],
  ['happy', 'proud', 'calm'],
  ['worried', 'thinking', 'happy'],
  ['sad', 'calm', 'happy'],
  ['surprised', 'excited', 'happy'],
  ['calm', 'happy', 'excited'],
]
const reduceMotion = () => { try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { return false } }
const hashStr = (x) => [...String(x)].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7)

function useAutoEmotion(on, seedKey, ref) {
  const [emo, setEmo] = useState('happy')
  const [visible, setVisible] = useState(!ref)
  useEffect(() => {
    if (!ref?.current || typeof IntersectionObserver === 'undefined') { setVisible(true); return undefined }
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: .3 })
    io.observe(ref.current)
    return () => io.disconnect()
  }, [ref])
  useEffect(() => {
    if (!on || !visible || reduceMotion()) return undefined
    let seed = hashStr(seedKey)
    const rnd = () => { seed = (seed * 1103515245 + 12345) >>> 0; return (seed >>> 8) / 16777216 }
    let beat = BEATS[seed % BEATS.length]; let i = 0; let timer
    const step = () => {
      if (document.hidden) { timer = setTimeout(step, 1500); return }
      setEmo(beat[i])
      i += 1
      if (i >= beat.length) { beat = BEATS[Math.floor(rnd() * BEATS.length)]; i = 0 }
      timer = setTimeout(step, 1400 + rnd() * 1900)          // uneven, human timing
    }
    timer = setTimeout(step, 300 + rnd() * 1500)              // cards don't all change together
    return () => clearTimeout(timer)
  }, [on, visible, seedKey])
  return emo
}

function Portrait({ c, emotion = 'happy', arms, style, size = 360, className = '' }) {
  const col = colorsOf(c)
  const src = castImg(c.id, { emotion, arms: arms || POSE[emotion] || 'down', style, size })
  const [shown, setShown] = useState(src)      // the image on screen; the next one fades in once loaded
  const [next, setNext] = useState(null)
  const [bad, setBad] = useState(false)
  useEffect(() => {
    if (src === shown) return undefined
    let live = true
    const im = new Image()
    im.onload = () => { if (live) setNext(src) }
    im.onerror = () => { if (live) setBad(true) }
    im.src = src
    return () => { live = false }
  }, [src, shown])
  useEffect(() => {
    if (!next) return undefined
    const t = setTimeout(() => { setShown(next); setNext(null) }, 260)
    return () => clearTimeout(t)
  }, [next])
  return (
    <div className={`portrait ${className}`} style={{ '--c-main': col.main || 'var(--brand)', '--c-accent': col.accent || col.main || 'var(--sun)' }}>
      {bad && !shown ? <span className="portrait-ph">{(c.name || '?').slice(0, 1)}</span> : (
        <span className="portrait-stack">
          <SafeImg src={shown} alt={`${c.name}, ${emotion}`} fallback={<span className="portrait-ph">{(c.name || '?').slice(0, 1)}</span>} />
          {next && <img src={next} alt="" aria-hidden="true" className="portrait-next" />}
        </span>
      )}
    </div>
  )
}

function EmotionPicker({ value, onChange, small, auto, onAuto }) {
  return (
    <div className={`emo-row ${small ? 'sm' : ''}`} role="radiogroup" aria-label="Emotion">
      {onAuto && (
        <button type="button" role="radio" aria-checked={!!auto} className={`emo-auto ${auto ? 'on' : ''}`} title="Auto: expressions change by themselves"
          aria-label="Automatic expressions" onClick={(ev) => { ev.stopPropagation(); ev.preventDefault(); onAuto() }}>{small ? '✨' : '✨ Auto'}</button>
      )}
      {EMOTIONS.map(([e, emoji]) => (
        <button key={e} type="button" role="radio" aria-checked={!auto && value === e} className={`${value === e ? 'on' : ''} ${auto && value === e ? 'live' : ''}`} title={titleCase(e)} aria-label={e}
          onClick={(ev) => { ev.stopPropagation(); ev.preventDefault(); onChange(e) }}>{emoji}</button>
      ))}
    </div>
  )
}

function CharCard({ c, style, onOpen }) {
  const ref = useRef(null)
  const [pick, setPick] = useState(null)          // null = automatic
  const autoEmo = useAutoEmotion(pick == null, c.id, ref)
  const emo = pick ?? autoEmo
  return (
    <article className="char-card" ref={ref}>
      <button type="button" className="char-hit" onClick={() => onOpen(c)} aria-label={`Open ${c.name}`} />
      <Portrait c={c} emotion={emo} style={style} />
      <div className="char-top"><TierBadge tier={c.tier} size="sm" />{c.role === 'star' ? <Badge size="sm" tone="amber">⭐ Star</Badge> : c.core && <Badge size="sm" icon="lock">Core</Badge>}</div>
      <EmotionPicker value={emo} onChange={setPick} small auto={pick == null} onAuto={() => setPick(null)} />
      <div className="char-body">
        <div className="char-name"><b>{c.name}</b>{c.appearances != null && <span className="char-apps" title="Episodes this character appears in"><Icon name="film" size={12} />{c.appearances}</span>}</div>
        <div className="char-sub">{[c.species, c.age && c.age !== 'child' ? c.age : null].filter(Boolean).join(' · ') || titleCase(c.kind)}</div>
        <div className="char-origin">{originText(c)}</div>
      </div>
    </article>
  )
}

/* -------------------------------------------------------------- editor */
function CharForm({ value, onChange, core, voices, isNew }) {
  const v = value
  const set = (k) => (x) => onChange({ ...v, [k]: x })
  const ev = (k, fn = (x) => x) => (e) => set(k)(fn(e.target.value))
  const col = colorsOf(v)
  const lock = (k) => core && !CORE_EDITABLE.has(k)
  const voiceList = voices || []
  return (
    <div className="form-grid">
      <Field label="Name" className="span2"><input value={v.name || ''} onChange={ev('name')} disabled={lock('name')} required placeholder="e.g. Wolf" /></Field>
      {isNew && (
        <Field label="Kind">
          <select value={v.kind || 'animal'} onChange={ev('kind')}><option value="animal">Animal</option><option value="human">Human</option></select>
        </Field>
      )}
      <Field label="Species / type"><input value={v.species || ''} onChange={ev('species')} disabled={lock('species')} placeholder={v.kind === 'human' ? 'e.g. girl, king, wizard' : 'e.g. fox, owl, turtle'} /></Field>
      <Field label="Age">
        <select value={v.age || 'child'} onChange={ev('age')} disabled={lock('age')}><option value="child">Child</option><option value="adult">Adult</option><option value="old">Old</option></select>
      </Field>
      <Field label="Gender">
        <select value={v.gender || 'f'} onChange={ev('gender')} disabled={lock('gender')}><option value="f">Female</option><option value="m">Male</option></select>
      </Field>
      <Field label="Main colour">
        <div className="color-input"><input type="color" value={col.main || '#8c91a5'} disabled={lock('colors')} onChange={(e) => set('colors')({ ...(v.colors || {}), [col.mainKey]: e.target.value })} /><code>{col.main || '—'}</code></div>
      </Field>
      <Field label="Accent colour">
        <div className="color-input"><input type="color" value={col.accent || '#e1e4eb'} disabled={lock('colors')} onChange={(e) => set('colors')({ ...(v.colors || {}), accent: e.target.value })} /><code>{col.accent || '—'}</code></div>
      </Field>
      <Field label="Outfit"><input value={v.outfit || ''} onChange={ev('outfit')} disabled={lock('outfit')} placeholder="e.g. scarf, crown, cape" /></Field>
      {(v.kind === 'human' || v.hair || v.skin) && (
        <>
          <Field label="Hair"><input value={v.hair || ''} onChange={ev('hair')} disabled={lock('hair')} placeholder="e.g. curly, bun" /></Field>
          <Field label="Hair colour"><input value={v.hair_color || ''} onChange={ev('hair_color')} disabled={lock('hair_color')} placeholder="#3b2a20" /></Field>
          <Field label="Skin tone"><input value={v.skin || ''} onChange={ev('skin')} disabled={lock('skin')} placeholder="#c68642" /></Field>
        </>
      )}
      <Field label="Look" hint="One line the renderer and writers use to picture them." className="span2">
        <input value={v.look || ''} onChange={ev('look')} disabled={lock('look')} placeholder="A grey wolf with a long bushy tail and a red scarf" />
      </Field>
      <Field label="Personality" className="span2"><textarea rows={3} value={v.personality || ''} onChange={ev('personality')} placeholder="Brave but a little boastful; learns to tell the truth." /></Field>
      <Field label="Catchphrase" className="span2"><input value={v.catchphrase || ''} onChange={ev('catchphrase')} placeholder="“Howl-o, friends!”" /></Field>
      <Field label="Voice" className="span2">
        <select value={v.voice || ''} onChange={ev('voice')}>
          <option value="">Automatic (picked from size & age)</option>
          {v.voice && !voiceList.some((x) => x.id === v.voice) && <option value={v.voice}>{v.voice}</option>}
          {voiceList.map((x) => <option key={x.id} value={x.id}>{x.label}{x.gender ? ` · ${x.gender}` : ''}</option>)}
        </select>
      </Field>
      <Field label={<>Pitch <b className="accent">{Number(v.pitch ?? 1).toFixed(2)}×</b></>} hint="Big animals sound deeper, small ones higher." className="span2">
        <input type="range" min={0.7} max={1.4} step={0.01} value={v.pitch ?? 1} onChange={ev('pitch', Number)} />
      </Field>
      {voiceList.find((x) => x.id === v.voice)?.sample && (
        <div className="span2"><audio controls preload="none" src={voiceList.find((x) => x.id === v.voice).sample} className="voice-audio" /></div>
      )}
    </div>
  )
}

function CharacterDrawer({ id, onClose, onChanged, onDeleted, readOnly, fallback }) {
  const toast = useToast()
  const voices = useStatic('/voices')
  const { styles } = useStyles()
  const [c, setC] = useState(null)
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [pickEmo, setEmo] = useState(null)        // null = automatic
  const [pickArms, setArms] = useState(null)
  const autoEmo = useAutoEmotion(pickEmo == null, `${id}-drawer`)
  const emo = pickEmo ?? autoEmo
  const arms = pickArms ?? POSE[emo] ?? 'down'
  const [style, setStyle] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [busy, run] = useAction()

  useEffect(() => {
    if (!id) return undefined
    let alive = true
    setC(null); setD(null); setErr(null); setEmo(null); setArms(null)
    if (readOnly) { setC(fallback); setD(structuredClone(fallback)); return undefined }
    get(`/characters/${encodeURIComponent(id)}`).then((x) => { if (alive) { setC(x); setD(structuredClone(x)) } }, (e) => { if (alive) setErr(e) })
    return () => { alive = false }
  }, [id, readOnly, fallback])

  const changed = useMemo(() => {
    if (!c || !d) return {}
    const o = {}
    for (const k of EDITABLE) if (JSON.stringify(d[k] ?? null) !== JSON.stringify(c[k] ?? null)) o[k] = d[k]
    return o
  }, [c, d])
  const dirty = Object.keys(changed).length > 0

  const apply = async (body, msg) => {
    const r = await run('save', () => patch(`/characters/${encodeURIComponent(id)}`, body), msg)
    if (r) { const merged = { ...c, ...r }; setC(merged); setD(structuredClone(merged)); onChanged?.(merged) }
  }
  const tierIdx = TIER_ORDER.indexOf(c?.tier)

  return (
    <Drawer open={!!id} onClose={onClose} width={620}
      title={c ? c.name : 'Character'}
      sub={c && <span className="row wrap-row"><TierBadge tier={c.tier} size="sm" />{c.core && <Badge size="sm" icon="lock">Core cast</Badge>}<span className="muted small">{originText(c)}</span></span>}
      footer={c && !readOnly && (
        <>
          {!c.core && <button className="btn ghost danger-text" onClick={() => setConfirm(true)}><Icon name="trash" size={15} />Delete</button>}
          <div className="spacer" />
          <button className="btn ghost" disabled={!dirty} onClick={() => setD(structuredClone(c))}>Discard</button>
          <button className="btn primary" disabled={!dirty || busy === 'save' || !d?.name?.trim()} onClick={() => apply(changed, `${d.name} saved`)}>
            {busy === 'save' ? <Spinner /> : <Icon name="save" size={15} />}Save changes
          </button>
        </>
      )}>
      {err ? <Empty compact icon="alertCircle" title="Couldn’t load this character">{err.message}</Empty> : !c || !d ? (
        <><Skeleton h={300} r={16} /><Skeleton h={18} count={6} style={{ marginTop: 12 }} /></>
      ) : (
        <div className="char-detail">
          <div className="char-stage">
            <Portrait c={d} emotion={emo} arms={arms} style={style || undefined} size={520} className="lg" />
            <div className="stage-controls">
              <EmotionPicker value={emo} onChange={setEmo} auto={pickEmo == null} onAuto={() => { setEmo(null); setArms(null) }} />
              <div className="row wrap-row">
                <Seg size="sm" value={arms} onChange={setArms} options={ARMS} label="Pose" />
                <select className="sm" value={style} onChange={(e) => setStyle(e.target.value)} aria-label="Preview in art style">
                  <option value="">House style</option>
                  {(styles || []).map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                </select>
              </div>
            </div>
          </div>

          {readOnly && <div className="banner info"><Icon name="info" size={18} /><div>The character library API isn’t available on this server yet, so the cast is read-only here.</div></div>}

          {!readOnly && (
            <div className="tier-box">
              <div>
                <div className="field-label">Tier</div>
                <p className="muted small">{TIERS[c.tier]?.note}</p>
              </div>
              {c.core ? <Badge tone="brand" icon="lock">Always main</Badge> : (
                <div className="row">
                  <button className="btn sm" disabled={tierIdx <= 0 || !!busy} onClick={() => apply({ tier: TIER_ORDER[tierIdx - 1] }, `Promoted to ${TIERS[TIER_ORDER[tierIdx - 1]].label}`)}><Icon name="chevronsUp" size={15} />Promote</button>
                  <button className="btn sm" disabled={tierIdx < 0 || tierIdx >= TIER_ORDER.length - 1 || !!busy} onClick={() => apply({ tier: TIER_ORDER[tierIdx + 1] }, `Moved to ${TIERS[TIER_ORDER[tierIdx + 1]].label}`)}><Icon name="chevronsDown" size={15} />Demote</button>
                </div>
              )}
            </div>
          )}

          <div className="char-stats">
            <div><b>{c.appearances ?? '—'}</b><span>appearances</span></div>
            <div><b>{titleCase(c.kind) || '—'}</b><span>kind</span></div>
            <div><b>{c.updated_at ? ago(c.updated_at) : '—'}</b><span>updated</span></div>
          </div>

          <fieldset className="plain-fieldset" disabled={readOnly}>
            <legend className="sr-only">Character details</legend>
            {c.core && !readOnly && <p className="muted small">Core cast: personality, catchphrase and voice are editable; the design stays on model.</p>}
            <CharForm value={d} onChange={setD} core={c.core} voices={voices} />
          </fieldset>

          <div className="block">
            <h4>Episodes</h4>
            {c.episodes_detail?.length ? (
              <ul className="mini-list">
                {c.episodes_detail.map((e) => (
                  <li key={e.id}><Link to={`/episodes/${e.id}`}>{e.title || `Episode #${e.id}`}</Link><StatusPill status={e.status} small /></li>
                ))}
              </ul>
            ) : <p className="muted small">{c.core ? 'Appears across the whole show.' : 'Not in any episode yet.'}</p>}
          </div>
        </div>
      )}

      <Modal open={confirm} onClose={() => setConfirm(false)} title={`Delete ${c?.name}?`} icon="trash"
        actions={<><button className="btn ghost" onClick={() => setConfirm(false)}>Keep</button>
          <button className="btn danger" disabled={busy === 'del'} onClick={async () => {
            const r = await run('del', () => del(`/characters/${encodeURIComponent(id)}`))
            if (r !== undefined) { toast(`${c.name} deleted`); setConfirm(false); onDeleted?.(id) }
          }}>{busy === 'del' ? <Spinner /> : null}Delete character</button></>}>
        <p>{c?.name} will be removed from the library. Episodes already rendered keep their pictures; new stories will design a fresh character if needed.</p>
      </Modal>
    </Drawer>
  )
}

/* ---------------------------------------------------------- new / story */
const BLANK = { name: '', kind: 'animal', tier: 'recurring', species: '', age: 'child', gender: 'f', colors: { main: '#f2a541', accent: '#ffe6b3' }, outfit: '', look: '', personality: '', catchphrase: '', voice: '', pitch: 1 }

function NewCharacter({ open, onClose, onCreated }) {
  const voices = useStatic(open ? '/voices' : null)
  const [d, setD] = useState(BLANK)
  const [busy, run] = useAction()
  useEffect(() => { if (open) setD(structuredClone(BLANK)) }, [open])
  const submit = async () => {
    const body = Object.fromEntries(Object.entries(d).filter(([, v]) => v !== '' && v != null))
    const r = await run('new', () => post('/characters', body), `${d.name} added to the library`)
    if (r) onCreated(r)
  }
  return (
    <Drawer open={open} onClose={onClose} title="New character" sub="Designed in the house style, voiced automatically unless you pick a voice." width={620}
      footer={<><div className="spacer" /><button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={!d.name.trim() || busy === 'new'} onClick={submit}>{busy === 'new' ? <Spinner /> : <Icon name="userPlus" size={16} />}Create character</button></>}>
      <div className="char-detail">
        <div className="char-stage new">
          <div className="portrait lg" style={{ '--c-main': d.colors?.main, '--c-accent': d.colors?.accent }}>
            <span className="portrait-ph">{(d.name || '?').slice(0, 1).toUpperCase()}</span>
          </div>
          <div className="stage-controls"><p className="muted small">The portrait is drawn after you create the character.</p></div>
        </div>
        <div className="field">
          <span className="field-label">Tier</span>
          <Seg value={d.tier} onChange={(t) => setD({ ...d, tier: t })} options={TIER_ORDER.map((t) => [t, TIERS[t].label])} label="Tier" />
          <small className="hint">{TIERS[d.tier]?.note}</small>
        </div>
        <CharForm value={d} onChange={setD} voices={voices} isNew />
      </div>
    </Drawer>
  )
}

function FromStory({ open, onClose, onDone, styleId }) {
  const [title, setTitle] = useState('')
  const [book, setBook] = useState('')
  const [text, setText] = useState('')
  const [res, setRes] = useState(null)
  const [busy, run] = useAction()
  useEffect(() => { if (open) { setRes(null) } }, [open])
  const submit = async () => {
    const r = await run('story', () => post('/characters/from-story', { title: title.trim(), text, book: book.trim() || undefined }),
      (x) => `Designed ${x?.characters?.length ?? 0} character${x?.characters?.length === 1 ? '' : 's'}`)
    if (r) { setRes(r); onDone?.() }
  }
  return (
    <Modal open={open} onClose={onClose} wide icon="wand" title={res ? 'Your story’s cast' : 'Create characters from a story'}
      actions={res ? <><button className="btn ghost" onClick={() => setRes(null)}>Another story</button><button className="btn primary" onClick={onClose}>Done</button></>
        : <><button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!title.trim() || text.trim().length < 40 || text.length > 20000 || busy === 'story'} onClick={submit}>
            {busy === 'story' ? <><Spinner />Designing…</> : <><Icon name="sparkles" size={16} />Design the cast</>}
          </button></>}>
      {res ? (
        <>
          <div className="row wrap-row">
            <Badge tone="green" icon="plus">{res.created ?? 0} new</Badge>
            <Badge tone="blue" icon="refresh">{res.reused ?? 0} reused</Badge>
            <span className="muted small">Saved as cameos — promote any you want to keep around.</span>
          </div>
          {res.characters?.length ? (
            <div className="grid chars small" style={{ marginTop: 16 }}>
              {res.characters.map((c) => (
                <div key={c.id} className="char-card static">
                  <Portrait c={c} style={styleId} />
                  <div className="char-top"><TierBadge tier={c.tier} size="sm" /></div>
                  <div className="char-body"><div className="char-name"><b>{c.name}</b></div><div className="char-sub">{c.species || titleCase(c.kind)}</div>{c.look && <div className="char-origin">{c.look}</div>}</div>
                </div>
              ))}
            </div>
          ) : <Empty compact icon="users" title="No characters found">The designer couldn’t spot any characters in that text.</Empty>}
        </>
      ) : (
        <div className="form-grid">
          <Field label="Story title"><input data-autofocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="The Lion and the Mouse" /></Field>
          <Field label={<>Book <span className="muted">(optional)</span></>}><input value={book} onChange={(e) => setBook(e.target.value)} placeholder="Aesop’s Fables" /></Field>
          <Field label="Story text" className="span2" hint="Every character the story needs is designed (with AI if a key is set, otherwise the keyword designer) and saved as a cameo."
            counter={<span className={`counter ${text.length > 20000 ? 'over' : ''}`}>{text.length.toLocaleString()}/20,000</span>}>
            <textarea rows={10} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the story here…" />
          </Field>
        </div>
      )}
    </Modal>
  )
}

/* --------------------------------------------------------------- page */
export default function Characters() {
  const [tier, setTier] = useState('all')
  const [q, setQ] = useState('')
  const [qDeb, setQDeb] = useState('')
  const [style, setStyle] = useState('')
  const [openId, setOpenId] = useState(null)
  const [newOpen, setNewOpen] = useState(false)
  const [storyOpen, setStoryOpen] = useState(false)
  const { styles } = useStyles()
  useEffect(() => { const h = setTimeout(() => setQDeb(q.trim()), 250); return () => clearTimeout(h) }, [q])

  const lib = useApi(`/characters${qDeb ? `?q=${encodeURIComponent(qDeb)}` : ''}`, { quiet: true })
  const fallbackOn = !!lib.error && (lib.error.status === 404 || lib.error.status === 405)
  const cast = useApi(fallbackOn ? '/cast' : null, { quiet: true })

  const all = useMemo(() => {
    if (Array.isArray(lib.data)) return lib.data
    if (fallbackOn && Array.isArray(cast.data)) {
      const needle = qDeb.toLowerCase()
      return cast.data.map(fromCast).filter((c) => !needle || `${c.name} ${c.species}`.toLowerCase().includes(needle))
    }
    return null
  }, [lib.data, fallbackOn, cast.data, qDeb])
  const counts = useMemo(() => {
    const o = { all: all?.length || 0 }
    for (const c of all || []) o[c.tier] = (o[c.tier] || 0) + 1
    return o
  }, [all])
  const list = (all || []).filter((c) => tier === 'all' || c.tier === tier)
  const openChar = (all || []).find((c) => c.id === openId)
  const loading = (lib.loading && !lib.data) || (fallbackOn && cast.loading && !cast.data)

  const replace = (c) => lib.setData((x) => (Array.isArray(x) ? x.map((y) => (y.id === c.id ? { ...y, ...c } : y)) : x))

  return (
    <div className="page">
      <PageHead title="Characters" sub="Every character in the show. Main and recurring characters are in every writer brief; cameos are designed for one story and reused when they come back.">
        <button className="btn" onClick={() => setStoryOpen(true)} disabled={fallbackOn}><Icon name="wand" size={16} />From a story</button>
        <button className="btn primary" onClick={() => setNewOpen(true)} disabled={fallbackOn}><Icon name="userPlus" size={16} />New character</button>
      </PageHead>

      {fallbackOn && (
        <div className="banner info"><Icon name="info" size={18} /><div><b>Showing the core cast only.</b> The character library API (<code>/api/characters</code>) isn’t on this server yet — story characters, tiers and editing appear once the backend is updated.</div></div>
      )}
      {lib.error && !fallbackOn && (
        <div className="banner bad"><Icon name="alertCircle" size={18} /><div>Couldn’t load characters: {lib.error.message} <button className="btn sm" onClick={() => lib.reload()}>Retry</button></div></div>
      )}

      <div className="toolbar">
        <Tabs value={tier} onChange={setTier} className="pill-tabs" tabs={[
          ['all', 'All', counts.all],
          ['main', 'Main', counts.main || 0, 'star'],
          ['recurring', 'Recurring', counts.recurring || 0, 'refresh'],
          ['cameo', 'Cameo', counts.cameo || 0, 'user'],
        ]} />
        <div className="spacer" />
        <label className="search-box">
          <Icon name="search" size={16} />
          <input type="search" placeholder="Search characters" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search characters" />
        </label>
        <label className="select-inline">
          <Icon name="palette" size={15} />
          <select value={style} onChange={(e) => setStyle(e.target.value)} aria-label="Preview portraits in art style">
            <option value="">House style</option>
            {(styles || []).map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
      </div>

      {loading ? <SkeletonCards n={8} h={220} className="grid chars" /> : list.length === 0 ? (
        <Empty icon="users" title={q ? 'No characters match' : tier === 'all' ? 'No characters yet' : `No ${TIERS[tier]?.label.toLowerCase()} characters`}
          action={!fallbackOn && <button className="btn primary" onClick={() => setStoryOpen(true)}><Icon name="wand" size={16} />Create from a story</button>}>
          {tier === 'cameo' ? 'Cameos are designed automatically when an episode adapts a story.' : 'Characters appear here as stories are adapted, or create one by hand.'}
        </Empty>
      ) : (
        <div className="grid chars">
          {list.map((c) => <CharCard key={c.id} c={c} style={style || undefined} onOpen={(x) => setOpenId(x.id)} />)}
        </div>
      )}

      <CharacterDrawer id={openId} onClose={() => setOpenId(null)} readOnly={fallbackOn} fallback={fallbackOn ? openChar : null}
        onChanged={replace} onDeleted={() => { setOpenId(null); lib.reload(true) }} />
      <NewCharacter open={newOpen} onClose={() => setNewOpen(false)} onCreated={(c) => { setNewOpen(false); lib.reload(true); if (c?.id) setOpenId(c.id) }} />
      <FromStory open={storyOpen} onClose={() => setStoryOpen(false)} onDone={() => lib.reload(true)} styleId={style || undefined} />
    </div>
  )
}
