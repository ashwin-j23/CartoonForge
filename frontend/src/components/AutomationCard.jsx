import { Link } from 'react-router-dom'
import { post, put } from '../api'
import Icon from './icons'
import { ago, Badge, fmtDate, Skeleton, Spinner, Toggle, useAction, useApi } from './ui'

/** Full auto mode: one switch, what it needs, what it's doing, and why anything is held back. */
export default function AutomationCard() {
  const { data: a, setData, reload } = useApi('/automation', { ms: 20000, quiet: true })
  const [busy, run] = useAction()
  if (!a) return <section className="card auto-card"><Skeleton h={160} r={14} /></section>

  const toggle = async (on) => {
    const r = await run('toggle', () => put('/automation', { enabled: on }),
      on ? 'Full auto is ON — the studio now runs the channel' : 'Full auto is OFF — episodes wait for your review')
    if (r) setData(r)
  }
  const missing = a.checklist.filter((c) => c.need && !c.ok)
  const last = a.last_tick

  return (
    <section className={`card auto-card ${a.enabled ? 'on' : ''}`} aria-labelledby="auto-h">
      <div className="auto-head">
        <div className="auto-title">
          <span className={`auto-dot ${a.enabled ? (a.ready ? 'run' : 'warn') : ''}`} aria-hidden="true" />
          <div>
            <h2 id="auto-h">Full auto mode</h2>
            <p className="muted small">
              Plans, writes, renders, checks and publishes {a.episodes_per_day} episode{a.episodes_per_day === 1 ? '' : 's'} a day on its own —
              strict gates for children’s content, the kill switch always wins.
            </p>
          </div>
        </div>
        <Toggle checked={a.enabled} disabled={busy === 'toggle'} onChange={toggle} label={a.enabled ? 'On' : 'Off'} />
      </div>

      {a.enabled && !a.ready && (
        <div className="banner warn"><Icon name="alert" size={18} />
          <div><b>Running, but nothing can be published yet.</b> {missing.map((m) => m.title).join(' · ')}</div>
        </div>
      )}

      <div className="auto-grid">
        <div>
          <h3 className="auto-sub">Ready?</h3>
          <ul className="auto-check">
            {a.checklist.map((c) => (
              <li key={c.id} className={c.ok ? 'ok' : (c.need ? 'bad' : 'meh')} title={c.detail}>
                <Icon name={c.ok ? 'checkCircle' : 'alertCircle'} size={16} />
                <span><b>{c.title}</b><small>{c.detail}</small></span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="auto-sub">Today</h3>
          <div className="auto-stats">
            <div><b>{a.published_today}</b><small>published (max {a.max_per_day} + Shorts)</small></div>
            <div><b>{(a.counts.planned || 0) + (a.counts.writing || 0) + (a.counts.scripted || 0) + (a.counts.rendering || 0)}</b><small>in production</small></div>
            <div><b>{a.counts.approved || 0}</b><small>scheduled</small></div>
            <div><b>{a.counts.review || 0}</b><small>held for review</small></div>
          </div>
          <div className="muted small" style={{ marginTop: 10 }}>
            <Icon name="clock" size={13} /> Heartbeat every {a.heartbeat_minutes} min
            {last?.at ? <> · last cycle {ago(last.at)} ({Math.round(last.seconds)} s)</> : ' · no cycle yet'}
          </div>
          {a.next_slots?.length > 0 && (
            <div className="chips" style={{ marginTop: 8 }}>
              {a.next_slots.slice(0, 4).map((s) => <Badge key={s} size="sm" icon="calendar">{fmtDate(s, { weekday: 'short', hour: 'numeric', minute: '2-digit' })}</Badge>)}
            </div>
          )}
          <button className="btn sm" style={{ marginTop: 12 }} disabled={!!busy}
            onClick={async () => { await run('cycle', () => post('/automation/run'), (r) => r?.result || 'Cycle queued'); setTimeout(reload, 4000) }}>
            {busy === 'cycle' ? <Spinner size={14} /> : <Icon name="play" size={14} />}Run a cycle now
          </button>
        </div>
      </div>

      {a.held?.length > 0 && (
        <div className="auto-held">
          <h3 className="auto-sub">Held for you ({a.held.length})</h3>
          {a.held.slice(0, 4).map((h) => (
            <Link key={h.id} to={`/episodes/${h.id}`} className="auto-held-row">
              <span className="grow"><b>{h.title}</b><small>{(h.why || []).join(' · ') || 'Passes every gate — approves on the next cycle'}</small></span>
              <Icon name="chevronRight" size={16} />
            </Link>
          ))}
        </div>
      )}

      {a.actions?.length > 0 && (
        <details className="auto-log">
          <summary>What it did recently</summary>
          <ul>{a.actions.slice(0, 8).map((x, i) => <li key={i} className={x.level}><time>{ago(x.at)}</time>{x.msg}</li>)}</ul>
        </details>
      )}
    </section>
  )
}
