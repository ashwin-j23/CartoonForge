import { useEffect, useState } from 'react'
import { get } from '../api'
import Icon from './icons'
import { Badge, Empty, fmtNum, Skeleton, Spinner, Toggle, useApi, useToast } from './ui'

export const gutErr = (e) => (e?.status === 502 ? 'Couldn’t reach Project Gutenberg — try again in a minute.' : e?.message)

const SPINE = ['#6447f5', '#e5488a', '#12a594', '#2f81f7', '#f59e0b', '#a64bd3']
const spine = (id) => SPINE[Math.abs(Number(String(id).replace(/\D/g, '')) || 0) % SPINE.length]

function BookCard({ b, active, onOpen }) {
  return (
    <button type="button" className={`book-card ${active ? 'on' : ''}`} onClick={() => onOpen(b)} aria-pressed={active}>
      <span className="book-cover" style={{ '--spine': spine(b.id) }} aria-hidden="true">
        <span className="book-cover-title">{b.title}</span>
      </span>
      <span className="book-body">
        <b className="book-title">{b.title}</b>
        <span className="muted small">{(b.authors || []).join(', ') || 'Unknown author'}</span>
        {b.why && <span className="small book-why">{b.why}</span>}
        <span className="chips">
          {(b.subjects || []).slice(0, 2).map((s) => <Badge key={s} size="sm" title={s}>{s.length > 28 ? `${s.slice(0, 26)}…` : s}</Badge>)}
          {b.downloads > 0 && <Badge size="sm" tone="blue" icon="arrowDown">{fmtNum(b.downloads)}</Badge>}
        </span>
      </span>
    </button>
  )
}

/** Story list of one book. renderAction(story, book) returns the action node for each story. */
export function Stories({ book, onClose, renderAction }) {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    setData(null); setErr(null)
    get(`/books/${encodeURIComponent(book.id)}/stories`).then((d) => { if (alive) setData(d) }, (e) => {
      if (!alive) return
      setErr(gutErr(e)); toast(gutErr(e), 'bad')
    })
    return () => { alive = false }
  }, [book.id, toast])

  const b = data?.book || book
  return (
    <section className="card stories">
      <div className="card-head">
        <div>
          <h2><Icon name="bookOpen" size={18} />{b.title}</h2>
          <span className="muted small">{(b.authors || []).join(', ')}{b.url && <> · <a href={b.url} target="_blank" rel="noreferrer">Project Gutenberg<Icon name="external" size={12} /></a></>}</span>
        </div>
        {onClose && <button className="icon-btn" onClick={onClose} aria-label="Close book"><Icon name="x" /></button>}
      </div>
      {err ? <Empty compact icon="cloud" title="Couldn’t open this book">{err}</Empty> : !data ? (
        <div className="book-loading"><span className="muted small"><Spinner size={14} /> Reading the book and finding its stories…</span><Skeleton h={58} count={3} r={10} style={{ marginTop: 8 }} /></div>
      ) : !data.stories?.length ? <Empty compact icon="search" title="No stories found">This book didn’t split into animatable stories.</Empty> : (
        <ol className="story-list">
          {data.stories.map((s) => (
            <li key={s.index} className="story">
              <span className="story-n">{s.index + 1}</span>
              <div className="story-main">
                <div className="story-head"><b>{s.title || `Story ${s.index + 1}`}</b><span className="muted tiny">{fmtNum(s.words)} words</span></div>
                {s.preview && <p className="story-preview">{s.preview}</p>}
              </div>
              <div className="story-act">{renderAction(s, b)}</div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

/** Shelf + Gutenberg search + story list. */
export default function BookBrowser({ renderAction, compact }) {
  const shelf = useApi('/books', { quiet: true })
  const toast = useToast()
  const [q, setQ] = useState('')
  const [kids, setKids] = useState(false)
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [open, setOpen] = useState(null)

  useEffect(() => { if (shelf.error) toast(gutErr(shelf.error), 'bad') }, [shelf.error, toast])

  const search = async (e) => {
    e?.preventDefault()
    if (!q.trim()) { setResults(null); return }
    setSearching(true)
    try { setResults(await get(`/books/search?q=${encodeURIComponent(q.trim())}&children=${kids}`)) }
    catch (er) { toast(gutErr(er), 'bad'); setResults([]) }
    finally { setSearching(false) }
  }

  const list = results ?? shelf.data
  const pick = (b) => { setOpen(b); setTimeout(() => document.getElementById('book-stories')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 60) }
  const groups = [...new Set((list || []).map((b) => b.group || ''))]

  return (
    <div className={`book-browser ${compact ? 'compact' : ''}`}>
      <form className="book-search" onSubmit={search}>
        <label className="search-box grow">
          <Icon name="search" size={16} />
          <input type="search" placeholder="Search Project Gutenberg — Aesop, Peter Rabbit, fairy tales…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search books" />
        </label>
        <Toggle checked={kids} onChange={setKids} label="Children’s books only" />
        <button className="btn primary" disabled={searching || !q.trim()}>{searching ? <Spinner /> : <Icon name="search" size={16} />}Search</button>
        {results && <button type="button" className="btn ghost" onClick={() => { setResults(null); setQ('') }}>Back to shelf</button>}
      </form>

      {open && <div id="book-stories"><Stories book={open} onClose={() => setOpen(null)} renderAction={renderAction} /></div>}

      <section>
        <div className="section-title"><div><h2>{results ? `${results.length} result${results.length === 1 ? '' : 's'}` : 'Curated shelf'}</h2></div></div>
        {(shelf.loading && !results) || searching ? (
          <>
            <p className="muted small"><Spinner size={13} /> Dusting off the shelf… the first visit can take 10–20 seconds while we fetch from Project Gutenberg.</p>
            <div className="grid books"><Skeleton h={128} r={14} count={compact ? 4 : 6} /></div>
          </>
        ) : !list?.length ? (
          shelf.error && !results
            ? <Empty icon="cloud" title="Couldn’t reach Project Gutenberg" action={<button className="btn" onClick={() => shelf.reload()}><Icon name="refresh" size={15} />Try again</button>}>The library may be busy. Try again in a minute.</Empty>
            : <Empty icon="book" title="No books found">Try a different search, or turn off “children’s books only”.</Empty>
        ) : groups.map((g) => (
          <div key={g || 'all'} className="book-group">
            {g && <h3 className="book-group-title">{g}</h3>}
            <div className="grid books">{list.filter((b) => (b.group || '') === g).map((b) => <BookCard key={b.id} b={b} active={open?.id === b.id} onOpen={pick} />)}</div>
          </div>
        ))}
      </section>
    </div>
  )
}
