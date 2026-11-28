import { Link } from 'react-router-dom'
import { mediaUrl } from '../api'
import { ChannelBadge, chOf, itemLink } from './channel'
import Icon from './icons'
import { AnimationBadge } from './looks'
import { ago, Badge, fmtDate, fmtDur, Progress, SafeImg, ScoreBadge, shownStatus, StatusPill } from './ui'

export function Thumb({ ep, emoji, className = 'thumb' }) {
  return (
    <SafeImg className={className} src={mediaUrl(ep.thumb_url)} alt=""
      fallback={<div className={`${className} ph`}><span aria-hidden="true">{emoji || '🎬'}</span></div>} />
  )
}

export function KindBadge({ kind }) {
  if (!kind || kind === 'episode') return null
  if (kind === 'short') return <Badge tone="pink" icon="phone" size="sm">Short</Badge>
  if (kind === 'compilation') return <Badge tone="blue" icon="layers" size="sm">Compilation</Badge>
  if (kind === 'dub') return null
  return <Badge size="sm">{kind}</Badge>
}

const epTitle = (ep) => ep.title || ep.topic || `Episode #${ep.id}`

/** Compact card for pipeline board columns */
const LIVE = ['writing', 'rendering', 'publishing']

export function MiniCard({ ep, catEmoji, bar, onRetry, retrying }) {
  const p = ep.progress
  const failed = ['failed', 'rejected'].includes(ep.status)
  const renderFail = /^render/i.test(ep.error || '')
  return (
    <Link to={itemLink(ep)} className={`mini-card ${failed ? 'is-failed' : ''} ch-edge-${chOf(ep)}`}>
      <div className="mini-thumb">
        <Thumb ep={ep} emoji={catEmoji} />
        {ep.duration ? <span className="dur">{fmtDur(ep.duration)}</span> : null}
      </div>
      <div className="mini-body">
        <div className="mini-title">{epTitle(ep)}</div>
        <div className="mini-meta">
          <ChannelBadge it={ep} />
          <KindBadge kind={ep.kind} />
          <ScoreBadge score={ep.score} bar={bar} />
          {ep.publish_at && ['approved', 'publishing', 'upcoming'].includes(shownStatus(ep))
            ? <span className="muted tiny"><Icon name="calendar" size={12} /> {fmtDate(shownStatus(ep) === 'upcoming' ? ep.published_at : ep.publish_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
            : <span className="muted tiny">{ago(ep.created_at)}</span>}
        </div>
        {LIVE.includes(ep.status) && p && p.pct != null && p.pct < 100
          && <Progress pct={p.pct} label={p.stage} tone={ep.status === 'rendering' ? 'violet' : 'blue'} />}
        {ep.status === 'planned' && <span className="mini-queued"><Icon name="clock" size={12} />Queued</span>}
        {failed && ep.error && <div className="mini-err" title={ep.error}>{ep.error}</div>}
        {failed && onRetry && (
          <button className="btn sm mini-retry" disabled={retrying}
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRetry(ep, renderFail ? 'render' : 'rewrite') }}>
            <Icon name="refresh" size={13} />{renderFail ? 'Render again' : 'Rewrite'}
          </button>
        )}
      </div>
    </Link>
  )
}

/** Larger card for the episodes grid */
export function EpisodeCard({ ep, cat, bar }) {
  const p = ep.progress
  return (
    <Link to={itemLink(ep)} className={`ep-card ch-${chOf(ep)}`}>
      <div className="ep-thumb">
        <Thumb ep={ep} emoji={cat?.emoji} />
        <span className="ep-status"><StatusPill status={shownStatus(ep)} small /></span>
        {ep.duration ? <span className="dur">{fmtDur(ep.duration)}</span> : null}
        {ep.video_url && <span className="ep-play" aria-hidden="true"><Icon name="play" size={18} /></span>}
        <ChannelBadge it={ep} size="on-media" />
      </div>
      <div className="ep-body">
        <div className="ep-title">{epTitle(ep)}</div>
        <div className="ep-meta">
          <KindBadge kind={ep.kind} />
          {cat && <Badge size="sm">{cat.emoji} {cat.name}</Badge>}
          {ep.age_band && <Badge size="sm">{ep.age_band}</Badge>}
          {ep.animation && ep.animation !== 'code' && <AnimationBadge mode={ep.animation} size="sm" />}
          <ScoreBadge score={ep.score} bar={bar} />
        </div>
        {p && p.pct != null && p.pct < 100 && <Progress pct={p.pct} label={p.stage} tone="violet" />}
        {ep.status === 'failed' && ep.error && <div className="mini-err" title={ep.error}>{ep.error}</div>}
        <div className="ep-foot">
          <span>#{ep.id} · {ago(ep.created_at)}</span>
          {ep.youtube?.url ? <span className="ep-yt"><Icon name="play" size={11} /> On YouTube</span>
            : ep.publish_at ? <span><Icon name="calendar" size={12} /> {fmtDate(ep.publish_at, { month: 'short', day: 'numeric' })}</span> : null}
        </div>
      </div>
    </Link>
  )
}
