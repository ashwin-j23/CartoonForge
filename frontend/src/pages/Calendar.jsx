import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { mediaUrl, post } from '../api'
import Icon from '../components/icons'
import { StageChip, STAGES, stageOfSlot } from '../components/stage'
import { ago, Empty, fmtDate, fmtDur, fmtNum, PageHead, Progress, SafeImg, Seg, Skeleton, until, useAction, useApi, useCategoryMap } from '../components/ui'

const FILTERS = ['live', 'upcoming', 'scheduled', 'uploading', 'failed']
const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const LIVE_PREVIEW = 10
const dayKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const clock = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
const ts = (iso) => new Date(iso || 0).getTime()
const label = (s) => (s === 'failed' ? 'Late' : STAGES[s].label)

function dayTitle(k, today) {
  const d = new Date(k + 'T12:00:00')
  const diff = Math.round((d - new Date(today + 'T12:00:00')) / 86400000)
  return {
    lead: diff === 0 ? 'Today' : diff === 1 ? 'Tomorrow' : diff === -1 ? 'Yesterday' : d.toLocaleDateString(undefined, { weekday: 'long' }),
    name: d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' }),
  }
}

/** Re-render every 30 s so the countdowns stay right. */
function useTick(ms = 30000) {
  const [, set] = useState(0)
  useEffect(() => { const t = setInterval(() => set((n) => n + 1), ms); return () => clearInterval(t) }, [ms])
}

function Mini({ it, catMap }) {
  return (
    <SafeImg className="sch-thumb" src={mediaUrl(it.thumb_url)} alt=""
      fallback={<span className="sch-thumb ph" aria-hidden="true">{catMap[it.category]?.emoji || (it.kind === 'short' ? '📱' : '🎬')}</span>} />
  )
}

function Item({ it, catMap, past }) {
  const st = it._stage
  return (
    <li className={`sch-item st-${st}`}>
      <span className="sch-time">
        {past ? <>{fmtDate(it.publish_at, { month: 'short', day: 'numeric' })}<small>{clock(it.publish_at)}</small></> : clock(it.publish_at)}
      </span>
      <span className="sch-rail" aria-hidden="true"><i /></span>
      <div className="sch-card">
        <Link to={`/episodes/${it.id}`} className="sch-card-link">
          <Mini it={it} catMap={catMap} />
          <span className="sch-card-main">
            <b className="sch-title">{it.title}</b>
            <span className="sch-sub">
              <span className={`sch-kind ${it.kind === 'short' ? 'short' : ''}`}>{it.kind === 'short' ? 'Short' : 'Episode'}</span>
              {it.duration ? <span>{fmtDur(it.duration)}</span> : null}
              {st === 'live' ? <><span><Icon name="eye" size={12} /> {fmtNum(it.views || 0)} views</span><span>live {ago(it.publish_at)}</span></>
                : st === 'failed' ? <span className="sch-err" title={it.error}>was due {ago(it.publish_at)}{it.error ? ` · ${it.error}` : ''}</span>
                : <span className="sch-in">goes live in {until(it.publish_at)}</span>}
            </span>
          </span>
        </Link>
        <span className="sch-card-side">
          <StageChip stage={st} label={st === 'failed' ? 'Late' : undefined} />
          {it.url
            ? <a className="icon-btn sm" href={it.url} target="_blank" rel="noreferrer" title="Open on YouTube" aria-label="Open on YouTube"><Icon name="external" size={15} /></a>
            : <span className="sch-noyt" title="Uploads by itself up to 12 hours before its time">not uploaded yet</span>}
        </span>
      </div>
    </li>
  )
}

function Slot({ at }) {
  return (
    <li className="sch-item slot">
      <span className="sch-time">{clock(at)}</span>
      <span className="sch-rail" aria-hidden="true"><i /></span>
      <div className="sch-card slot"><Icon name="plus" size={14} />Open slot: the next approved episode takes it</div>
    </li>
  )
}

export default function Calendar() {
  useTick()
  const { data, loading, reload } = useApi('/calendar', { ms: 30000 })
  const [busy, run] = useAction()
  const [, catMap] = useCategoryMap()
  const [view, setView] = useState('agenda')
  const [only, setOnly] = useState('')
  const [allLive, setAllLive] = useState(false)
  const [cursor, setCursor] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1) })
  const dayRefs = useRef({})
  const today = dayKey(new Date())

  const items = useMemo(() => (data?.scheduled || []).map((it) => ({ ...it, _stage: stageOfSlot(it.state) }))
    .sort((a, b) => ts(a.publish_at) - ts(b.publish_at)), [data])
  const counts = useMemo(() => {
    const c = {}
    for (const it of items) c[it._stage] = (c[it._stage] || 0) + 1
    return c
  }, [items])
  const filtered = useMemo(() => (only ? items.filter((it) => it._stage === only) : items), [items, only])
  const upcoming = useMemo(() => filtered.filter((it) => it._stage !== 'live'), [filtered])
  const live = useMemo(() => filtered.filter((it) => it._stage === 'live').sort((a, b) => ts(b.publish_at) - ts(a.publish_at)), [filtered])
  const next = items.find((it) => !['live', 'failed'].includes(it._stage) && ts(it.publish_at) >= Date.now() - 60000)

  // agenda: each day with what goes live on it, plus the next open slots
  const days = useMemo(() => {
    const m = {}
    for (const it of upcoming) (m[dayKey(new Date(it.publish_at))] ||= []).push({ type: 'it', at: it.publish_at, it })
    if (!only) for (const s of (data?.slots || []).slice(0, 3)) (m[dayKey(new Date(s))] ||= []).push({ type: 'slot', at: s })
    for (const k of Object.keys(m)) m[k].sort((a, b) => ts(a.at) - ts(b.at))
    return Object.entries(m).sort(([a], [b]) => a.localeCompare(b))
  }, [upcoming, data, only])

  // the next 7 days at a glance
  const week = useMemo(() => Array.from({ length: 7 }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() + i)
    const k = dayKey(d)
    return { k, d, its: items.filter((it) => dayKey(new Date(it.publish_at)) === k) }
  }), [items])

  const byDay = useMemo(() => {
    const m = {}
    const add = (k, x) => { (m[k] ||= []).push(x) }
    for (const it of filtered) add(dayKey(new Date(it.publish_at)), { type: 'it', at: it.publish_at, it })
    for (const w of data?.world_days || []) if (w.date) add(String(w.date).slice(0, 10), { type: 'world', w })
    for (const k of Object.keys(m)) m[k].sort((a, b) => ts(a.at) - ts(b.at))
    return m
  }, [filtered, data])
  const cells = useMemo(() => {
    const start = new Date(cursor); start.setDate(1 - ((cursor.getDay() + 6) % 7))
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d })
  }, [cursor])
  const move = (n) => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + n, 1))
  const jump = (k) => { setView('agenda'); setOnly(''); setTimeout(() => dayRefs.current[k]?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 40) }

  const liveAll = items.filter((it) => it._stage === 'live')
  const liveShorts = liveAll.filter((it) => it.kind === 'short').length
  const totalViews = liveAll.reduce((n, it) => n + (it.views || 0), 0)
  const worldSoon = (data?.world_days || []).filter((w) => w.date >= today).slice(0, 5)

  return (
    <div className="page">
      <PageHead title="Schedule" sub="When each video goes live on YouTube. Each colour shows where a video stands." />

      {loading && !data ? <Skeleton h={150} r={16} /> : (
        <div className="sch-top">
          <div className={`sch-next ${next ? `st-${next._stage}` : ''}`}>
            <span className="sch-eyebrow"><Icon name="rocket" size={14} />Next to go live</span>
            {next ? (
              <Link to={`/episodes/${next.id}`} className="sch-next-body">
                <Mini it={next} catMap={catMap} />
                <span className="sch-next-text">
                  <span className="sch-count">in {until(next.publish_at)}</span>
                  <b>{next.title}</b>
                  <span className="sch-sub"><span>{fmtDate(next.publish_at)}</span><StageChip stage={next._stage} /></span>
                </span>
              </Link>
            ) : <p className="sch-none">Nothing waiting. New episodes take the next open slot as soon as they're approved.</p>}
          </div>

          <div className="sch-sum">
            <div className="sch-sum-head">
              <div><b>{liveAll.length}</b><span>live · {liveAll.length - liveShorts} episodes, {liveShorts} Shorts</span></div>
              <div><b>{fmtNum(totalViews)}</b><span>views</span></div>
              <div><b>{items.length - liveAll.length}</b><span>still to go live</span></div>
            </div>
            <div className="sch-stack" aria-hidden="true">
              {FILTERS.map((s) => (counts[s] ? <i key={s} className={`st-${s}`} style={{ flexGrow: counts[s] }} /> : null))}
            </div>
            <div className="sch-filters" role="group" aria-label="Show only">
              {FILTERS.filter((s) => counts[s] || only === s || ['live', 'upcoming', 'scheduled'].includes(s)).map((s) => (
                <button key={s} type="button" className={`sch-filter st-${s} ${only === s ? 'on' : ''}`} aria-pressed={only === s}
                  onClick={() => setOnly(only === s ? '' : s)} title={STAGES[s].hint}>
                  <i />{label(s)}<b>{counts[s] || 0}</b>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="sch-week" aria-label="Next 7 days">
        {week.map(({ k, d, its }) => (
          <button key={k} type="button" className={`sch-day-tile ${k === today ? 'today' : ''}`}
            onClick={() => its.length && jump(k)} disabled={!its.length}>
            <span className="sch-dow">{k === today ? 'Today' : d.toLocaleDateString(undefined, { weekday: 'short' })}</span>
            <span className="sch-date">{d.getDate()}</span>
            <span className="sch-dots">{its.slice(0, 8).map((it) => <i key={it.id} className={`st-${it._stage}`} title={`${clock(it.publish_at)} · ${it.title}`} />)}</span>
            <span className="sch-day-n">{its.length ? `${its.length} video${its.length === 1 ? '' : 's'}` : 'free'}</span>
          </button>
        ))}
      </div>

      <div className="sch-layout">
        <div className="card sch-main">
          <div className="sch-toolbar">
            <h2>{view === 'month' ? cursor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }) : only ? label(only) : 'Coming up'}</h2>
            <div className="row">
              {view === 'month' && <>
                <button className="btn ghost sm" onClick={() => { const d = new Date(); setCursor(new Date(d.getFullYear(), d.getMonth(), 1)) }}>Today</button>
                <button className="icon-btn" onClick={() => move(-1)} aria-label="Previous month"><Icon name="chevronLeft" /></button>
                <button className="icon-btn" onClick={() => move(1)} aria-label="Next month"><Icon name="chevronRight" /></button>
              </>}
              <Seg value={view} onChange={setView} size="sm" label="View" options={[['agenda', 'Agenda', 'list'], ['month', 'Month', 'calendar']]} />
            </div>
          </div>

          {loading && !data ? <Skeleton h={420} r={10} /> : view === 'agenda' ? (
            <>
              {days.map(([k, rows]) => {
                const t = dayTitle(k, today)
                const n = rows.filter((r) => r.type === 'it').length
                return (
                  <section key={k} className={`sch-dayblock ${k === today ? 'today' : ''}`} ref={(el) => { dayRefs.current[k] = el }}>
                    <h3 className="sch-dayhead"><span>{t.lead}</span><small>{t.name}</small>{n > 0 && <em>{n} video{n === 1 ? '' : 's'}</em>}</h3>
                    <ul className="sch-timeline">
                      {rows.map((r, i) => (r.type === 'it' ? <Item key={r.it.id} it={r.it} catMap={catMap} /> : <Slot key={`s${i}`} at={r.at} />))}
                    </ul>
                  </section>
                )
              })}
              {!days.length && only !== 'live' && <Empty compact icon="calendar">{only ? 'Nothing in this state right now.' : 'Nothing waiting to go live.'}</Empty>}

              {live.length > 0 && (
                <section className="sch-dayblock sch-livelist">
                  <h3 className="sch-dayhead"><span>Already live</span><small>newest first</small><em>{live.length} videos</em></h3>
                  <ul className="sch-timeline">
                    {(allLive ? live : live.slice(0, LIVE_PREVIEW)).map((it) => <Item key={it.id} it={it} catMap={catMap} past />)}
                  </ul>
                  {!allLive && live.length > LIVE_PREVIEW && <button className="btn ghost sch-more" onClick={() => setAllLive(true)}>Show all {live.length}<Icon name="chevronDown" size={14} /></button>}
                </section>
              )}
            </>
          ) : (
            <div className="sch-month-wrap">
              <div className="sch-month" role="grid">
                {DOW.map((d) => <div key={d} className="sch-mdow" role="columnheader">{d}</div>)}
                {cells.map((d) => {
                  const k = dayKey(d)
                  const its = byDay[k] || []
                  return (
                    <div key={k} className={`sch-mcell ${d.getMonth() !== cursor.getMonth() ? 'out' : ''} ${k === today ? 'today' : ''} ${k < today ? 'past' : ''}`} role="gridcell">
                      <span className="sch-mday">{d.getDate()}</span>
                      {its.slice(0, 4).map((x, i) => (x.type === 'it' ? (
                        <Link key={i} to={`/episodes/${x.it.id}`} className={`sch-mev st-${x.it._stage}`} title={`${label(x.it._stage)} · ${x.it.title} · ${fmtDate(x.it.publish_at)}`}>
                          <i /><b>{clock(x.it.publish_at)}</b><span>{x.it.kind === 'short' ? '📱 ' : ''}{x.it.title}</span>
                        </Link>
                      ) : (
                        <span key={i} className="sch-mev world" title={x.w.theme}>{catMap[x.w.category]?.emoji || '🌍'}<span>{x.w.theme}</span></span>
                      )))}
                      {its.length > 4 && <button type="button" className="sch-mmore" onClick={() => jump(k)}>+{its.length - 4} more</button>}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          <div className="sch-legend">
            {FILTERS.map((s) => <span key={s}><i className={`st-${s}`} />{label(s)}</span>)}
            {view === 'month' && <span><i className="world" />World day</span>}
          </div>
        </div>

        <aside className="sch-side">
          <div className="card sch-how">
            <h3><Icon name="info" size={16} />How a video goes live</h3>
            <ol>
              <li className="st-scheduled"><i /><div><b>Scheduled</b><span>Approved and given a time slot.</span></div></li>
              <li className="st-upcoming"><i /><div><b>On YouTube · going live</b><span>Uploaded up to 12 h early as private. YouTube makes it public on the minute.</span></div></li>
              <li className="st-live"><i /><div><b>Live</b><span>Public: anyone can watch.</span></div></li>
            </ol>
            <p className="muted tiny">Times are in your time zone. Videos go live at least an hour apart.</p>
          </div>

          <div className="card">
            <h3><Icon name="clock" size={16} />Open slots</h3>
            {!data ? <Skeleton h={18} count={4} /> : data.slots?.length ? (
              <ul className="sch-slots">{data.slots.slice(0, 6).map((s) => <li key={s}><b>{fmtDate(s)}</b><span>in {until(s)}</span></li>)}</ul>
            ) : <p className="muted small">No open slots. The schedule is full.</p>}
          </div>

          <div className="card">
            <h3><Icon name="box" size={16} />Storage</h3>
            {data?.storage ? (() => {
              const st = data.storage
              const pct = st.pct ?? 0
              return <>
                <Progress pct={Math.min(100, pct)} tone={pct >= 100 ? 'red' : pct >= 75 ? 'amber' : 'green'} label={`${Math.round(st.used_mb)} of ${st.limit_mb} MB`} />
                <p className="muted tiny sch-gap">{pct >= 100 ? 'Over the limit; it shrinks as videos go live. ' : pct >= 75 ? 'Nearly full: new episodes pause until some go live. ' : 'Healthy. '}Old files are removed automatically. Checked {ago(st.at)}.</p>
              </>
            })() : <p className="muted small">Checked after each upload and once a day.</p>}
            <button className="btn sm sch-gap" disabled={busy === 'clean'}
              onClick={async () => { const r = await run('clean', () => post('/storage/cleanup'), (x) => `Freed ${Math.round(x.freed_mb)} MB`); if (r) reload(true) }}>
              <Icon name="trash" size={14} />{busy === 'clean' ? 'Cleaning…' : 'Clean up now'}
            </button>
          </div>

          {worldSoon.length > 0 && (
            <div className="card">
              <h3><Icon name="globe" size={16} />Coming world days</h3>
              <ul className="sch-slots">{worldSoon.map((w, i) => (
                <li key={i}>
                  <b>{catMap[w.category]?.emoji || '🌍'} {w.theme}</b>
                  <span>{fmtDate(w.date + 'T12:00:00', { weekday: 'short', month: 'short', day: 'numeric' })} ·{' '}
                    <Link className="link-sm" to={`/create?${new URLSearchParams({ topic: w.theme, ...(w.category ? { category: w.category } : {}) })}`}>Make episode</Link></span>
                </li>
              ))}</ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
