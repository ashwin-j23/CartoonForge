import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { post } from '../api'
import { ChannelBadge, chOf, CHANNELS, inChannel, itemLink, useChannel } from '../components/channel'
import { Thumb } from '../components/EpisodeCard'
import Icon from '../components/icons'
import { goLiveAt, StageChip, STAGES, stageOf } from '../components/stage'
import {
  ago, Empty, fmtDate, fmtDur, fmtNum, isLive, PageHead, Progress, ScoreBadge, Seg, SkeletonCards, until, useAction, useApi, useCategoryMap,
} from '../components/ui'

// tabs across the top: what each one holds, in pipeline order
const TABS = [
  ['all', 'All', null],
  ['production', 'In production', ['production']],
  ['review', 'Review', ['review']],
  ['scheduled', 'Scheduled', ['scheduled', 'uploading', 'upcoming']],
  ['live', 'Live', ['live']],
  ['failed', 'Needs attention', ['failed']],
  ['rejected', 'Rejected', ['rejected']],
]
// sections on the "All" tab, in the order they matter to you
const SECTIONS = [
  ['review', 'Needs your review', 'Watch it, read the scorecard, then approve or reject.', ['review']],
  ['failed', 'Needs attention', 'Something went wrong. Retry from here or open it.', ['failed']],
  ['production', 'In production', 'Being written and rendered right now.', ['production']],
  ['scheduled', 'Going live next', 'In order. Uploaded videos go public by themselves at their time.', ['uploading', 'upcoming', 'scheduled']],
  ['live', 'Live on YouTube', 'Public now, newest first.', ['live']],
]
// old links (?status=…) from Home and elsewhere
const LEGACY = { review: 'review', failed: 'failed', rejected: 'rejected', published: 'live', approved: 'scheduled', publishing: 'scheduled',
  planned: 'production', writing: 'production', scripted: 'production', rendering: 'production' }
const KINDS = [['', 'All'], ['episode', 'Episodes'], ['short', 'Shorts'], ['compilation', 'Compilations'], ['dub', 'Dubs']]
const SORTS = [['smart', 'Best order'], ['newest', 'Newest'], ['views', 'Most views']]
const LIVE_PREVIEW = 8
const SOON = ['scheduled', 'uploading', 'upcoming']

const shortWhen = (iso) => fmtDate(iso, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
const ts = (iso) => new Date(iso || 0).getTime()

function smartSort(list) {
  return [...list].sort((a, b) => {
    if (a._stage === 'live' && b._stage === 'live') return ts(goLiveAt(b)) - ts(goLiveAt(a))   // newest live first
    if (SOON.includes(a._stage) && SOON.includes(b._stage)) return ts(goLiveAt(a)) - ts(goLiveAt(b))   // soonest first
    return ts(b.created_at) - ts(a.created_at)
  })
}

export default function Episodes() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || LEGACY[params.get('status')] || 'all'
  const kind = params.get('kind') || ''
  const view = params.get('view') === 'list' ? 'list' : 'cards'
  const sort = params.get('sort') || 'smart'
  const [q, setQ] = useState('')
  const [showAllLive, setShowAllLive] = useState(false)
  const [busy, run] = useAction()
  const [channel] = useChannel()
  const { data, loading, reload } = useApi('/episodes?channel=all', { ms: (d) => (Array.isArray(d) && d.some(isLive) ? 5000 : 30000) })
  const [, catMap] = useCategoryMap()
  const bar = useApi('/settings', { quiet: true }).data?.quality_bar

  const setParam = (k, v) => {
    const n = new URLSearchParams(params)
    n.delete('status')
    if (v) n.set(k, v); else n.delete(k)
    setParams(n, { replace: true })
  }

  // a dub that isn't made yet only shows on the World view (on "All" it would bury the English pipeline)
  const queuedDub = (e) => e.kind === 'dub' && e.status === 'scripted' && !e.error
  const all = useMemo(() => (Array.isArray(data) ? data : []).filter((e) => inChannel(e, channel) && !(channel === 'all' && queuedDub(e)))
    .map((e) => ({ ...e, _stage: stageOf(e) })), [data, channel])
  const hiddenDubs = channel === 'all' ? (Array.isArray(data) ? data : []).filter(queuedDub).length : 0
  const base = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return all.filter((e) => (!kind || (e.kind || 'episode') === kind)
      && (!needle || [e.title, e.topic, e.category, String(e.id), e.lang_name, e.lang].some((x) => x && String(x).toLowerCase().includes(needle))))
  }, [all, q, kind])
  const counts = useMemo(() => {
    const c = { all: base.length }
    for (const [id, , stages] of TABS) if (stages) c[id] = base.filter((e) => stages.includes(e._stage)).length
    return c
  }, [base])
  const sorted = (list) => (sort === 'views' ? [...list].sort((a, b) => (b.views || 0) - (a.views || 0))
    : sort === 'newest' ? [...list].sort((a, b) => ts(b.created_at) - ts(a.created_at)) : smartSort(list))

  const retry = async (ep, how) => {
    const r = chOf(ep) === 'world'
      ? await run(`retry-${ep.id}`, () => post(`/episodes/${ep.episode_id}/edition`, { lang: ep.lang }), `${ep.lang_name} dub queued again`)
      : await run(`retry-${ep.id}`, () => post(`/episodes/${ep.id}/${how}`), how === 'render' ? 'Rendering again' : 'Writing it again')
    if (r) reload()
  }
  const live = all.filter((e) => e._stage === 'live')
  const liveEps = live.filter((e) => !['short', 'dub'].includes(e.kind || 'episode')).length
  const liveDubs = live.filter((e) => e.kind === 'dub').length
  const totalViews = live.reduce((n, e) => n + (e.views || 0), 0)
  const next = all.filter((e) => SOON.includes(e._stage) && goLiveAt(e)).sort((a, b) => ts(goLiveAt(a)) - ts(goLiveAt(b)))[0]
  const waiting = all.filter((e) => SOON.includes(e._stage)).length
  const review = all.filter((e) => e._stage === 'review').length

  const tabDef = TABS.find(([id]) => id === tab) || TABS[0]
  const visibleTabs = TABS.filter(([id]) => id === 'all' || counts[id] || id === tab || ['review', 'scheduled', 'live'].includes(id))
  const cardProps = { catMap, bar, onRetry: retry, busy }

  return (
    <div className="page">
      <PageHead title={channel === 'all' ? 'Episodes' : `Episodes · ${CHANNELS[channel].label}`}
        sub={channel === 'world' ? 'Dubs on Hoppy Hop Hop World: one row per language, made from the English episode.'
          : channel === 'en' ? 'Everything on the English channel, from first draft to live on YouTube.'
          : 'Both channels. The badge on each video says where it goes: 🐸 English or 🌍 World.'}>
        <Link to="/calendar" className="btn"><Icon name="calendar" size={16} />Schedule</Link>
        <Link to="/create" className="btn primary"><Icon name="plus" size={16} />New episode</Link>
      </PageHead>

      {!data && (
        <div className="eps-hero" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="eps-hero-item"><span className="eps-hero-ico skel" /><span><b>—</b><small>&nbsp;</small></span></div>
          ))}
        </div>
      )}
      {data && (
        <div className="eps-hero">
          <button type="button" className="eps-hero-item st-live" onClick={() => setParam('tab', 'live')}>
            <span className="eps-hero-ico"><Icon name="checkCircle" size={18} /></span>
            <span><b>{live.length}</b><small>{channel === 'world' ? `dubs live in ${new Set(live.map((e) => e.lang)).size} languages` : `live · ${liveEps} episodes, ${live.length - liveEps - liveDubs} Shorts${liveDubs ? `, ${liveDubs} dubs` : ''}`}</small></span>
          </button>
          <button type="button" className="eps-hero-item st-live" onClick={() => setParams({ tab: 'live', sort: 'views', ...(kind ? { kind } : {}) }, { replace: true })}>
            <span className="eps-hero-ico"><Icon name="eye" size={18} /></span>
            <span><b>{fmtNum(totalViews)}</b><small>views on live videos</small></span>
          </button>
          <button type="button" className="eps-hero-item st-scheduled" onClick={() => setParam('tab', 'scheduled')}>
            <span className="eps-hero-ico"><Icon name="clock" size={18} /></span>
            <span>{next ? <><b>in {until(goLiveAt(next))}</b><small className="ellipsis" title={next.title}>{waiting} waiting · next: {next.title}</small></>
              : <><b>—</b><small>nothing waiting to go live</small></>}</span>
          </button>
          <button type="button" className={`eps-hero-item ${review ? 'st-review' : 'st-rejected'}`} onClick={() => setParam('tab', 'review')}>
            <span className="eps-hero-ico"><Icon name="eye" size={18} /></span>
            <span><b>{review}</b><small>{review ? 'waiting for your review' : 'nothing to review'}</small></span>
          </button>
        </div>
      )}

      <nav className="eps-tabs" aria-label="Filter by stage">
        {visibleTabs.map(([id, label, stages]) => (
          <button key={id} type="button" className={`eps-tab ${stages ? `st-${id === 'scheduled' ? 'scheduled' : stages[0]}` : ''} ${tab === id ? 'on' : ''}`}
            aria-pressed={tab === id} onClick={() => { setParam('tab', id === 'all' ? '' : id); setShowAllLive(false) }}>
            {stages && <span className="eps-tab-dot" />}{label}<span className="eps-tab-n">{counts[id] || 0}</span>
          </button>
        ))}
      </nav>

      {hiddenDubs > 0 && (
        <p className="muted small eps-note"><span className="ch-badge world">🌍</span> {hiddenDubs} dub{hiddenDubs === 1 ? '' : 's'} waiting to be made are hidden here: switch the channel to <b>Hoppy Hop Hop World</b> to see them.</p>
      )}
      <div className="eps-toolbar">
        <label className="search-box">
          <Icon name="search" size={16} />
          <input type="search" placeholder="Search title, topic or #id" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search episodes" />
        </label>
        <Seg value={kind} onChange={(v) => setParam('kind', v)} size="sm" options={KINDS} label="Kind" />
        <div className="spacer" />
        <label className="eps-sort">
          <span>Sort</span>
          <select value={sort} onChange={(e) => setParam('sort', e.target.value === 'smart' ? '' : e.target.value)}>
            {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <Seg value={view} onChange={(v) => setParam('view', v === 'cards' ? '' : v)} size="sm" label="View"
          options={[['cards', 'Cards', 'grid'], ['list', 'List', 'list']]} />
      </div>

      {loading && !data ? <SkeletonCards n={8} h={250} className="eps-grid" /> : base.length === 0 ? (
        <Empty icon="film" title={q ? 'Nothing matches your search' : 'No episodes yet'}
          action={<Link className="btn primary" to="/create"><Icon name="plus" size={16} />Create an episode</Link>}>
          {q ? 'Try a different word, or clear the search.' : 'They show up here as soon as the planner queues them.'}
        </Empty>
      ) : tab === 'all' ? (
        SECTIONS.map(([id, title0, hint0, stages]) => {
          const [title, hint] = channel === 'world' && id === 'production' ? ['Waiting to be dubbed', 'Each language is dubbed up to 3 days before the English episode goes live.'] : [title0, hint0]
          const full = sorted(base.filter((e) => stages.includes(e._stage)))
          if (!full.length) return null
          const more = id === 'live' && !showAllLive && full.length > LIVE_PREVIEW ? full.length - LIVE_PREVIEW : 0
          const items = more ? full.slice(0, LIVE_PREVIEW) : full
          return (
            <section key={id} className={`eps-section st-${id}`}>
              <header className="eps-section-head">
                <h2><span className="eps-section-bar" />{title}<span className="eps-tab-n">{full.length}</span></h2>
                <p>{hint}</p>
              </header>
              <Items list={items} view={view} {...cardProps} />
              {more > 0 && <button className="btn ghost eps-more" onClick={() => setShowAllLive(true)}>Show {more} more live videos<Icon name="chevronDown" size={14} /></button>}
            </section>
          )
        })
      ) : (() => {
        const items = sorted(base.filter((e) => tabDef[2].includes(e._stage)))
        return items.length ? <Items list={items} view={view} {...cardProps} />
          : <Empty compact icon="filter" title={`Nothing here right now (${STAGES[tabDef[2][0]]?.label || tabDef[1]})`}
            action={<button className="btn" onClick={() => setParam('tab', '')}>Show everything</button>} />
      })()}
    </div>
  )
}

function Items({ list, view, ...p }) {
  if (view === 'list') {
    return (
      <div className="card flush eps-table" role="table">
        <div className="eps-tr eps-th" role="row">
          <span /><span>Video</span><span>Stage</span><span>Goes live / went live</span><span className="num">Views</span>
        </div>
        {list.map((e) => <Row key={e.id} ep={e} {...p} />)}
      </div>
    )
  }
  return <div className="eps-grid">{list.map((e) => <Card key={e.id} ep={e} {...p} />)}</div>
}

/** The line under the title, depending on where the video stands. */
function Status({ ep, bar, onRetry, busy }) {
  const st = ep._stage
  const at = goLiveAt(ep)
  if (st === 'live') {
    return (
      <div className="eps-status">
        <span className="eps-views"><Icon name="eye" size={13} /><b>{fmtNum(ep.views || 0)}</b> views</span>
        {ep.likes ? <span className="eps-views"><Icon name="heart" size={13} /><b>{fmtNum(ep.likes)}</b></span> : null}
        {at && <span className="eps-faint">live {ago(at)}</span>}
      </div>
    )
  }
  if (st === 'upcoming' || st === 'scheduled') {
    return (
      <div className="eps-status">
        <span className="eps-when"><Icon name="calendar" size={13} />{shortWhen(at)}</span>
        <span className="eps-in">in {until(at)}</span>
      </div>
    )
  }
  if (st === 'uploading') return <div className="eps-status"><span className="eps-when"><span className="pulse-dot" />Sending to YouTube…</span></div>
  if (st === 'production') {
    const p = ep.progress
    return p && p.pct != null && p.pct < 100
      ? <Progress pct={p.pct} label={p.stage} tone="violet" />
      : <div className="eps-status"><span className="eps-faint"><Icon name="clock" size={12} /> {ep.kind === 'dub' ? (ep.error?.startsWith('Waiting') ? ep.error.replace(/^Waiting: /, 'Waiting for ') : 'Dub queued: made up to 3 days before the English one goes live') : ep.status === 'planned' ? 'Queued' : ep.status === 'scripted' ? 'Script ready, rendering next' : 'Working on it…'}</span></div>
  }
  if (st === 'review') {
    return <div className="eps-status"><ScoreBadge score={ep.score} bar={bar} /><span className="eps-cta">Review now<Icon name="arrowRight" size={13} /></span></div>
  }
  if (st === 'failed') {
    const renderFail = /^render/i.test(ep.error || '')
    return (
      <div className="eps-status col">
        {ep.error && <span className="eps-err" title={ep.error}>{ep.error}</span>}
        {onRetry && (
          <button className="btn sm" disabled={busy === `retry-${ep.id}`}
            onClick={(ev) => { ev.preventDefault(); ev.stopPropagation(); onRetry(ep, renderFail ? 'render' : 'rewrite') }}>
            <Icon name="refresh" size={13} />{ep.kind === 'dub' ? 'Dub again' : renderFail ? 'Render again' : 'Rewrite'}
          </button>
        )}
      </div>
    )
  }
  return <div className="eps-status"><span className="eps-faint">{ago(ep.created_at)}</span></div>
}

function Card({ ep, catMap, ...p }) {
  const cat = catMap[ep.category]
  return (
    <Link to={itemLink(ep)} className={`eps-card st-${ep._stage} ch-${chOf(ep)}`}>
      <div className="eps-media">
        <Thumb ep={ep} emoji={cat?.emoji} />
        <span className="eps-media-chip"><StageChip stage={ep._stage} solid /></span>
        {ep.kind === 'short' && <span className="eps-kind"><Icon name="phone" size={11} />Short</span>}
        {ep.kind === 'compilation' && <span className="eps-kind"><Icon name="layers" size={11} />Compilation</span>}
        {ep.duration ? <span className="dur">{fmtDur(ep.duration)}</span> : null}
        {ep.video_url && <span className="ep-play" aria-hidden="true"><Icon name="play" size={18} /></span>}
        <ChannelBadge it={ep} size="on-media" />
      </div>
      <div className="eps-body">
        <h3 className="eps-title">{ep.title || ep.topic || `Episode #${ep.id}`}</h3>
        <div className="eps-meta">
          {chOf(ep) === 'world' ? <span>{ep.lang_native} · {ep.lang_name}</span> : cat && <span>{cat.emoji} {cat.name}</span>}
          {chOf(ep) !== 'world' && ep.age_band && <span>Ages {ep.age_band}</span>}
        </div>
        <Status ep={ep} {...p} />
      </div>
    </Link>
  )
}

function Row({ ep, catMap, bar }) {
  const cat = catMap[ep.category]
  const at = goLiveAt(ep)
  const st = ep._stage
  return (
    <Link to={itemLink(ep)} className={`eps-tr st-${st} ch-edge-${chOf(ep)}`} role="row">
      <span className="eps-row-thumb"><Thumb ep={ep} emoji={cat?.emoji} />{ep.duration ? <span className="dur">{fmtDur(ep.duration)}</span> : null}</span>
      <span className="eps-row-main">
        <b>{ep.title || ep.topic}</b>
        <span className="eps-meta">
          <ChannelBadge it={ep} />
          {ep.kind === 'short' ? <span className="eps-kind-inline">Short</span> : ep.kind === 'compilation' ? <span className="eps-kind-inline">Compilation</span> : null}
          {cat && <span>{cat.emoji} {cat.name}</span>}
          {chOf(ep) === 'world' ? <span>{ep.lang_name}</span> : <span>#{ep.id}</span>}
        </span>
      </span>
      <span className="eps-row-stage"><StageChip stage={st} /></span>
      <span className="eps-row-when">
        {at && ['live', ...SOON].includes(st)
          ? <>{shortWhen(at)}<small>{st === 'live' ? ago(at) : `in ${until(at)}`}</small></>
          : st === 'failed' ? <small className="eps-err" title={ep.error}>{ep.error}</small>
          : st === 'review' ? <ScoreBadge score={ep.score} bar={bar} /> : <small>{ago(ep.created_at)}</small>}
      </span>
      <span className="num">{st === 'live' ? <b>{fmtNum(ep.views || 0)}</b> : <span className="eps-faint">—</span>}</span>
    </Link>
  )
}
