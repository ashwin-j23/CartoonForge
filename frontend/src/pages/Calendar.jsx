import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from '../components/icons'
import { post } from '../api'
import { ago, Empty, fmtDate, PageHead, Progress, Skeleton, until, useAction, useApi, useCategoryMap } from '../components/ui'

/** Where every video stands, one colour per state (the server decides the state from YouTube's real status). */
export const STATES = {
  live: { label: 'Live on YouTube', short: 'Live', icon: 'checkCircle', hint: 'Public now' },
  uploaded: { label: 'Uploaded · goes live by itself', short: 'Uploaded', icon: 'clock', hint: 'On YouTube, set to go public at its time' },
  uploading: { label: 'Uploading now', short: 'Uploading', icon: 'refresh', hint: 'Being sent to YouTube right now' },
  waiting: { label: 'Not uploaded yet', short: 'Waiting', icon: 'inbox', hint: 'Uploaded automatically up to 12 h before its time' },
  late: { label: 'Late / upload failed', short: 'Late', icon: 'alertCircle', hint: 'Its time passed without going live — retried automatically' },
}
const ORDER = ['late', 'uploading', 'waiting', 'uploaded', 'live']

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const key = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const time = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })

function dayLabel(k, today) {
  const d = new Date(k + 'T12:00:00')
  const t = new Date(today + 'T12:00:00')
  const diff = Math.round((d - t) / 86400000)
  const name = d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
  return diff === 0 ? `Today · ${name}` : diff === 1 ? `Tomorrow · ${name}` : diff === -1 ? `Yesterday · ${name}` : name
}

function StatePill({ state }) {
  const s = STATES[state] || STATES.waiting
  return <span className={`sched-pill s-${state}`} title={s.hint}><Icon name={s.icon} size={13} />{s.short}</span>
}

function when(it) {
  if (it.state === 'live') return `went live ${fmtDate(it.publish_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`
  if (it.state === 'late') return `was due ${fmtDate(it.publish_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`
  return `goes live in ${until(it.publish_at)}`
}

function Row({ it }) {
  return (
    <li className={`sched-row s-${it.state}`}>
      <span className="sched-time">{time(it.publish_at)}</span>
      <StatePill state={it.state} />
      <div className="sched-main">
        <Link to={`/episodes/${it.id}`} className="sched-title">{it.title}</Link>
        <span className="sched-sub">
          {it.kind === 'short' ? <span className="sched-kind">Short</span> : <span className="sched-kind ep">Episode</span>}
          {when(it)}
          {it.error && <span className="sched-err" title={it.error}> · {it.error}</span>}
        </span>
      </div>
      {it.url ? (
        <a className="btn ghost sm" href={it.url} target="_blank" rel="noreferrer"><Icon name="external" size={14} />YouTube</a>
      ) : <span className="sched-noyt">Not on YouTube yet</span>}
    </li>
  )
}

export default function Calendar() {
  const { data, loading, reload } = useApi('/calendar', { ms: 30000 })
  const [busy, run] = useAction()
  const [, catMap] = useCategoryMap()
  const [view, setView] = useState('list')
  const [only, setOnly] = useState('')
  const [cursor, setCursor] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1) })
  const today = key(new Date())

  const items = useMemo(() => [...(data?.scheduled || [])]
    .sort((a, b) => String(a.publish_at).localeCompare(String(b.publish_at))), [data])
  const counts = useMemo(() => {
    const c = {}
    for (const it of items) c[it.state] = (c[it.state] || 0) + 1
    return c
  }, [items])
  const shown = only ? items.filter((it) => it.state === only) : items

  // list: everything not yet live, plus what went live in the last 3 days; free slots in between
  const groups = useMemo(() => {
    const from = new Date(); from.setDate(from.getDate() - 3)
    const m = {}
    for (const it of shown) {
      if (it.state === 'live' && new Date(it.publish_at) < from) continue
      ;(m[key(new Date(it.publish_at))] ||= []).push({ type: 'ep', ...it })
    }
    if (!only) for (const s of (data?.slots || []).slice(0, 3)) (m[key(new Date(s))] ||= []).push({ type: 'slot', publish_at: s })
    for (const k of Object.keys(m)) m[k].sort((a, b) => String(a.publish_at).localeCompare(String(b.publish_at)))
    return Object.entries(m).sort(([a], [b]) => a.localeCompare(b))
  }, [shown, data, only])

  const byDay = useMemo(() => {
    const m = {}
    const add = (k, item) => { (m[k] ||= []).push(item) }
    for (const s of shown) add(key(new Date(s.publish_at)), { type: 'ep', ...s })
    for (const w of data?.world_days || []) if (w.date) add(String(w.date).slice(0, 10), { type: 'world', ...w })
    if (!only) for (const s of data?.slots || []) add(key(new Date(s)), { type: 'slot', at: s })
    for (const k of Object.keys(m)) m[k].sort((a, b) => String(a.publish_at || a.at || '').localeCompare(String(b.publish_at || b.at || '')))
    return m
  }, [shown, data, only])

  const cells = useMemo(() => {
    const first = new Date(cursor)
    const offset = (first.getDay() + 6) % 7
    const start = new Date(first); start.setDate(1 - offset)
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d })
  }, [cursor])
  const move = (n) => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + n, 1))
  const upcomingWorld = (data?.world_days || []).filter((w) => w.date >= today).slice(0, 6)

  return (
    <div className="page">
      <PageHead title="Schedule" sub="Every video and where it stands: live, uploaded and waiting to go live, or not uploaded yet." />

      <div className="sched-summary" role="group" aria-label="Filter by state">
        {ORDER.map((st) => (
          <button key={st} type="button" className={`sched-stat s-${st} ${only === st ? 'on' : ''}`} aria-pressed={only === st}
            onClick={() => setOnly(only === st ? '' : st)} title={STATES[st].hint}>
            <span className="sched-stat-n">{counts[st] || 0}</span>
            <span className="sched-stat-l"><Icon name={STATES[st].icon} size={14} />{STATES[st].label}</span>
          </button>
        ))}
      </div>

      <div className="cal-layout">
        <div className="card cal-card">
          <div className="cal-toolbar">
            {view === 'month' ? (
              <h2 className="month">{cursor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</h2>
            ) : <h2 className="month">{only ? STATES[only].label : 'Coming up'}</h2>}
            <div className="row">
              {view === 'month' && <>
                <button className="btn ghost sm" onClick={() => { const d = new Date(); setCursor(new Date(d.getFullYear(), d.getMonth(), 1)) }}>Today</button>
                <button className="icon-btn" onClick={() => move(-1)} aria-label="Previous month"><Icon name="chevronLeft" /></button>
                <button className="icon-btn" onClick={() => move(1)} aria-label="Next month"><Icon name="chevronRight" /></button>
              </>}
              <div className="seg" role="tablist">
                <button role="tab" aria-selected={view === 'list'} className={view === 'list' ? 'on' : ''} onClick={() => setView('list')}><Icon name="list" size={14} />List</button>
                <button role="tab" aria-selected={view === 'month'} className={view === 'month' ? 'on' : ''} onClick={() => setView('month')}><Icon name="calendar" size={14} />Month</button>
              </div>
            </div>
          </div>

          {loading && !data ? <Skeleton h={480} r={10} /> : view === 'list' ? (
            groups.length ? (
              <div className="sched-list">
                {groups.map(([k, rows]) => (
                  <section key={k} className={k === today ? 'today' : ''}>
                    <h4 className="sched-day">{dayLabel(k, today)}</h4>
                    <ul>
                      {rows.map((it, i) => it.type === 'ep' ? <Row key={it.id} it={it} /> : (
                        <li key={`s${i}`} className="sched-row slot">
                          <span className="sched-time">{time(it.publish_at)}</span>
                          <span className="sched-pill s-slot">Free slot</span>
                          <span className="sched-sub">The next approved episode takes this time</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            ) : <Empty compact icon="calendar">{only ? 'Nothing in this state.' : 'Nothing scheduled yet.'}</Empty>
          ) : (
            <div className="cal" role="grid">
              {DOW.map((d) => <div key={d} className="cal-dow" role="columnheader">{d}</div>)}
              {cells.map((d) => {
                const k = key(d)
                const its = byDay[k] || []
                const out = d.getMonth() !== cursor.getMonth()
                return (
                  <div key={k} className={`cal-cell ${out ? 'out' : ''} ${k === today ? 'today' : ''}`} role="gridcell">
                    <span className="cal-day">{d.getDate()}</span>
                    {its.map((it, i) => it.type === 'ep' ? (
                      <Link key={i} to={`/episodes/${it.id}`} className={`cal-ev ep s-${it.state}`}
                        title={`${STATES[it.state]?.label} · ${it.title} · ${fmtDate(it.publish_at)}`}>
                        <span className="cal-ev-t">{time(it.publish_at)}</span> {it.kind === 'short' ? '▸ ' : ''}{it.title}
                      </Link>
                    ) : it.type === 'world' ? (
                      <span key={i} className="cal-ev world" title={it.theme}>{catMap[it.category]?.emoji || '🌍'} {it.theme}</span>
                    ) : (
                      <span key={i} className="cal-ev slot" title={`Free slot ${fmtDate(it.at)}`}>Free {time(it.at)}</span>
                    ))}
                  </div>
                )
              })}
            </div>
          )}

          <div className="legend">
            {ORDER.map((st) => <span key={st}><i className={`lg s-${st}`} />{STATES[st].label}</span>)}
            <span><i className="lg slot" />Free slot</span>
            {view === 'month' && <span><i className="lg world" />World day</span>}
          </div>
        </div>

        <aside className="stack">
          {data?.totals && (
            <div className="card">
              <h3><Icon name="chart" size={16} />Published so far</h3>
              <div className="sched-totals">
                <div><b>{data.totals.episodes}</b><span>episodes live</span></div>
                <div><b>{data.totals.shorts}</b><span>Shorts live</span></div>
                <div><b>{data.totals.uploaded}</b><span>uploaded, going live</span></div>
                <div><b>{data.totals.waiting}</b><span>not uploaded yet</span></div>
              </div>
            </div>
          )}
          <div className="card">
            <h3><Icon name="box" size={16} />Storage</h3>
            {data?.storage ? (() => {
              const st = data.storage
              const pct = st.pct ?? 0
              return <>
                <Progress pct={Math.min(100, pct)} tone={pct >= 100 ? 'red' : pct >= 75 ? 'amber' : 'green'}
                  label={`${Math.round(st.used_mb)} of ${st.limit_mb} MB`} />
                <p className="muted tiny" style={{ marginTop: 8 }}>
                  {pct >= 100 ? 'Over the limit: it shrinks as waiting episodes are uploaded (their full copy then lives on YouTube). '
                    : pct >= 75 ? 'Nearly full: new episodes pause until some are published. ' : 'Healthy. '}
                  Old renders are removed automatically. Checked {ago(st.at)}.
                </p>
              </>
            })() : <p className="muted small">Not measured yet: it's checked after each upload and once a day.</p>}
            <button className="btn sm" style={{ marginTop: 8 }} disabled={busy === 'clean'}
              onClick={async () => { const r = await run('clean', () => post('/storage/cleanup'), (x) => `Freed ${Math.round(x.freed_mb)} MB`); if (r) reload(true) }}>
              <Icon name="trash" size={14} />{busy === 'clean' ? 'Cleaning…' : 'Clean up now'}
            </button>
          </div>
          <div className="card">
            <h3><Icon name="info" size={16} />How publishing works</h3>
            <ol className="sched-how">
              <li><StatePill state="waiting" /> Approved, waiting its turn.</li>
              <li><StatePill state="uploaded" /> Uploaded up to 12 h early; YouTube makes it public on the minute.</li>
              <li><StatePill state="live" /> Public on YouTube.</li>
            </ol>
            <p className="muted tiny">Times are shown in your time zone.</p>
          </div>
          <div className="card">
            <h3><Icon name="clock" size={16} />Next free slots</h3>
            {!data ? <Skeleton h={20} count={4} style={{ marginTop: 8 }} /> : data.slots?.length ? (
              <ol className="mini-list">{data.slots.slice(0, 6).map((s) => <li key={s}><b>{fmtDate(s)}</b><span className="muted tiny">in {until(s)}</span></li>)}</ol>
            ) : <p className="muted small">No free slots — the schedule is full.</p>}
          </div>
          {upcomingWorld.length > 0 && (
            <div className="card">
              <h3><Icon name="globe" size={16} />Coming world days</h3>
              <ul className="mini-list">{upcomingWorld.map((w, i) => (
                <li key={i}>
                  <b>{catMap[w.category]?.emoji || '🌍'} {w.theme}</b>
                  <span className="row"><span className="muted tiny">{fmtDate(w.date + 'T12:00:00', { weekday: 'short', month: 'short', day: 'numeric' })}</span>
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
