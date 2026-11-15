import { Link, useNavigate } from 'react-router-dom'
import { mediaUrl, post } from '../api'
import AutomationCard from '../components/AutomationCard'
import { EpisodeCard, MiniCard, Thumb } from '../components/EpisodeCard'
import Icon from '../components/icons'
import {
  ago, Badge, Empty, fmtDate, fmtNum, isLive, SafeImg, Skeleton, Spinner, Stat, StatusPill, until, useAction, useApi, useCategoryMap,
} from '../components/ui'

const PIPE = [
  ['Writing', ['planned', 'writing', 'scripted'], 'blue'],
  ['Rendering', ['rendering'], 'violet'],
  ['Review', ['review'], 'amber'],
  ['Scheduled', ['approved', 'publishing'], 'green'],
]

function greeting() {
  const h = new Date().getHours()
  if (h < 5) return 'Burning the midnight oil'
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

function AttentionItem({ icon, tone, title, children, to, action }) {
  const body = (
    <>
      <span className={`att-ico t-${tone}`}><Icon name={icon} size={18} /></span>
      <span className="att-text"><b>{title}</b>{children && <small>{children}</small>}</span>
      {action || (to && <Icon name="chevronRight" size={18} className="att-go" />)}
    </>
  )
  return to ? <Link to={to} className="att-item">{body}</Link> : <div className="att-item">{body}</div>
}

export default function Home() {
  const nav = useNavigate()
  const ov = useApi('/overview', { ms: (d) => (d?.worker?.busy ? 5000 : 30000) })
  const eps = useApi('/episodes', { ms: (d) => (Array.isArray(d) && d.some(isLive) ? 5000 : 30000) })
  const [, catMap] = useCategoryMap()
  const settings = useApi('/settings', { quiet: true }).data
  const [busy, run] = useAction()

  const o = ov.data
  const s = o?.settings_summary
  const list = Array.isArray(eps.data) ? eps.data : []
  const counts = o?.counts || {}
  const ch = o?.channel
  const bar = settings?.quality_bar
  const review = list.filter((e) => e.status === 'review')
  const failed = list.filter((e) => e.status === 'failed')
  const published = list.filter((e) => e.status === 'published').slice(0, 4)
  const inProd = (counts.planned || 0) + (counts.writing || 0) + (counts.scripted || 0) + (counts.rendering || 0)

  const surprise = async () => {
    const ep = await run('surprise', () => post('/episodes', {}), 'Episode queued — the planner picked a topic')
    if (ep?.id != null) nav(`/episodes/${ep.id}`)
  }

  const attention = []
  if (settings?.kill_switch) attention.push(<AttentionItem key="kill" icon="power" tone="red" title="Kill switch is on — the studio is paused" to="/settings">Nothing will be written, rendered or published until you resume.</AttentionItem>)
  if (review.length) attention.push(<AttentionItem key="rev" icon="eye" tone="amber" title={`${review.length} episode${review.length === 1 ? '' : 's'} waiting for your review`} to="/episodes?status=review">{review.slice(0, 3).map((e) => e.title || e.topic).join(' · ')}</AttentionItem>)
  if (failed.length) attention.push(<AttentionItem key="fail" icon="alertCircle" tone="red" title={`${failed.length} episode${failed.length === 1 ? '' : 's'} failed`} to="/episodes?status=failed">{failed[0]?.error || 'Open to retry or rewrite.'}</AttentionItem>)
  for (const [i, w] of (o?.warnings || []).entries()) attention.push(<AttentionItem key={`w${i}`} icon="alert" tone="amber" title={w} to="/settings" />)
  if (o && !ch?.connected) attention.push(<AttentionItem key="yt" icon="plug" tone="blue" title="Connect your YouTube channel" to="/channel">So the studio can upload, schedule and learn from analytics.</AttentionItem>)

  return (
    <div className="page home">
      <section className="home-hero">
        <div className="home-hero-text">
          <div className="eyebrow"><Icon name="sun" size={14} />{greeting()}</div>
          <h1>{s?.channel_name || 'Sunny Sprouts'} Studio</h1>
          <p className="sub">
            {s ? <>Ages <b>{s.age_band}</b> · <b>{s.target_minutes}</b>-minute episodes · {s.autopilot ? 'Autopilot publishes episodes that clear the bar' : 'Every episode waits for your review'}</> : <Skeleton h={16} w={320} />}
          </p>
          <div className="hero-actions">
            <Link to="/create" className="btn primary lg"><Icon name="sparkles" size={18} />Create an episode</Link>
            <button className="btn lg" onClick={surprise} disabled={busy === 'surprise'}>
              {busy === 'surprise' ? <Spinner /> : <Icon name="dice" size={18} />}Surprise me
            </button>
          </div>
          <div className="hero-sources">
            <Link to="/library/trends"><Icon name="trending" size={15} />From a trend</Link>
            <Link to="/library/books"><Icon name="book" size={15} />From a book</Link>
            <Link to="/characters"><Icon name="users" size={15} />Characters</Link>
            <Link to="/looks"><Icon name="palette" size={15} />Looks</Link>
          </div>
        </div>
        <div className="home-next">
          <div className="home-next-label"><Icon name="calendar" size={14} />Next publish</div>
          {!o ? <Skeleton h={60} /> : o.next_publish ? (
            <Link to={`/episodes/${o.next_publish.id}`} className="next-pub">
              <b>{o.next_publish.title}</b>
              <span>{fmtDate(o.next_publish.publish_at)}</span>
              <Badge tone="green" icon="clock" size="sm">in {until(o.next_publish.publish_at)}</Badge>
            </Link>
          ) : (
            <div className="next-pub empty-next">
              <b>Nothing scheduled</b>
              <span>Approve an episode in review to fill the next slot.</span>
            </div>
          )}
          <div className="hero-sprites" aria-hidden="true">
            {['sunny', 'hoppy', 'mimi'].map((id, i) => <SafeImg key={id} src={`/api/cast/${id}.png?emotion=${i === 1 ? 'excited' : 'happy'}&arms=${i === 0 ? 'wave' : 'down'}&size=200`} className={`sprite s${i}`} />)}
          </div>
        </div>
      </section>

      <section className="stats">
        {!o ? <Skeleton h={98} count={4} r={14} /> : (
          <>
            <Stat icon="eye" tone="amber" label="Waiting for review" value={counts.review || 0} />
            <Stat icon="film" tone="violet" label="In production" value={inProd} sub={o.worker?.busy && o.worker.current ? `${o.worker.current.stage}…` : null} />
            <Stat icon="calendar" tone="green" label="Scheduled" value={(counts.approved || 0) + (counts.publishing || 0)} />
            {ch?.connected
              ? <Stat icon="users" tone="blue" label="Subscribers" value={fmtNum(ch.subscribers)} sub={`${fmtNum(ch.views)} views`} />
              : <Stat icon="star" tone="pink" label="Published" value={counts.published || 0} sub={counts.failed ? `${counts.failed} failed` : null} />}
          </>
        )}
      </section>

      <AutomationCard />

      <div className="home-grid">
        <section className="card">
          <div className="card-head">
            <h2>Needs attention</h2>
            {attention.length > 0 && <Badge tone="amber" size="sm">{attention.length}</Badge>}
          </div>
          {!o || !eps.data ? <Skeleton h={52} count={3} r={10} style={{ marginBottom: 8 }} /> : attention.length ? (
            <div className="att-list">{attention}</div>
          ) : (
            <Empty compact icon="checkCircle" title="All clear">Nothing needs you right now. The studio keeps the pipeline full on its own.</Empty>
          )}
        </section>

        <section className="card">
          <div className="card-head">
            <h2>Review queue</h2>
            <Link to="/episodes?status=review" className="link-sm">View all<Icon name="arrowRight" size={14} /></Link>
          </div>
          {!eps.data ? <Skeleton h={64} count={3} r={10} style={{ marginBottom: 8 }} /> : review.length === 0 ? (
            <Empty compact icon="inbox" title="Inbox zero">Finished episodes land here for a final look before publishing.</Empty>
          ) : (
            <ul className="queue">
              {review.slice(0, 5).map((e) => (
                <li key={e.id}>
                  <Link to={`/episodes/${e.id}`} className="queue-item">
                    <Thumb ep={e} emoji={catMap[e.category]?.emoji} className="queue-thumb" />
                    <span className="queue-text"><b>{e.title || e.topic}</b><small>{catMap[e.category]?.name || e.category} · {ago(e.created_at)}</small></span>
                    <span className="btn sm">Review</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="card">
        <div className="card-head">
          <h2>Pipeline</h2>
          <Link to="/episodes?view=board" className="link-sm">Open board<Icon name="arrowRight" size={14} /></Link>
        </div>
        {!eps.data ? <div className="board"><Skeleton h={200} count={4} r={12} /></div> : list.length === 0 ? (
          <Empty icon="sparkles" title="No episodes yet" action={<Link className="btn primary" to="/create"><Icon name="plus" size={16} />Create your first episode</Link>}>
            It takes a few minutes to write and render one.
          </Empty>
        ) : (
          <div className="board compact">
            {PIPE.map(([title, sts, tone]) => {
              const items = list.filter((e) => sts.includes(e.status))
              return (
                <div className={`col t-${tone}`} key={title}>
                  <div className="col-head"><span className="col-dot" />{title}<span className="col-count">{items.length}</span></div>
                  <div className="col-body">
                    {items.length === 0 && <div className="col-empty">Nothing here</div>}
                    {items.slice(0, 4).map((e) => <MiniCard key={e.id} ep={e} catEmoji={catMap[e.category]?.emoji} bar={bar} />)}
                    {items.length > 4 && <Link className="col-more" to={`/episodes?status=${sts[0] === 'planned' ? 'writing' : sts[0]}`}>+{items.length - 4} more</Link>}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {published.length > 0 && (
        <section>
          <div className="section-title">
            <div><h2>Recently published</h2></div>
            <Link to="/episodes?status=published" className="link-sm">All published<Icon name="arrowRight" size={14} /></Link>
          </div>
          <div className="grid cards">{published.map((e) => <EpisodeCard key={e.id} ep={e} cat={catMap[e.category]} bar={bar} />)}</div>
        </section>
      )}

      {ch?.connected && (
        <section className="card channel-mini">
          {ch.thumb ? <img src={mediaUrl(ch.thumb)} alt="" className="ch-thumb" /> : <span className="ch-thumb ph"><Icon name="tv" /></span>}
          <div className="grow">
            <b>{ch.title}</b>
            <div className="muted small">{fmtNum(ch.subscribers)} subscribers · {fmtNum(ch.views)} views · {fmtNum(ch.videos)} videos</div>
          </div>
          <StatusPill status="published" small />
          <Link to="/insights/analytics" className="btn sm"><Icon name="chart" size={15} />Analytics</Link>
        </section>
      )}
    </div>
  )
}
