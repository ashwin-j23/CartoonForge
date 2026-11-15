import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { post } from '../api'
import BookBrowser from '../components/BookBrowser'
import Icon from '../components/icons'
import { AnimationPicker, EstimateBox, MODE_MAP, PalettePicker, StyleThumb, StylePicker, useAIVideo, usePalettes, useStyles, AUTO_STYLE } from '../components/looks'
import { Field, fmtUsd, Seg, Skeleton, Spinner, useAction, useApi, useCategoryMap, useStatic } from '../components/ui'

const STEPS = [
  ['idea', 'Idea', 'bulb'],
  ['audience', 'Audience', 'smile'],
  ['look', 'Art style', 'palette'],
  ['motion', 'Animation', 'film'],
  ['review', 'Review', 'checkCircle'],
]

function Stepper({ step, setStep, maxSeen }) {
  return (
    <ol className="stepper" aria-label="Steps">
      {STEPS.map(([id, label, icon], i) => {
        const state = i === step ? 'current' : i < step ? 'done' : ''
        return (
          <li key={id} className={state}>
            <button type="button" disabled={i > maxSeen} onClick={() => setStep(i)} aria-current={i === step ? 'step' : undefined}>
              <span className="step-n">{i < step ? <Icon name="check" size={14} strokeWidth={2.6} /> : <Icon name={icon} size={14} />}</span>
              <span className="step-label">{label}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

export default function Create() {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const [cats, catMap] = useCategoryMap()
  const psych = useStatic('/psychology')
  const settings = useApi('/settings', { quiet: true }).data
  const trends = useApi('/trends', { quiet: true }).data
  const { map: styleMap } = useStyles()
  const { info: ai } = useAIVideo()
  const [busy, run] = useAction()
  const top = useRef(null)

  const initBook = params.get('book') ? { gid: params.get('book'), index: Number(params.get('index') || 0), title: params.get('story') || 'Story', bookTitle: params.get('bookTitle') || '' } : null
  const [step, setStep] = useState(0)
  const [maxSeen, setMaxSeen] = useState(0)
  const [source, setSource] = useState(initBook ? 'book' : 'topic')
  const [cat, setCat] = useState(params.get('category') || null)
  const [topic, setTopic] = useState(params.get('topic') || '')
  const [book, setBook] = useState(initBook)
  const [band, setBand] = useState(params.get('band') || '')
  const [minutes, setMinutes] = useState(null)
  const [style, setStyle] = useState(params.get('style') || null)
  const [pal, setPal] = useState(params.get('palette') || 'auto')
  const { list: palettes } = usePalettes()
  const [anim, setAnim] = useState(params.get('animation') || null)
  const [budget, setBudget] = useState(null)

  // defaults from settings, once
  useEffect(() => {
    if (!settings) return
    setBand((b) => b || settings.age_band || 'preschool')
    setMinutes((m) => m ?? settings.target_minutes ?? 12)
    setStyle((s) => s ?? settings.art_style ?? 'auto')
    setAnim((a) => a ?? settings.animation ?? 'code')
    setBudget((b) => b ?? settings.ai_video_budget_usd ?? 5)
  }, [settings])
  useEffect(() => { if (!settings && psych && !band) setBand(Object.keys(psych.bands || {})[0] || '') }, [psych, settings, band])

  const go = (i) => {
    setStep(i); setMaxSeen((m) => Math.max(m, i))
    top.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const bands = psych?.bands || {}
  const current = cat ? catMap[cat] : null
  const ideas = (trends?.ideas || []).filter((t) => !t.used).slice(0, 6)
  const bandOk = !current || !current.bands?.length || current.bands.includes(band)
  const ideaOk = source === 'topic' || !!book
  const styleObj = style === 'auto' ? AUTO_STYLE : styleMap[style]

  const create = async () => {
    const body = { age_band: band || undefined, minutes: Number(minutes) || undefined, art_style: style || undefined, animation: anim || undefined, palette: pal && pal !== 'auto' ? pal : undefined }
    if (anim && anim !== 'code' && budget != null && budget !== '') body.ai_budget_usd = Number(budget)
    if (source === 'book' && book) body.book = { gid: Number(book.gid) || book.gid, index: Number(book.index) || 0 }
    else {
      if (cat) body.category = cat
      if (topic.trim()) body.topic = topic.trim()
    }
    const ep = await run('create', () => post('/episodes', body), 'Episode queued — the writers are on it!')
    if (ep?.id != null) nav(`/episodes/${ep.id}`)
  }

  const summary = useMemo(() => [
    ['Idea', source === 'book' && book ? <><b>{book.title}</b>{book.bookTitle ? <span className="muted"> · from {book.bookTitle}</span> : null}</>
      : <>{current ? <b>{current.emoji} {current.name}</b> : <b>Planner’s choice</b>}{topic.trim() ? <span> · “{topic.trim()}”</span> : <span className="muted"> · topic picked by the planner</span>}</>, 0],
    ['Audience', <><b>{bands[band]?.label || band}</b><span className="muted"> · {minutes} minutes</span></>, 1],
    ['Art style', <span className="sum-style"><StyleThumb style={styleObj || { id: style, label: style }} className="sm" /><b>{styleObj?.label || style}</b></span>, 2],
    ['Animation', <><b>{MODE_MAP[anim]?.label || anim}</b>{anim !== 'code' && budget ? <span className="muted"> · budget cap {fmtUsd(budget)}</span> : null}</>, 3],
  ], [source, book, current, topic, bands, band, minutes, styleObj, style, anim, budget])

  return (
    <div className="page create" ref={top}>
      <div className="crumbs"><Link to="/episodes"><Icon name="arrowLeft" size={14} />Episodes</Link></div>
      <header className="page-head">
        <div className="page-head-text">
          <div className="eyebrow"><Icon name="sparkles" size={14} />New episode</div>
          <h1>Let’s make an episode</h1>
          <p className="sub">Five quick choices. The writers, critic, voices and renderer do the rest.</p>
        </div>
      </header>

      <Stepper step={step} setStep={go} maxSeen={maxSeen} />

      <div className="wizard">
        {step === 0 && (
          <section className="wizard-step">
            <div className="step-head">
              <h2>What’s it about?</h2>
              <Seg value={source} onChange={setSource} label="Source" options={[['topic', 'Topic', 'bulb'], ['book', 'Book story', 'book']]} />
            </div>

            {source === 'topic' ? (
              <>
                <div className="field-label">Category</div>
                {!cats ? <div className="cat-grid"><Skeleton h={78} count={8} r={12} /></div> : (
                  <div className="cat-grid" role="radiogroup" aria-label="Category">
                    <button type="button" role="radio" aria-checked={cat === null} className={`cat-tile ${cat === null ? 'on' : ''}`} onClick={() => setCat(null)}>
                      <span className="cat-emoji">🎲</span><span>Surprise me</span>
                    </button>
                    {cats.map((c) => (
                      <button type="button" role="radio" aria-checked={cat === c.id} key={c.id} className={`cat-tile ${cat === c.id ? 'on' : ''}`} onClick={() => setCat(c.id)} title={c.mood || c.name}>
                        <span className="cat-emoji">{c.emoji}</span><span>{c.name}</span>
                      </button>
                    ))}
                  </div>
                )}
                <Field label={<>Topic <span className="muted">(optional)</span></>} hint={current ? `${current.name}${current.lead ? ` · hosted by ${current.lead}` : ''}${current.blueprint?.length ? ` · ${current.blueprint.length} segments` : ''}` : 'Leave empty and the planner picks a fresh one.'}>
                  <input value={topic} maxLength={120} onChange={(e) => setTopic(e.target.value)} placeholder={current ? `e.g. ${current.topics?.[0] || 'counting ducks'}` : 'e.g. why the moon changes shape'} />
                </Field>
                {current?.topics?.length > 0 && (
                  <div className="suggest">
                    <span className="muted small">Ideas</span>
                    {current.topics.slice(0, 8).map((t) => <button type="button" key={t} className={`chip ${topic === t ? 'on' : ''}`} onClick={() => setTopic(t)}>{t}</button>)}
                  </div>
                )}
                {ideas.length > 0 && (
                  <div className="trend-picks">
                    <div className="field-label"><span><Icon name="trending" size={14} /> Trending right now</span><Link to="/library/trends" className="link-sm">All trends</Link></div>
                    <div className="trend-pick-grid">
                      {ideas.map((t) => (
                        <button type="button" key={t.id} className={`trend-pick ${topic === t.topic ? 'on' : ''}`}
                          onClick={() => { setTopic(t.topic); if (catMap[t.category]) setCat(t.category); if (t.age_band && bands[t.age_band]) setBand(t.age_band) }}>
                          <span className="trend-score-sm">{t.score}</span>
                          <span><b>{t.topic}</b><small>{catMap[t.category]?.emoji} {catMap[t.category]?.name || t.category}</small></span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : book ? (
              <div className="picked-book">
                <span className="picked-ico"><Icon name="bookOpen" size={22} /></span>
                <div className="grow"><b>{book.title}</b><div className="muted small">{book.bookTitle ? `From ${book.bookTitle} · ` : ''}Project Gutenberg #{book.gid} · story {Number(book.index) + 1}</div></div>
                <button className="btn sm" onClick={() => setBook(null)}>Change</button>
              </div>
            ) : (
              <BookBrowser compact renderAction={(s, b) => (
                <button className="btn primary sm" onClick={() => { setBook({ gid: b.id, index: s.index, title: s.title || `Story ${s.index + 1}`, bookTitle: b.title }); go(1) }}>
                  Use this story<Icon name="arrowRight" size={14} />
                </button>
              )} />
            )}
          </section>
        )}

        {step === 1 && (
          <section className="wizard-step">
            <div className="step-head"><h2>Who’s watching?</h2></div>
            {!psych ? <div className="band-grid"><Skeleton h={120} count={4} r={14} /></div> : (
              <div className="band-grid" role="radiogroup" aria-label="Age band">
                {Object.entries(bands).map(([id, b]) => (
                  <button type="button" key={id} role="radio" aria-checked={band === id} className={`band-card ${band === id ? 'on' : ''}`} onClick={() => setBand(id)}>
                    <span className="band-ages">{b.ages || id}</span>
                    <b>{b.label || id}</b>
                    <span className="band-facts">{b.wpm ? `${b.wpm} words/min` : ''}{b.sentence ? ` · ≤${b.sentence}-word sentences` : ''}</span>
                    {b.content && <span className="band-note">{b.content}</span>}
                  </button>
                ))}
              </div>
            )}
            {!bandOk && <div className="banner warn"><Icon name="alert" size={18} /><div>{current.name} isn’t designed for this age band — the writer will adapt it, but a different category may fit better.</div></div>}
            <div className="length-pick">
              <Field label={<>Length <b className="accent">{minutes ?? 12} min</b></>} hint="Long enough to settle in, short enough to finish. 10–15 minutes works best for watch time.">
                <input type="range" min={10} max={15} step={1} value={minutes ?? 12} onChange={(e) => setMinutes(Number(e.target.value))} />
                <div className="range-ticks" aria-hidden="true">{[10, 11, 12, 13, 14, 15].map((m) => <span key={m}>{m}</span>)}</div>
              </Field>
            </div>
          </section>
        )}

        {step === 2 && (
          <section className="wizard-step">
            <div className="step-head">
              <div>
                <h2>Pick the look</h2>
                <p className="muted">Same characters, same story — a different visual treatment. Looks tuned for {bands[band]?.label || 'this age band'} are highlighted.</p>
              </div>
              <Link to="/looks" className="link-sm">About looks<Icon name="arrowRight" size={14} /></Link>
            </div>
            <StylePicker value={style} onChange={setStyle} band={band} defaultId={settings?.art_style} />
            {palettes.length > 0 && (
              <div style={{ marginTop: 24 }}>
                <div className="field-label"><span>Colour palette</span><small className="muted"> · Auto matches the topic and age (pastels for toddlers and bedtime)</small></div>
                <PalettePicker value={pal} onChange={setPal} list={palettes} />
              </div>
            )}
          </section>
        )}

        {step === 3 && (
          <section className="wizard-step">
            <div className="step-head">
              <div>
                <h2>How should it move?</h2>
                <p className="muted">Our code renderer is free and frame-exact. AI video can add cinematic hero shots, or re-animate everything.</p>
              </div>
            </div>
            <AnimationPicker value={anim} onChange={setAnim} info={ai} />
            <div className="motion-foot">
              <EstimateBox mode={anim} minutes={minutes} provider={settings?.ai_video_provider} info={ai} budget={anim !== 'code' ? budget : null} />
              {anim !== 'code' && (
                <Field label="Budget cap (USD)" hint="AI spending stops here; remaining shots keep the code animation.">
                  <div className="input-prefix"><span>$</span><input type="number" min={0} step={1} value={budget ?? ''} onChange={(e) => setBudget(e.target.value === '' ? '' : Number(e.target.value))} /></div>
                </Field>
              )}
            </div>
          </section>
        )}

        {step === 4 && (
          <section className="wizard-step">
            <div className="step-head"><h2>Ready to roll?</h2></div>
            <dl className="summary">
              {summary.map(([k, v, i]) => (
                <div key={k} className="summary-row">
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                  <button className="btn ghost sm" onClick={() => go(i)}><Icon name="edit" size={14} />Edit</button>
                </div>
              ))}
            </dl>
            <div className="banner info">
              <Icon name="shieldCheck" size={18} />
              <div>The script is scored by the child-psychology critic and checked by the safety gate. {settings?.autopilot ? 'Autopilot will schedule it if it clears the bar.' : 'It will wait in your review queue before anything is published.'}</div>
            </div>
          </section>
        )}
      </div>

      <div className="wizard-bar">
        <button className="btn ghost" onClick={() => (step ? go(step - 1) : nav(-1))}><Icon name="arrowLeft" size={16} />{step ? 'Back' : 'Cancel'}</button>
        <span className="wizard-pos muted small">Step {step + 1} of {STEPS.length}</span>
        {step < STEPS.length - 1 ? (
          <button className="btn primary" onClick={() => go(step + 1)} disabled={step === 0 && !ideaOk}>
            Next: {STEPS[step + 1][1]}<Icon name="arrowRight" size={16} />
          </button>
        ) : (
          <button className="btn primary lg" onClick={create} disabled={busy === 'create' || !ideaOk}>
            {busy === 'create' ? <Spinner /> : <Icon name="sparkles" size={18} />}Create episode
          </button>
        )}
      </div>
      {step === 0 && source === 'book' && !book && <p className="muted small center">Open a book and pick a story to continue.</p>}
    </div>
  )
}
