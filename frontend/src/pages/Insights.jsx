import { useMemo, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { post } from '../api'
import { EpisodeCard } from '../components/EpisodeCard'
import Icon from '../components/icons'
import {
  Badge, Bar, Empty, fmtDate, fmtNum, PageHead, Progress, Skeleton, SkeletonCards, Spinner, Stat, Tabs, until, useAction, useApi, useCategoryMap,
} from '../components/ui'

/* =========================================================== analytics */
function usePctScale(rows) {
  return useMemo(() => {
    const vals = rows.map((r) => r.avg_pct).filter((v) => typeof v === 'number')
    return vals.length && vals.every((v) => v <= 1) ? 100 : 1
  }, [rows])
}
const pct = (v, k) => (v == null ? '—' : `${(v * k).toFixed(1)}%`)
const DIM = { pace: 'Pace', minutes: 'Length (min)', thumb: 'Thumbnail style', title: 'Title style', style: 'Art style', art_style: 'Art style' }
const fmtMean = (v) => (v == null ? '—' : v <= 1 ? `${(v * 100).toFixed(1)}%` : Number(v).toFixed(1))

function Learning() {
  const { data, loading } = useApi('/optimizer', { quiet: true })
  if (loading && !data) return <section className="card"><Skeleton h={160} /></section>
  if (!data) return null
  const arms = Object.entries(data.arms || {})
  const segs = Object.entries(data.segments || {}).filter(([, v]) => typeof v === 'number').sort((a, b) => a[1] - b[1])
  const maxDrop = Math.max(0.0001, ...segs.map(([, v]) => v))
  return (
    <section className="card">
      <div className="card-head">
        <h2><Icon name="flask" size={18} />What the channel is learning</h2>
        {data.updated && <span className="muted small">{data.episodes} episodes · updated {fmtDate(data.updated)}</span>}
      </div>
      {!data.episodes ? (
        <Empty compact icon="flask" title="Nothing learned yet">Learns once episodes are published and YouTube Analytics is connected.</Empty>
      ) : (
        <>
          {data.hints && <div className="banner info"><Icon name="bulb" size={18} /><div className="wrap">{data.hints}</div></div>}
          <div className="arms">
            {arms.map(([dim, opts]) => {
              const rows = Object.entries(opts || {})
              const max = Math.max(0.0001, ...rows.map(([, o]) => o.mean || 0))
              const best = rows.filter(([, o]) => o.n > 0).reduce((a, r) => (!a || (r[1].mean ?? -Infinity) > (a[1].mean ?? -Infinity) ? r : a), null)?.[0]
              return (
                <div className="arm" key={dim}>
                  <h4>{DIM[dim] || dim}</h4>
                  {rows.length === 0 ? <p className="muted small">No data yet.</p> : rows.map(([opt, o]) => (
                    <div key={opt} className={`arm-row ${opt === best ? 'best' : ''}`}>
                      <span className="arm-name">{opt === best && <Icon name="star" size={12} />}{opt}</span>
                      <Bar value={o.mean || 0} max={max} tone={opt === best ? 'green' : 'blue'} />
                      <span className="arm-v">{fmtMean(o.mean)} <small className="muted">n={o.n ?? 0}</small></span>
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
          <div className="learn-two">
            <div>
              <h4>Segments that hold attention <small className="muted">avg viewer drop per minute — lower is better</small></h4>
              {segs.length === 0 ? <p className="muted small">No segment data yet.</p> : (
                <ol className="seg-rank">
                  {segs.map(([k, v], i) => (
                    <li key={k}>
                      <span className="seg-rank-n">{i + 1}</span>
                      <span className="arm-name">{k}</span>
                      <Bar value={v} max={maxDrop} tone={i === 0 ? 'green' : i === segs.length - 1 && segs.length > 1 ? 'red' : 'amber'} />
                      <span className="arm-v">{Number(v).toFixed(1)}%/min</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
            <div className="first30">
              <h4>First 30 seconds</h4>
              <div className="big-num">{data.first_30s_drop == null ? '—' : `${Number(data.first_30s_drop).toFixed(1)}%`}</div>
              <p className="muted small">of viewers leave in the first 30 s. The opening hook matters most.</p>
            </div>
          </div>
        </>
      )}
    </section>
  )
}

function Analytics() {
  const { data, loading } = useApi('/analytics')
  const [sort, setSort] = useState('views')
  const cats = data?.categories || []
  const eps = data?.episodes || []
  const k = usePctScale([...cats, ...eps])
  const maxViews = Math.max(1, ...cats.map((c) => c.views || 0))
  const sorted = useMemo(() => [...eps].sort((a, b) => (sort === 'recent' ? String(b.published_at).localeCompare(String(a.published_at)) : (b[sort] || 0) - (a[sort] || 0))), [eps, sort])

  if (loading && !data) return <><div className="stats"><Skeleton h={98} count={3} r={14} /></div><Skeleton h={300} r={14} /></>

  return (
    <>
      <section className="stats three">
        <Stat icon="eye" tone="blue" label="Total views" value={fmtNum(data?.totals?.views)} />
        <Stat icon="heart" tone="pink" label="Likes" value={fmtNum(data?.totals?.likes)} />
        <Stat icon="film" tone="green" label="Published episodes" value={fmtNum(data?.totals?.episodes)} />
      </section>

      <Learning />

      {!cats.length && !eps.length ? (
        <Empty icon="chart" title="No numbers yet">Analytics appear once episodes are published and YouTube is connected.</Empty>
      ) : (
        <>
          <section className="card flush">
            <div className="card-head pad"><h2>By category</h2><span className="muted small">Average view % is the best signal that kids stayed</span></div>
            <div className="scroll-x">
              <table className="table">
                <thead><tr><th>Category</th><th className="num">Episodes</th><th>Views</th><th>Avg view %</th></tr></thead>
                <tbody>
                  {[...cats].sort((a, b) => (b.views || 0) - (a.views || 0)).map((c) => (
                    <tr key={c.id}>
                      <td><b>{c.emoji} {c.name}</b></td>
                      <td className="num">{c.episodes}</td>
                      <td className="bar-cell"><Bar value={c.views} max={maxViews} tone="blue" /><span>{fmtNum(c.views)}</span></td>
                      <td className="bar-cell"><Bar value={(c.avg_pct || 0) * k} max={100} tone={(c.avg_pct || 0) * k >= 50 ? 'green' : (c.avg_pct || 0) * k >= 30 ? 'amber' : 'red'} /><span>{pct(c.avg_pct, k)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card flush">
            <div className="card-head pad">
              <h2>Top episodes</h2>
              <select value={sort} onChange={(e) => setSort(e.target.value)} className="sm" aria-label="Sort episodes">
                <option value="views">Most viewed</option><option value="likes">Most liked</option><option value="avg_pct">Best retention</option><option value="recent">Most recent</option>
              </select>
            </div>
            <div className="scroll-x">
              <table className="table">
                <thead><tr><th>#</th><th>Episode</th><th className="num">Views</th><th className="num">Likes</th><th>Avg view %</th><th>Published</th></tr></thead>
                <tbody>
                  {sorted.slice(0, 50).map((e, i) => (
                    <tr key={e.id}>
                      <td className="muted">{i + 1}</td>
                      <td><Link to={`/episodes/${e.id}`}>{e.title}</Link> {e.url && <a href={e.url} target="_blank" rel="noreferrer" title="Open on YouTube" aria-label="Open on YouTube"><Icon name="external" size={12} /></a>}<div className="muted tiny">{e.category}</div></td>
                      <td className="num">{fmtNum(e.views)}</td>
                      <td className="num">{fmtNum(e.likes)}</td>
                      <td className="bar-cell"><Bar value={(e.avg_pct || 0) * k} max={100} tone="green" /><span>{pct(e.avg_pct, k)}</span></td>
                      <td className="muted small nowrap">{fmtDate(e.published_at, { month: 'short', day: 'numeric', year: 'numeric' })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  )
}

/* ============================================================== growth */
function Growth() {
  const { data, loading, reload } = useApi('/growth', { ms: 30000 })
  const [busy, run] = useAction()
  const [, catMap] = useCategoryMap()
  const tips = data?.tips || []
  const done = tips.filter((t) => t.done).length

  return (
    <>
      <div className="toolbar">
        <p className="muted small grow">Reach more families without ever pushing kids: Shorts, compilations, search and one grown-up-directed subscribe line.</p>
        <button className="btn primary" disabled={busy === 'comp'}
          onClick={async () => { const r = await run('comp', () => post('/growth/compilation'), 'Compilation queued'); if (r) reload(true) }}>
          {busy === 'comp' ? <Spinner /> : <Icon name="layers" size={16} />}Make a compilation now
        </button>
      </div>

      <div className="growth-top">
        <section className="card">
          <div className="card-head">
            <h2>Growth checklist</h2>
            {tips.length > 0 && <span className="muted small">{done} of {tips.length} done</span>}
          </div>
          {tips.length > 0 && <Progress pct={(done / tips.length) * 100} tone="green" />}
          {loading && !data ? <Skeleton h={44} count={5} style={{ marginTop: 10 }} /> : tips.length === 0 ? <p className="muted">No tips right now.</p> : (
            <ul className="checklist">
              {tips.map((t, i) => (
                <li key={i} className={t.done ? 'done' : ''}>
                  <span className="tick" aria-label={t.done ? 'done' : 'to do'}>{t.done && <Icon name="check" size={13} strokeWidth={2.6} />}</span>
                  <div><b>{t.title}</b>{t.detail && <p className="muted small">{t.detail}</p>}</div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <aside className="stack">
          <div className="card">
            <h3><Icon name="layers" size={16} />Next compilation</h3>
            {!data ? <Skeleton h={24} /> : data.next_compilation
              ? <p><b>{fmtDate(data.next_compilation, { weekday: 'long', month: 'short', day: 'numeric' })}</b><br /><span className="muted small">in {until(data.next_compilation)}</span></p>
              : <p className="muted small">Weekly compilations are off. Turn them on in <Link to="/settings#growth">Settings → Growth</Link>.</p>}
          </div>
          <div className="card">
            <h3><Icon name="search" size={16} />SEO keywords</h3>
            {data?.seo_keywords?.length
              ? <div className="chips">{data.seo_keywords.map((k) => <Badge key={k} tone="blue" size="sm">{k}</Badge>)}</div>
              : <p className="muted small">Keywords appear once a few episodes have metadata.</p>}
          </div>
        </aside>
      </div>

      <section>
        <div className="section-title"><div><h2><Icon name="phone" size={18} />Shorts</h2><p className="muted small">Vertical cut-downs of full episodes — the cheapest discovery channel.</p></div></div>
        {loading && !data ? <SkeletonCards n={4} h={140} /> : data?.shorts?.length
          ? <div className="grid cards">{data.shorts.map((e) => <EpisodeCard key={e.id} ep={e} cat={catMap[e.category]} />)}</div>
          : <Empty compact icon="phone" title="No Shorts yet">Open a published episode and press “Cut a Short”.</Empty>}
      </section>

      <section>
        <div className="section-title"><div><h2><Icon name="layers" size={18} />Compilations</h2><p className="muted small">Long-form blocks of past episodes — parents love 45 minutes for car rides.</p></div></div>
        {loading && !data ? <SkeletonCards n={3} h={140} /> : data?.compilations?.length
          ? <div className="grid cards">{data.compilations.map((e) => <EpisodeCard key={e.id} ep={e} cat={catMap[e.category]} />)}</div>
          : <Empty compact icon="layers" title="No compilations yet">Make one now with the button above.</Empty>}
      </section>
    </>
  )
}

/* ============================================================ playbook */
const ROWS = [
  ['ages', 'Ages', (v) => v],
  ['wpm', 'Speaking pace', (v) => `${v} words/min`],
  ['sentence', 'Longest sentence', (v) => `${v} words`],
  ['shot', 'Shortest shot', (v) => `${v} s`],
  ['segment', 'Attention segment', (v) => `${v} min`],
  ['pause', 'Answer pause', (v) => `${v} s`],
  ['interact_per_min', 'Interactions', (v) => `${v} / min`],
  ['repeat_key', 'Key-word repeats', (v) => `≥ ${v}×`],
  ['voice', 'Voice', (v) => v],
  ['content', 'Content', (v) => v],
]
const PRINCIPLE_EMOJI = ['🌱', '🔁', '🙋', '🐢', '🎵', '💛', '🧩', '🌈', '👀', '🧸', '🎯', '🌙']
const show = (v) => (Array.isArray(v) ? v.join(', ') : v && typeof v === 'object' ? Object.entries(v).map(([k, x]) => `${k}: ${x}`).join(' · ') : v)

function Playbook() {
  const { data, loading } = useApi('/psychology')
  if (loading && !data) return <Skeleton h={320} r={14} />
  if (!data) return <Empty icon="bulb" title="Playbook unavailable" />
  const bands = Object.entries(data.bands || {})
  const rows = ROWS.filter(([k]) => bands.some(([, b]) => b[k] != null && b[k] !== ''))

  return (
    <>
      <section className="playbook-hero">
        <div>
          <div className="eyebrow"><Icon name="bulb" size={14} />The playbook</div>
          <h2>How we make shows kids actually learn from</h2>
          <p>Every script is written to — and scored against — the research on how young children pay attention, process language and learn. The writer gets these rules as instructions and the critic measures every episode against them before you ever see it.</p>
        </div>
      </section>

      <section>
        <div className="section-title"><div><h2>Age bands at a glance</h2><p className="muted small">Younger kids need slower speech, shorter sentences, longer pauses to answer, and more chances to join in.</p></div></div>
        <div className="card flush scroll-x">
          <table className="table compare">
            <thead><tr><th />{bands.map(([id, b]) => <th key={id}><span className="band-name">{b.label || id}</span><small className="muted"> {id}</small></th>)}</tr></thead>
            <tbody>
              {rows.map(([k, label, fmt]) => (
                <tr key={k}>
                  <th scope="row">{label}</th>
                  {bands.map(([id, b]) => <td key={id}>{b[k] != null && b[k] !== '' ? show(fmt(b[k])) : '—'}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {data.principles?.length > 0 && (
        <section>
          <div className="section-title"><div><h2>Principles</h2></div></div>
          <div className="grid principles">
            {data.principles.map((p, i) => (
              <article key={p.id || i} className="card principle">
                <div className="p-emoji" aria-hidden="true">{PRINCIPLE_EMOJI[i % PRINCIPLE_EMOJI.length]}</div>
                <h3>{p.name}</h3>
                <div className="p-block"><span className="p-label">Why</span><p>{p.why}</p></div>
                <div className="p-block"><span className="p-label">How we do it</span><p>{p.how}</p></div>
              </article>
            ))}
          </div>
        </section>
      )}

      {data.paces && Object.keys(data.paces).length > 0 && (
        <section>
          <div className="section-title"><div><h2>Pace profiles</h2><p className="muted small">How fast the picture moves. Speech pace always follows the age band — these control cuts, zooms and motion.</p></div></div>
          <div className="grid paces">
            {Object.entries(data.paces).map(([id, p]) => (
              <article key={id} className="card">
                <div className="card-head"><h3>{p.label || id}</h3><code>{id}</code></div>
                <div className="chips">
                  {Array.isArray(p.shot) ? <Badge size="sm" tone="blue">shots {p.shot[0]}–{p.shot[1]} s</Badge> : <Badge size="sm">shot length learned</Badge>}
                  {p.zoom != null && <Badge size="sm">zoom {String(p.zoom)}</Badge>}
                  {p.motion != null && <Badge size="sm">motion {String(p.motion)}</Badge>}
                  {p.tempo != null && <Badge size="sm">tempo {String(p.tempo)}</Badge>}
                  {p.vivid != null && <Badge size="sm">vivid {String(p.vivid)}</Badge>}
                </div>
                {p.note && <p className="small" style={{ marginTop: 10 }}>{p.note}</p>}
              </article>
            ))}
          </div>
        </section>
      )}

      <div className="two-col">
        {data.never?.length > 0 && (
          <section className="card never">
            <h2>We never do this</h2>
            <ul>{data.never.map((n, i) => <li key={i}><Icon name="x" size={14} strokeWidth={2.4} />{n}</li>)}</ul>
          </section>
        )}
        {data.segment_kinds && Object.keys(data.segment_kinds).length > 0 && (
          <section className="card">
            <h2>Building blocks</h2>
            <p className="muted small">Episodes are assembled from these segment kinds — each category has its own blueprint.</p>
            <dl className="kinds">
              {Object.entries(data.segment_kinds).map(([k, d]) => <div key={k}><dt>{k}</dt><dd>{d}</dd></div>)}
            </dl>
          </section>
        )}
      </div>
    </>
  )
}

/* =========================================================== parent feedback */
const ENJOY_LABEL = { loved: '😍 Loved it', ok: '🙂 OK', not_really: '😕 Not really' }
const RATE_LABEL = [['style', 'Look & design'], ['animation', 'Animation'], ['voices', 'Songs & voices'], ['learning', 'Learning']]

function FeedbackTab() {
  const { data, loading } = useApi('/feedback', { ms: 60000 })
  const [busy, run] = useAction()
  const [ai, setAi] = useState(null)
  const nav = useNavigate()
  if (loading && !data) return <Skeleton h={300} r={14} />
  const s = data?.summary || {}
  const stars = (v) => (v == null ? '—' : `${v.toFixed(1)} ★`)
  const make = async (topic) => {
    const ep = await run(`make-${topic}`, () => post('/feedback/make', { topic }), `Episode queued: ${topic}`)
    if (ep?.id) nav(`/episodes/${ep.id}`)
  }
  const askAi = async () => { const r = await run('ai', () => post('/feedback/ai')); if (r) setAi(r) }
  return (
    <>
      <section className="stats">
        <Stat icon="users" tone="blue" label="Responses" value={fmtNum(s.count || 0)} sub="from parents & carers" />
        <Stat icon="heart" tone="pink" label="Kids loved it" value={s.count ? `${s.loved_pct}%` : '—'} sub="said 😍 Loved it" />
        <Stat icon="palette" tone="green" label="Look & animation" value={stars(s.avg?.style)} sub={`animation ${stars(s.avg?.animation)}`} />
        <Stat icon="music" tone="amber" label="Voices & learning" value={stars(s.avg?.voices)} sub={`learning ${stars(s.avg?.learning)}`} />
      </section>

      <section className="card">
        <div className="card-head">
          <div><h2>What parents are saying</h2><p className="muted small">YouTube turns comments off on made-for-kids videos, so every description links grown-ups to a 1-minute form.</p></div>
          <div className="row-gap">
            {data?.form_url && <a className="btn sm" href={data.form_url} target="_blank" rel="noreferrer"><Icon name="external" size={14} />Open the form</a>}
            <button className="btn primary sm" disabled={!s.count || busy === 'ai'} onClick={askAi}>
              {busy === 'ai' ? <Spinner size={14} /> : <Icon name="sparkles" size={14} />}AI summary
            </button>
          </div>
        </div>
        {ai && (
          <div className="fb-ai">
            {[['themes', 'Themes'], ['changes', 'Changes to make'], ['praise', 'Keep doing'], ['topics', 'Topics asked for']].map(([k, label]) => (
              ai[k]?.length ? <div key={k}><h3 className="auto-sub">{label}</h3><ul>{ai[k].map((x, i) => <li key={i}>{x}</li>)}</ul></div> : null
            ))}
          </div>
        )}
        {!s.count && <Empty icon="inbox" title="No feedback yet">Answers appear here as soon as parents use the link in a video description.</Empty>}
      </section>

      {s.requests?.length > 0 && (
        <section className="card">
          <div className="card-head"><h2>What should Hoppy learn next?</h2><span className="muted small">Most-requested topics</span></div>
          <ul className="fb-req">
            {s.requests.map((r) => (
              <li key={r.topic}>
                <span className="grow"><b>{r.topic}</b> <Badge size="sm">{r.n}×</Badge></span>
                <button className="btn sm" disabled={busy === `make-${r.topic}`} onClick={() => make(r.topic)}>
                  {busy === `make-${r.topic}` ? <Spinner size={14} /> : <Icon name="zap" size={14} />}Make it
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data?.items?.length > 0 && (
        <section className="card flush">
          <div className="card-head pad"><h2>Every response</h2><span className="muted small">Newest first</span></div>
          <ul className="fb-list">
            {data.items.map((r) => (
              <li key={r.id}>
                <div className="fb-row-top">
                  {r.enjoyed && <Badge size="sm">{ENJOY_LABEL[r.enjoyed]}</Badge>}
                  {r.episode_id && <Link to={`/episodes/${r.episode_id}`} className="small">{r.episode_title || `#${r.episode_id}`}</Link>}
                  <span className="muted tiny grow" style={{ textAlign: 'right' }}>{r.age_band ? `${r.age_band} · ` : ''}{r.created_at ? fmtDate(r.created_at) : ''}</span>
                </div>
                <div className="fb-row-rates">
                  {RATE_LABEL.filter(([k]) => r[k]).map(([k, l]) => <span key={k} className="muted tiny">{l} {'★'.repeat(r[k])}</span>)}
                </div>
                {r.change && <p className="small"><b>Change:</b> {r.change}</p>}
                {r.request && <p className="small"><b>Next:</b> {r.request}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

const TABS = [['analytics', 'Analytics', null, 'chart'], ['growth', 'Growth', null, 'rocket'], ['feedback', 'Feedback', null, 'heart'], ['playbook', 'Playbook', null, 'bulb']]

export default function Insights() {
  const { tab } = useParams()
  const nav = useNavigate()
  if (!TABS.some((t) => t[0] === tab)) return <Navigate to="/insights/analytics" replace />
  return (
    <div className="page">
      <PageHead title="Insights" sub="How episodes perform, how the channel grows, and the child-development rules every script follows." />
      <Tabs value={tab} onChange={(t) => nav(`/insights/${t}`)} tabs={TABS} />
      <div className="tab-page">
        {tab === 'analytics' && <Analytics />}
        {tab === 'growth' && <Growth />}
        {tab === 'feedback' && <FeedbackTab />}
        {tab === 'playbook' && <Playbook />}
      </div>
    </div>
  )
}
