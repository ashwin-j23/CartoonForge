import { useMemo, useState } from 'react'
import { castImg } from '../api'
import { Empty, fmtDur } from './ui'

const CARD_EMOJI = { count: '🔢', number: '#️⃣', letter: '🔤', word: '📝', color: '🎨', shape: '🔷', fact: '💡', question: '❓', page: '📖' }
const KIND_LABEL = { question: '❓ question', answer: '💬 answer', sing: '🎵 sing', line: null }
const SEG_EMOJI = { intro: '👋', hello: '👋', song: '🎵', sing: '🎵', story: '📖', count: '🔢', counting: '🔢', letters: '🔤', game: '🎲', quiz: '❓', recap: '🔁', outro: '🌙', goodbye: '🌙', fact: '💡', movement: '🤸', calm: '🧘', explore: '🔭' }

export function cardText(card) {
  if (!card) return ''
  const { type, ...f } = card
  switch (type) {
    case 'count': return `count ${f.n ?? '?'} × ${f.object ?? 'thing'}`
    case 'number': return `number ${f.n ?? f.number ?? f.text ?? ''}`.trim()
    case 'letter': return `letter ${f.letter ?? ''}${f.word ? ` · ${f.word}` : ''}`
    case 'word': return `word “${f.word ?? f.text ?? ''}”`
    case 'color': return `colour ${f.color ?? f.text ?? ''}${f.object ? ` · ${f.object}` : ''}`
    case 'shape': return `shape ${f.shape ?? ''}${f.color ? ` · ${f.color}` : ''}`
    case 'fact': return f.text ? `fact · ${f.text}` : 'fact'
    case 'question': return f.text ? `question · ${f.text}` : 'question'
    case 'page': return `“${f.text ?? ''}”`
    default: {
      const rest = Object.entries(f).filter(([, v]) => v != null && typeof v !== 'object').map(([k, v]) => `${k}: ${v}`).join(' · ')
      return `${type || 'card'}${rest ? ` · ${rest}` : ''}`
    }
  }
}

export function CardPill({ card }) {
  if (!card) return null
  const style = card.type === 'color' && card.color ? { '--swatch': card.color } : undefined
  return (
    <span className={`card-pill t-${card.type}`} style={style} title={JSON.stringify(card)}>
      <span aria-hidden="true">{CARD_EMOJI[card.type] || '🃏'}</span>
      {card.type === 'color' && card.color && <i className="swatch" />}
      {cardText(card)}
    </span>
  )
}

function Avatar({ castId, name }) {
  const [bad, setBad] = useState(false)
  if (!castId || bad) return <span className="avatar ph" title={name}>{(name || '?').slice(0, 1).toUpperCase()}</span>
  return <img className="avatar" src={castImg(castId)} alt={name} title={name} loading="lazy" onError={() => setBad(true)} />
}

/** Figure out which timeline entry belongs to segment i. */
function segTime(timeline, seg, i, nSegs) {
  if (!Array.isArray(timeline) || !timeline.length) return null
  const byTitle = timeline.find((t) => t.title && seg.title && t.title.toLowerCase() === seg.title.toLowerCase())
  if (byTitle) return byTitle
  if (timeline.length === nSegs) return timeline[i]
  return null
}

function roleOf(sc, who) {
  const r = sc.roles
  if (!r || typeof r !== 'object') return null
  return r[who?.id] || r[sc.speaker] || null
}

export default function ScriptView({ script, timeline, cast, onSeek }) {
  const segs = script?.segments || []
  const [open, setOpen] = useState(() => new Set([0]))
  const castMap = useMemo(() => {
    const m = {}
    for (const c of cast || []) { m[c.id] = c; if (c.name) m[c.name.toLowerCase()] = c }
    return m
  }, [cast])

  if (!script) return <Empty emoji="✍️" title="No script yet">The writer is still working — this fills in when it’s done.</Empty>

  const allOpen = open.size === segs.length
  const totalScenes = segs.reduce((a, s) => a + (s.scenes?.length || 0), 0)

  return (
    <div className="script">
      <div className="script-top">
        {script.title_idea && <h3>{script.title_idea}</h3>}
        {script.summary && <p>{script.summary}</p>}
        <div className="script-facts">
          {script.lesson && <span className="badge t-amber sm">🎯 Lesson: {script.lesson}</span>}
          {(script.key_words || []).map((w) => <span key={w} className="badge t-blue sm">🔑 {w}</span>)}
          <span className="badge t-neutral sm">{segs.length} segments · {totalScenes} scenes</span>
        </div>
        <button className="btn ghost sm" onClick={() => setOpen(allOpen ? new Set() : new Set(segs.map((_, i) => i)))}>
          {allOpen ? 'Collapse all' : 'Expand all'}
        </button>
      </div>

      {segs.map((seg, i) => {
        const t = segTime(timeline, seg, i, segs.length)
        const isOpen = open.has(i)
        return (
          <section key={i} className={`seg-block ${isOpen ? 'open' : ''}`}>
            <button className="seg-head" onClick={() => {
              const n = new Set(open); if (isOpen) n.delete(i); else n.add(i); setOpen(n)
            }} aria-expanded={isOpen}>
              <span className="seg-caret" aria-hidden="true">▸</span>
              <span className="seg-emoji">{SEG_EMOJI[seg.kind] || '🎬'}</span>
              <span className="seg-title">
                <b>{seg.title || seg.kind}</b>
                <small>{seg.kind}{seg.set ? ` · set: ${seg.set}` : ''} · {seg.scenes?.length || 0} scenes</small>
              </span>
              {t && (
                <span className="seg-time" role="button" tabIndex={0}
                  onClick={(e) => { e.stopPropagation(); onSeek?.(t.start) }}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onSeek?.(t.start) } }}
                  title="Jump to this chapter">
                  ⏱ {fmtDur(t.start)}–{fmtDur(t.end)}
                </span>
              )}
            </button>
            {isOpen && (
              <ol className="scenes">
                {(seg.scenes || []).map((sc, j) => {
                  const who = castMap[sc.speaker] || castMap[(sc.speaker || '').toLowerCase()] || null
                  const kindLabel = KIND_LABEL[sc.kind]
                  return (
                    <li key={j} className={`scene k-${sc.kind || 'line'}`}>
                      <Avatar castId={who?.id} name={who?.name || sc.speaker} />
                      <div className="scene-body">
                        <div className="scene-meta">
                          <b>{who?.name || sc.speaker || 'Narrator'}</b>
                          {roleOf(sc, who) && <span className="role">as {roleOf(sc, who)}</span>}
                          {kindLabel && <span className={`kind k-${sc.kind}`}>{kindLabel}</span>}
                          {sc.emotion && <span className="muted tiny">· {sc.emotion}</span>}
                        </div>
                        <p className="scene-text">{sc.text}</p>
                        {(sc.action || sc.card || sc.cast?.length > 0) && (
                          <div className="scene-extra">
                            {sc.card && <CardPill card={sc.card} />}
                            {sc.action && <span className="muted tiny">🎬 {sc.action}</span>}
                            {sc.cast?.length > 0 && (
                              <span className="cast-row" title="On screen">
                                {sc.cast.map((c) => <img key={c} className="avatar xs" src={castImg(c)} alt={castMap[c]?.name || c} title={castMap[c]?.name || c} loading="lazy" />)}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ol>
            )}
          </section>
        )
      })}
    </div>
  )
}
