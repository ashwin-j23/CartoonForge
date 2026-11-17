import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { post } from '../api'
import { EpisodeCard, KindBadge, MiniCard, Thumb } from '../components/EpisodeCard'
import Icon from '../components/icons'
import { AnimationBadge, StyleBadge, useStyles } from '../components/looks'
import {
  ago, Empty, fmtDur, isLive, PageHead, ScoreBadge, Seg, Skeleton, SkeletonCards, shownStatus, STATUS, STATUS_ORDER, StatusPill, useAction, useApi, useCategoryMap,
} from '../components/ui'

const BOARD = [
  ['Writing', ['planned', 'writing', 'scripted'], 'blue'],
  ['Rendering', ['rendering'], 'violet'],
  ['Review', ['review'], 'amber'],
  ['Scheduled', ['approved', 'publishing'], 'green'],
  ['Upcoming on YouTube', ['upcoming'], 'blue'],
  ['Live on YouTube', ['published'], 'pink'],
  ['Failed', ['failed', 'rejected'], 'red'],
]
const KINDS = [['', 'All'], ['episode', 'Episodes'], ['short', 'Shorts'], ['compilation', 'Compilations']]

export default function Episodes() {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') || ''
  const kind = params.get('kind') || ''
  const view = params.get('view') || (status ? 'grid' : 'board')
  const [q, setQ] = useState('')
  const [busy, run] = useAction()
  const { data, loading, reload } = useApi('/episodes', { ms: (d) => (Array.isArray(d) && d.some(isLive) ? 5000 : 30000) })
  const [, catMap] = useCategoryMap()
  const bar = useApi('/settings', { quiet: true }).data?.quality_bar
  const { map: styleMap } = useStyles()

  const setParam = (k, v) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }) }

  const all = Array.isArray(data) ? data : []
  const counts = useMemo(() => {
    const c = {}
    for (const e of all) if (!kind || (e.kind || 'episode') === kind) c[shownStatus(e)] = (c[shownStatus(e)] || 0) + 1
    return c
  }, [all, kind])
  const base = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return all.filter((e) => (!kind || (e.kind || 'episode') === kind)
      && (!needle || [e.title, e.topic, e.category, String(e.id)].some((x) => x && String(x).toLowerCase().includes(needle))))
  }, [all, q, kind])
  const list = status ? base.filter((e) => shownStatus(e) === status) : base
  const reviewQ = !status ? base.filter((e) => e.status === 'review') : []
  const rest = !status ? base.filter((e) => e.status !== 'review') : list
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const retry = async (ep, how) => {
    const r = await run(`retry-${ep.id}`, () => post(`/episodes/${ep.id}/${how}`),
      how === 'render' ? 'Rendering again' : 'Writing it again')
    if (r) reload()
  }

  return (
    <div className={`page ${view === 'board' ? 'wide' : ''}`}>
      <PageHead title="Episodes" sub="Everything the studio has written, rendered or published. Review queue first.">
        <Link to="/create" className="btn primary"><Icon name="plus" size={16} />New episode</Link>
      </PageHead>

      <div className="toolbar">
        <label className="search-box">
          <Icon name="search" size={16} />
          <input type="search" placeholder="Search title, topic or #id" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search episodes" />
        </label>
        <Seg value={kind} onChange={(v) => setParam('kind', v)} size="sm" options={KINDS} label="Kind" />
        <div className="spacer" />
        <Seg value={view} onChange={(v) => setParam('view', v)} size="sm" label="View"
          options={[['board', 'Board', 'board'], ['grid', 'Grid', 'grid'], ['list', 'List', 'list']]} />
      </div>

      {view !== 'board' && (
        <div className="chips filter" role="toolbar" aria-label="Filter by status">
          <button className={`chip ${!status ? 'on' : ''}`} onClick={() => setParam('status', '')}>All<span className="chip-n">{total}</span></button>
          {STATUS_ORDER.filter((s) => counts[s] || s === status || s === 'review').map((s) => (
            <button key={s} className={`chip ${status === s ? 'on' : ''}`} onClick={() => setParam('status', s)}>
              <span className={`dot t-${STATUS[s].tone}`} />{STATUS[s].label}<span className="chip-n">{counts[s] || 0}</span>
            </button>
          ))}
        </div>
      )}

      {loading && !data ? (view === 'board' ? <div className="board"><Skeleton h={320} count={5} r={12} /></div> : <SkeletonCards n={8} />) : base.length === 0 ? (
        <Empty icon="film" title={q ? 'Nothing matches your search' : 'No episodes yet'}
          action={<Link className="btn primary" to="/create"><Icon name="plus" size={16} />Create an episode</Link>}>
          {q ? 'Try a different word, or clear the search.' : 'They show up here as soon as the planner queues them.'}
        </Empty>
      ) : view === 'board' ? (
        <div className="board">
          {BOARD.map(([title, sts, tone]) => {
            const items = base.filter((e) => sts.includes(shownStatus(e)))
            return (
              <div className={`col t-${tone} ${items.length ? '' : 'is-empty'}`} key={title}>
                <div className="col-head"><span className="col-dot" />{title}<span className="col-count">{items.length}</span></div>
                <div className="col-body">
                  {items.length === 0 && <div className="col-empty">Nothing here</div>}
                  {items.slice(0, title === 'Live on YouTube' ? 12 : 50).map((e) => (
                    <MiniCard key={e.id} ep={e} catEmoji={catMap[e.category]?.emoji} bar={bar}
                      onRetry={title === 'Failed' ? retry : undefined} retrying={busy === `retry-${e.id}`} />
                  ))}
                  {title === 'Live on YouTube' && items.length > 12 && <button className="col-more" onClick={() => setParams({ view: 'grid', status: 'published' })}>+{items.length - 12} more</button>}
                </div>
              </div>
            )
          })}
        </div>
      ) : list.length === 0 ? (
        <Empty icon="filter" title={`No ${STATUS[status]?.label.toLowerCase() || status} episodes`} action={<button className="btn" onClick={() => setParam('status', '')}>Show all</button>} />
      ) : (
        <>
          {reviewQ.length > 0 && (
            <section className="review-q">
              <div className="section-title"><div><h2><Icon name="eye" size={18} />Review queue <span className="count-pill">{reviewQ.length}</span></h2><p className="muted small">Watch, read the scorecard, then approve or reject.</p></div></div>
              <EpisodeList list={reviewQ} view={view} catMap={catMap} bar={bar} styleMap={styleMap} />
            </section>
          )}
          {rest.length > 0 && (
            <section>
              {reviewQ.length > 0 && <div className="section-title"><div><h2>Everything else</h2></div></div>}
              <EpisodeList list={rest} view={view} catMap={catMap} bar={bar} styleMap={styleMap} />
            </section>
          )}
        </>
      )}
    </div>
  )
}

function EpisodeList({ list, view, catMap, bar, styleMap }) {
  if (view === 'grid') return <div className="grid cards">{list.map((e) => <EpisodeCard key={e.id} ep={e} cat={catMap[e.category]} bar={bar} />)}</div>
  return (
    <div className="card flush">
      <ul className="ep-rows">
        {list.map((e) => (
          <li key={e.id}>
            <Link to={`/episodes/${e.id}`} className="ep-row">
              <Thumb ep={e} emoji={catMap[e.category]?.emoji} className="row-thumb" />
              <span className="ep-row-main">
                <b>{e.title || e.topic}</b>
                <span className="ep-row-meta">
                  <span>#{e.id}</span>
                  {catMap[e.category] && <span>{catMap[e.category].emoji} {catMap[e.category].name}</span>}
                  {e.age_band && <span>{e.age_band}</span>}
                  {e.duration ? <span>{fmtDur(e.duration)}</span> : null}
                  <span>{ago(e.created_at)}</span>
                </span>
              </span>
              <span className="ep-row-badges">
                <KindBadge kind={e.kind} />
                {((e.art_style && e.art_style !== 'auto') || e.rendered_style) && <StyleBadge id={e.art_style} rendered={e.rendered_style} map={styleMap} size="sm" />}
                {e.animation && e.animation !== 'code' && <AnimationBadge mode={e.animation} size="sm" />}
                <ScoreBadge score={e.score} bar={bar} />
                <StatusPill status={shownStatus(e)} small />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
