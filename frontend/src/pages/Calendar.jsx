import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from '../components/icons'
import { Empty, fmtDate, PageHead, Skeleton, STATUS, until, useApi, useCategoryMap } from '../components/ui'

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const key = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const time = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })

export default function Calendar() {
  const { data, loading } = useApi('/calendar', { ms: 60000 })
  const [, catMap] = useCategoryMap()
  const [cursor, setCursor] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1) })

  const byDay = useMemo(() => {
    const m = {}
    const add = (k, item) => { (m[k] = m[k] || []).push(item) }
    for (const s of data?.scheduled || []) if (s.publish_at) add(key(new Date(s.publish_at)), { type: 'ep', ...s })
    for (const w of data?.world_days || []) if (w.date) add(String(w.date).slice(0, 10), { type: 'world', ...w })
    for (const s of data?.slots || []) add(key(new Date(s)), { type: 'slot', at: s })
    return m
  }, [data])

  const cells = useMemo(() => {
    const first = new Date(cursor)
    const offset = (first.getDay() + 6) % 7
    const start = new Date(first); start.setDate(1 - offset)
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d })
  }, [cursor])
  const today = key(new Date())
  const move = (n) => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + n, 1))
  const upcomingWorld = (data?.world_days || []).filter((w) => w.date >= today).slice(0, 6)

  return (
    <div className="page">
      <PageHead title="Schedule" sub="Scheduled episodes, open posting slots and world days worth a themed episode." />

      <div className="cal-layout">
        <div className="card cal-card">
          <div className="cal-toolbar">
            <h2 className="month">{cursor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</h2>
            <div className="row">
              <button className="btn ghost sm" onClick={() => { const d = new Date(); setCursor(new Date(d.getFullYear(), d.getMonth(), 1)) }}>Today</button>
              <button className="icon-btn" onClick={() => move(-1)} aria-label="Previous month"><Icon name="chevronLeft" /></button>
              <button className="icon-btn" onClick={() => move(1)} aria-label="Next month"><Icon name="chevronRight" /></button>
            </div>
          </div>
          {loading && !data ? <Skeleton h={480} r={10} /> : (
            <div className="cal" role="grid">
              {DOW.map((d) => <div key={d} className="cal-dow" role="columnheader">{d}</div>)}
              {cells.map((d) => {
                const k = key(d)
                const items = byDay[k] || []
                const out = d.getMonth() !== cursor.getMonth()
                return (
                  <div key={k} className={`cal-cell ${out ? 'out' : ''} ${k === today ? 'today' : ''}`} role="gridcell">
                    <span className="cal-day">{d.getDate()}</span>
                    {items.map((it, i) => it.type === 'ep' ? (
                      <Link key={i} to={`/episodes/${it.id}`} className={`cal-ev ep st-${it.status}`} title={`${it.title} · ${fmtDate(it.publish_at)}`}>
                        <span className="cal-ev-t">{time(it.publish_at)}</span> {it.title}
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
            <span><i className="lg ep" />Scheduled / published</span>
            <span><i className="lg world" />World day</span>
            <span><i className="lg slot" />Free slot</span>
          </div>
        </div>

        <aside className="stack">
          <div className="card">
            <h3><Icon name="clock" size={16} />Next free slots</h3>
            {!data ? <Skeleton h={20} count={4} style={{ marginTop: 8 }} /> : data.slots?.length ? (
              <ol className="mini-list">{data.slots.slice(0, 8).map((s) => <li key={s}><b>{fmtDate(s)}</b><span className="muted tiny">in {until(s)}</span></li>)}</ol>
            ) : <p className="muted small">No free slots — the schedule is full.</p>}
          </div>
          <div className="card">
            <h3><Icon name="calendar" size={16} />Scheduled</h3>
            {data?.scheduled?.length ? (
              <ul className="mini-list">
                {[...data.scheduled].sort((a, b) => String(a.publish_at).localeCompare(String(b.publish_at))).slice(0, 10).map((s) => (
                  <li key={s.id}><Link to={`/episodes/${s.id}`}>{s.title}</Link><span className="muted tiny">{STATUS[s.status]?.label} · {fmtDate(s.publish_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span></li>
                ))}
              </ul>
            ) : <Empty compact icon="calendar">Nothing scheduled yet.</Empty>}
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
