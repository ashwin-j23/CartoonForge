import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { post } from '../api'
import BookBrowser from '../components/BookBrowser'
import Icon from '../components/icons'
import { Badge, Empty, fmtDate, fmtNum, PageHead, Skeleton, Spinner, Tabs, useAction, useApi, useCategoryMap } from '../components/ui'

const BAND = { toddler: 'Toddlers 1-3', preschool: 'Preschool 3-5', early: 'Early 5-8', big: 'Big kids 8-12' }

function Trends() {
  const { data, loading, reload } = useApi('/trends', { ms: 8000 })
  const [busy, run] = useAction()
  const [, catMap] = useCategoryMap()
  const nav = useNavigate()
  const ideas = (data?.ideas || []).filter((i) => !i.used)
  const usedIdeas = (data?.ideas || []).filter((i) => i.used)
  const snap = data?.snapshot || {}
  const scanning = data?.scanning || busy === 'scan'

  const scan = async () => {
    const r = await run('scan', () => post('/trends/scan'), (x) => (x?.started ? 'Scanning trends — about 1-2 minutes' : x?.detail))
    if (r) setTimeout(() => reload(true), 2000)
  }
  const make = async (t) => {
    const ep = await run(`make-${t.id}`, () => post(`/trends/${t.id}/make`), 'Episode queued from this trend')
    if (ep?.id) nav(`/episodes/${ep.id}`)
  }
  const signals = [
    ['search', 'YouTube searches', `${(snap.suggest || []).length} phrases · US, IN, GB, BR`],
    ['zap', 'Hot kids videos', data?.has_youtube_key ? `${(snap.hot || []).length} from the last 14 days` : 'Add YOUTUBE_API_KEY in Settings → Keys'],
    ['book', 'Wikipedia interest', `${(snap.wiki || []).length} subjects tracked`],
    ['calendar', 'World days', `${(snap.upcoming || []).length} in the next 3 weeks`],
  ]

  return (
    <>
      <div className="toolbar">
        <p className="muted small grow">{snap.at ? <>Last scan {fmtDate(snap.at)} · {snap.ideas} ideas · {snap.seconds}s. Scans run daily by themselves; the planner uses these for most new episodes.</> : 'What parents search and children watch right now, turned into original episode ideas.'}</p>
        <button className="btn primary" onClick={scan} disabled={scanning}>{scanning ? <Spinner /> : <Icon name="refresh" size={16} />}{scanning ? 'Scanning…' : 'Scan now'}</button>
      </div>

      <div className="signal-row">
        {signals.map(([icon, t, s]) => (
          <div key={t} className="signal"><span className="signal-ico"><Icon name={icon} size={16} /></span><div><b>{t}</b><small>{s}</small></div></div>
        ))}
      </div>

      <section className="card flush">
        <div className="card-head pad"><h2>Episode ideas from trends</h2><span className="muted small">Best first · original angles only, never copied shows or brands</span></div>
        {loading && !data ? <div className="pad"><Skeleton h={64} count={5} r={10} style={{ marginBottom: 8 }} /></div> : ideas.length === 0 ? (
          <Empty icon="trending" title="No trend ideas yet" action={<button className="btn" onClick={scan} disabled={scanning}>Scan now</button>}>
            A scan reads YouTube search suggestions, rising Wikipedia subjects and upcoming world days{data?.has_youtube_key ? ', plus this week’s hottest kids videos' : ''}. With an AI key it writes original ideas; without one it ranks the raw signals.
          </Empty>
        ) : (
          <ul className="trend-list">
            {ideas.map((t) => {
              const c = catMap[t.category] || {}
              const q = new URLSearchParams({ topic: t.topic, ...(t.category ? { category: t.category } : {}), ...(t.age_band ? { band: t.age_band } : {}) })
              return (
                <li key={t.id} className="trend-row">
                  <div className="trend-score" title="Trend strength × fit">{t.score}</div>
                  <div className="trend-body">
                    <b>{t.topic}</b>
                    <div className="chips">
                      <Badge size="sm">{c.emoji} {c.name || t.category}</Badge>
                      <Badge size="sm">{BAND[t.age_band] || t.age_band}</Badge>
                      {t.rising && <Badge size="sm" tone="green" icon="trending">Rising</Badge>}
                      {t.evergreen && <Badge size="sm" tone="blue">Evergreen</Badge>}
                    </div>
                    {t.why && <p className="small muted">Why: {t.why}</p>}
                    {t.angle && <p className="small">Our angle: {t.angle}</p>}
                  </div>
                  <div className="trend-act">
                    <button className="btn primary sm" disabled={busy === `make-${t.id}`} onClick={() => make(t)}>
                      {busy === `make-${t.id}` ? <Spinner size={14} /> : <Icon name="zap" size={14} />}Make it
                    </button>
                    <Link className="btn ghost sm" to={`/create?${q}`}>Customise</Link>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <div className="trend-raw">
        <section className="card">
          <h3>What parents search</h3>
          <p className="muted tiny">YouTube autocomplete</p>
          <div className="chips">{(snap.suggest || []).slice(0, 40).map((s) => <Badge key={s.phrase} size="sm" title={(s.regions || []).join(', ')}>{s.phrase}{s.hits > 1 ? ` ×${s.hits}` : ''}</Badge>)}</div>
          {!(snap.suggest || []).length && <p className="muted small">Run a scan to collect search phrases.</p>}
        </section>
        <section className="card">
          <h3>Wikipedia: this week vs before</h3>
          <ul className="plain-list">{(snap.wiki || []).slice(0, 12).map((w) => <li key={w.subject}><b>{w.subject}</b> <span className={w.ratio > 1.2 ? 'up' : 'muted'}>×{w.ratio}</span> <span className="muted">· {fmtNum(w.daily)}/day</span></li>)}</ul>
          {!(snap.wiki || []).length && <p className="muted small">No subjects tracked yet.</p>}
        </section>
        {(snap.hot || []).length > 0 && (
          <section className="card">
            <h3>Hottest kids videos (14 days)</h3>
            <ul className="plain-list">{snap.hot.slice(0, 12).map((h) => <li key={h.id}><a href={`https://youtu.be/${h.id}`} target="_blank" rel="noreferrer">{h.title}</a> <span className="muted">· {fmtNum(h.views_per_day)}/day · {h.region}</span></li>)}</ul>
          </section>
        )}
      </div>
      {usedIdeas.length > 0 && <p className="muted small">Already made: {usedIdeas.map((u) => u.topic).join(' · ')}</p>}
    </>
  )
}

function Books() {
  const nav = useNavigate()
  return (
    <>
      <section className="feature-strip">
        {[['globe', 'Public domain', 'Books from Project Gutenberg that anyone may adapt.'],
          ['tag', 'Credited automatically', 'Title, author and source go in every description.'],
          ['heart', 'Scary parts softened', 'Peril and cruelty are gentled for little viewers.'],
          ['users', 'Our cast acts the roles', 'Familiar friends play the story’s characters.']].map(([i, t, d]) => (
          <div key={t}><span className="fs-ico"><Icon name={i} size={16} /></span><p><b>{t}</b>{d}</p></div>
        ))}
      </section>
      <BookBrowser renderAction={(s, b) => (
        <button className="btn primary sm" onClick={() => nav(`/create?${new URLSearchParams({ book: b.id, index: s.index, story: s.title || `Story ${s.index + 1}`, bookTitle: b.title })}`)}>
          <Icon name="film" size={14} />Animate this story
        </button>
      )} />
    </>
  )
}

export default function Library() {
  const { tab } = useParams()
  const nav = useNavigate()
  if (!['trends', 'books'].includes(tab)) return <Navigate to="/library/trends" replace />
  return (
    <div className="page">
      <PageHead title="Library" sub="Idea sources for new episodes: what kids are into right now, and classic stories our cast can act out." />
      <Tabs value={tab} onChange={(t) => nav(`/library/${t}`)} tabs={[['trends', 'Trends', null, 'trending'], ['books', 'Books', null, 'book']]} />
      <div className="tab-page">{tab === 'trends' ? <Trends /> : <Books />}</div>
    </div>
  )
}
