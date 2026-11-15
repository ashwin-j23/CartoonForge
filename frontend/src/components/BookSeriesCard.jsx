import { Link } from 'react-router-dom'
import { post, put } from '../api'
import Icon from './icons'
import { Badge, Skeleton, Spinner, Toggle, useAction } from './ui'

const STATUS_TONE = { published: 'green', approved: 'blue', review: 'amber', rendering: 'blue', writing: 'blue', scripted: 'blue', planned: 'neutral' }

/** Automatic book series: one book, story after story, an episode each day. `series` comes from GET /books/series. */
export default function BookSeriesCard({ series: s, setSeries }) {
  const [busy, run] = useAction()
  if (!s) return <section className="card series-card"><Skeleton h={120} r={14} /></section>

  const act = async (key, fn, msg) => { const r = await run(key, fn, msg); if (r) setSeries(r) }
  const b = s.book
  const pct = b ? Math.round((s.next / Math.max(1, b.total)) * 100) : 0

  return (
    <section className={`card series-card ${s.enabled ? 'on' : ''}`} aria-labelledby="series-h">
      <div className="auto-head">
        <div className="auto-title">
          <span className="fs-ico"><Icon name="bookOpen" size={18} /></span>
          <div>
            <h2 id="series-h">Automatic book series</h2>
            <p className="muted small">
              The studio takes the next story of the book and makes it an episode — story 1, 2, 3… to the end,
              then starts the next book on the shelf. Each episode credits the book.
            </p>
          </div>
        </div>
        <Toggle checked={s.enabled} disabled={busy === 'toggle'} label={s.enabled ? 'On' : 'Off'}
          onChange={(on) => act('toggle', () => put('/books/series', { enabled: on }),
            on ? 'Book series ON — the next story becomes an episode' : 'Book series OFF')} />
      </div>

      {b ? (
        <div className="series-book">
          <div className="grow">
            <b>{b.title}</b> <span className="muted small">{(b.authors || []).join(', ')}</span>
            <div className="series-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
              <span style={{ width: `${pct}%` }} />
            </div>
            <span className="muted small">{s.next >= b.total ? 'Finished' : `Next: story ${s.next + 1} of ${b.total}`}
              {s.next_book && <> · then “{s.next_book}”</>}</span>
          </div>
          <div className="row-gap">
            <button className="btn sm" disabled={!!busy || s.next >= b.total} title="Skip the next story"
              onClick={() => act('skip', () => post('/books/series/skip', { n: 1 }), 'Skipped one story')}>
              {busy === 'skip' ? <Spinner size={14} /> : <Icon name="skipForward" size={14} />}Skip
            </button>
            <button className="btn sm ghost" disabled={!!busy}
              onClick={() => act('restart', () => post('/books/series/restart'), 'Back to story 1')}>
              <Icon name="refresh" size={14} />Restart
            </button>
          </div>
        </div>
      ) : (
        <p className="muted small">No book yet: switch it on to start with the first book on the shelf, or open a book below and press <b>Use for series</b>.</p>
      )}

      <div className="auto-grid">
        <div>
          <h3 className="auto-sub">Coming up</h3>
          {s.upcoming?.length ? (
            <ol className="series-list" start={s.next + 1}>
              {s.upcoming.map((u) => <li key={u.index}>{u.title}</li>)}
            </ol>
          ) : <p className="muted small">—</p>}
        </div>
        <div>
          <h3 className="auto-sub">Episodes per day from books</h3>
          <div className="chips">
            {[1, 2, 3].map((n) => (
              <button key={n} className={`btn sm ${s.per_day === n ? 'primary' : ''}`} disabled={!!busy}
                onClick={() => act(`pd${n}`, () => put('/books/series', { per_day: n }), `${n} book episode${n > 1 ? 's' : ''} a day`)}>{n}</button>
            ))}
          </div>
          <p className="muted small" style={{ marginTop: 8 }}>The rest of the day’s episodes stay normal topics. Needs an AI key.</p>
          {s.made?.length > 0 && (
            <>
              <h3 className="auto-sub" style={{ marginTop: 12 }}>Made from this book</h3>
              {s.made.slice(-4).reverse().map((m) => (
                <Link key={m.id} to={`/episodes/${m.id}`} className="auto-held-row">
                  <span className="grow"><b>Story {m.index + 1}</b><small> {m.title}</small></span>
                  <Badge size="sm" tone={STATUS_TONE[m.status] || 'neutral'}>{m.status}</Badge>
                </Link>
              ))}
            </>
          )}
        </div>
      </div>
    </section>
  )
}
