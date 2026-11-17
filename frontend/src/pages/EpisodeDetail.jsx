import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError, authedUrl, del, mediaUrl, patch, post } from '../api'
import ScriptView from '../components/ScriptView'
import Scorecard from '../components/Scorecard'
import { KindBadge } from '../components/EpisodeCard'
import Icon from '../components/icons'
import { AnimationBadge, AnimationPicker, EstimateBox, MODE_MAP, PaletteBadge, PalettePicker, StyleBadge, StylePicker, useAIVideo, usePalettes, useStyles } from '../components/looks'
import {
  ago, Badge, Empty, Field, fmtDate, fmtDur, fmtUsd, Modal, Progress, SafeImg, Seg, Skeleton, Spinner, shownStatus, StatusPill, Tabs, TagInput,
  toLocalInput, useAction, useApi, useCategoryMap, useStatic, useToast,
} from '../components/ui'

const LIVE = new Set(['planned', 'writing', 'rendering', 'publishing'])
const CAN = {
  approve: ['review', 'scripted', 'failed'],
  reject: ['review', 'scripted', 'approved', 'failed'],
  rewrite: ['scripted', 'review', 'failed', 'rejected', 'approved'],
  render: ['scripted', 'review', 'failed', 'approved', 'rejected', 'published'],
  restyle: ['scripted', 'review', 'failed', 'approved', 'rejected', 'published'],
  publish: ['review', 'approved'],
  edition: ['review', 'approved', 'published'],
  short: ['review', 'approved', 'published'],
}

/* ------------------------------------------------------------ media pane */
function Media({ ep, seekRef }) {
  const videoRef = useRef(null)
  const end = useMemo(() => {
    const tl = ep.timeline || []
    return Math.max(ep.duration || 0, tl.length ? tl[tl.length - 1].end || 0 : 0) || 600
  }, [ep.duration, ep.timeline])
  const [t, setT] = useState(5)
  const [shown, setShown] = useState(5)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(false)
  const video = mediaUrl(ep.video_url)

  useEffect(() => { const h = setTimeout(() => setShown(t), 250); return () => clearTimeout(h) }, [t])
  useEffect(() => { setLoading(true); setErr(false) }, [shown])

  seekRef.current = (sec) => {
    if (video && videoRef.current) { videoRef.current.currentTime = sec; videoRef.current.play?.().catch(() => {}) }
    else { setT(Math.floor(sec) + 1) }
  }

  return (
    <div className="card flush media">
      {video ? (
        <video ref={videoRef} className="player" src={video} controls preload="metadata" poster={mediaUrl(ep.thumb_url) || undefined} />
      ) : ep.script ? (
        <>
          <div className="frame">
            {!err && <img src={authedUrl(`/episodes/${ep.id}/preview.png?t=${shown}`)} alt={`Frame at ${fmtDur(shown)}`}
              onLoad={() => setLoading(false)} onError={() => { setLoading(false); setErr(true) }} className={loading ? 'dim' : ''} />}
            {err && <div className="frame-ph"><Icon name="image" size={28} /><span>No preview for this moment yet</span></div>}
            {loading && !err && <div className="frame-load"><Spinner size={22} /></div>}
            <span className="frame-badge">Preview · {fmtDur(shown)}</span>
          </div>
          <div className="scrub">
            <input type="range" min={0} max={Math.ceil(end)} value={t} onChange={(e) => setT(Number(e.target.value))} aria-label="Preview time" />
            <span className="mono tiny">{fmtDur(t)} / {fmtDur(end)}</span>
          </div>
        </>
      ) : (
        <div className="frame"><div className="frame-ph"><Icon name="pen" size={28} /><span>The writers are still working — frames appear once there’s a script.</span></div></div>
      )}
      {ep.timeline?.length > 0 && (
        <div className="chapters" aria-label="Chapters">
          {ep.timeline.map((c, i) => (
            <button key={i} className="chapter" onClick={() => seekRef.current(c.start)} title={`${c.title || c.kind} · ${fmtDur(c.start)}`}
              style={{ flexGrow: Math.max(1, (c.end || 0) - (c.start || 0)) }}>
              <span>{c.title || c.kind}</span><small>{fmtDur(c.start)}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/* -------------------------------------------------------- AI video info */
function AIVideoPanel({ ai, onSeek }) {
  if (!ai) return null
  const clips = ai.clips || []
  const ok = clips.filter((c) => c.status === 'ok').length
  return (
    <section className="card">
      <div className="card-head">
        <h3><Icon name="sparkles" size={16} />AI video</h3>
        <AnimationBadge mode={ai.mode} size="sm" />
      </div>
      <div className="kv-row">
        <div><span>Provider</span><b>{ai.provider || '—'}</b></div>
        <div><span>Clips</span><b>{ok}/{clips.length}</b></div>
        <div><span>Spend</span><b>{fmtUsd(ai.usd)}</b></div>
      </div>
      {clips.length > 0 && (
        <ul className="clip-list">
          {clips.map((c, i) => (
            <li key={i}>
              <button className="clip" onClick={() => onSeek(c.t)} title="Jump to this shot">
                <span className="mono">{fmtDur(c.t)}</span>
                <span className="muted">{c.dur}s</span>
                <Badge size="sm" tone={c.status === 'ok' ? 'green' : c.status === 'failed' ? 'red' : 'neutral'}>{c.status}</Badge>
                <span className="clip-usd mono">{c.usd != null ? fmtUsd(c.usd) : ''}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/* -------------------------------------------------------- metadata tab */
function MetaEditor({ ep, onSaved }) {
  const [busy, run] = useAction()
  const [title, setTitle] = useState(ep.meta?.title || '')
  const [desc, setDesc] = useState(ep.meta?.description || '')
  const [tags, setTags] = useState(ep.meta?.tags || [])
  const langs = useStatic('/languages')
  useEffect(() => {
    setTitle(ep.meta?.title || ''); setDesc(ep.meta?.description || ''); setTags(ep.meta?.tags || [])
  }, [ep.id, ep.meta])

  if (!ep.meta) return <Empty compact icon="tag" title="No metadata yet">Title, description and tags are generated with the script.</Empty>
  const dirty = title !== (ep.meta.title || '') || desc !== (ep.meta.description || '') || JSON.stringify(tags) !== JSON.stringify(ep.meta.tags || [])
  const tagChars = tags.join(',').length
  const langName = (code) => langs?.find((l) => l.code === code)?.name || code
  const loc = Object.entries(ep.meta.localizations || {})

  return (
    <div className="meta-editor">
      <Field label="Title" counter={<span className={`counter ${title.length > 100 ? 'over' : ''}`}>{title.length}/100</span>}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field label="Description" counter={<span className={`counter ${desc.length > 5000 ? 'over' : ''}`}>{desc.length}/5000</span>}
        hint="The first two lines show above the fold — keep them parent-friendly.">
        <textarea rows={10} value={desc} onChange={(e) => setDesc(e.target.value)} />
      </Field>
      <Field label="Tags" counter={<span className={`counter ${tagChars > 500 ? 'over' : ''}`}>{tagChars}/500</span>} hint="Enter or comma to add · Backspace removes the last one">
        <TagInput value={tags} onChange={setTags} />
      </Field>
      <div className="chips">
        {ep.meta.category_id && <Badge size="sm">YouTube category {ep.meta.category_id}</Badge>}
        {ep.meta.playlist && <Badge size="sm" icon="list">Playlist: {ep.meta.playlist}</Badge>}
      </div>
      <div className="row end">
        <button className="btn ghost" disabled={!dirty} onClick={() => { setTitle(ep.meta.title || ''); setDesc(ep.meta.description || ''); setTags(ep.meta.tags || []) }}><Icon name="undo" size={15} />Undo</button>
        <button className="btn primary" disabled={!dirty || !!busy || title.length > 100 || !title.trim()}
          onClick={async () => { const r = await run('save', () => patch(`/episodes/${ep.id}`, { meta: { title: title.trim(), description: desc, tags } }), 'Metadata saved'); if (r) onSaved(r) }}>
          {busy ? <Spinner /> : <Icon name="save" size={15} />}Save metadata
        </button>
      </div>
      {loc.length > 0 && (
        <div className="block">
          <h4>Localizations</h4>
          <div className="loc-list">
            {loc.map(([code, v]) => (
              <div key={code} className="loc">
                <Badge tone="blue" size="sm">{langName(code)} · {code}</Badge>
                <div><b>{v.title}</b><p className="muted small clamp3">{v.description}</p></div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function SafetyTab({ safety }) {
  if (!safety) return <Empty compact icon="shield" title="Safety gate hasn’t run yet" />
  const issues = safety.issues || []
  return (
    <div>
      <div className={`banner ${safety.ok ? 'ok' : 'bad'}`}>
        <Icon name={safety.ok ? 'shieldCheck' : 'ban'} size={18} />
        <div><b>{safety.ok ? 'Passed the safety gate' : 'Blocked by the safety gate'}</b>
          <div className="small">{issues.length ? `${issues.filter((i) => i.level === 'block').length} blocking · ${issues.filter((i) => i.level !== 'block').length} warnings` : 'No words or themes flagged.'}</div></div>
      </div>
      {issues.length > 0 && (
        <div className="scroll-x">
          <table className="table">
            <thead><tr><th>Level</th><th>Rule</th><th>Word</th><th>Where</th></tr></thead>
            <tbody>{issues.map((i, k) => (
              <tr key={k}>
                <td><Badge size="sm" tone={i.level === 'block' ? 'red' : 'amber'}>{i.level === 'block' ? 'Block' : 'Warn'}</Badge></td>
                <td>{i.rule}</td><td><code>{i.word}</code></td><td className="muted small">{i.where}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function QATab({ qa }) {
  if (!qa) return <Empty compact icon="checkCircle" title="QA runs after rendering" />
  return (
    <div>
      <div className={`banner ${qa.ok ? 'ok' : 'bad'}`}><Icon name={qa.ok ? 'checkCircle' : 'alertCircle'} size={18} /><b>{qa.ok ? 'All render checks passed' : 'Some render checks failed'}</b></div>
      <ul className="checks">
        {(qa.checks || []).map((c, i) => (
          <li key={i} className={c.ok ? 'ok' : 'bad'}><Icon name={c.ok ? 'check' : 'x'} size={15} strokeWidth={2.4} /><b>{c.name}</b><span className="muted small">{c.detail}</span></li>
        ))}
      </ul>
    </div>
  )
}

function LogTab({ log }) {
  if (!log?.length) return <Empty compact icon="activity" title="Nothing logged yet" />
  return (
    <ul className="log">
      {[...log].reverse().map((l, i) => (
        <li key={i} className={`lvl-${l.level}`}>
          <span className="log-time mono" title={fmtDate(l.created_at)}>{fmtDate(l.created_at, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
          <span className="log-lvl">{l.level}</span>
          <span className="log-msg">{l.msg}</span>
        </li>
      ))}
    </ul>
  )
}

/* --------------------------------------------------------------- page */
export default function EpisodeDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const { data: ep, setData, loading, error, reload } = useApi(`/episodes/${id}`, {
    ms: (d) => (d && (LIVE.has(d.status) || (d.progress && d.progress.pct != null && d.progress.pct < 100)) ? 4000 : 0),
  })
  const settings = useApi('/settings', { quiet: true }).data
  const psych = useStatic('/psychology')
  const cast = useStatic('/cast')
  const langs = useStatic('/languages')
  const { map: styleMap } = useStyles()
  const { map: palMap } = usePalettes()
  const [, catMap] = useCategoryMap()
  const [tab, setTab] = useState('script')
  const [busy, run] = useAction()
  const [modal, setModal] = useState(null)
  const seekRef = useRef(() => {})

  if (loading && !ep) return <div className="page"><Skeleton h={36} w={420} /><div className="detail"><Skeleton h={360} r={14} /><Skeleton h={360} r={14} /></div></div>
  if (!ep) return <div className="page"><Empty icon="film" title="Episode not found" action={<Link className="btn" to="/episodes"><Icon name="arrowLeft" size={15} />All episodes</Link>}>{error?.message}</Empty></div>

  const act = async (key, fn, msg) => {
    const r = await run(key, fn, msg)
    if (r && typeof r === 'object' && r.id != null && String(r.id) === String(ep.id)) setData(r)
    else if (r !== undefined) reload(true)
    return r
  }
  const can = (k) => CAN[k].includes(ep.status)
  const cat = catMap[ep.category]
  const band = psych?.bands?.[ep.age_band]
  const editions = Object.entries(ep.editions || {})
  const title = ep.meta?.title || ep.script?.title_idea || ep.topic || `Episode #${ep.id}`
  const live = LIVE.has(ep.status)

  return (
    <div className="page">
      <div className="crumbs">
        <Link to="/episodes"><Icon name="arrowLeft" size={14} />Episodes</Link>
        {ep.parent_id != null && <><span>/</span><Link to={`/episodes/${ep.parent_id}`}>Parent #{ep.parent_id}</Link></>}
      </div>

      <header className="detail-head">
        <div className="detail-title">
          <h1>{title}</h1>
          <div className="head-meta">
            <StatusPill status={shownStatus(ep)} />
            <KindBadge kind={ep.kind} />
            {cat && <Badge>{cat.emoji} {cat.name}</Badge>}
            <Badge icon="smile">{band?.label || ep.age_band}</Badge>
            <Badge icon="globe">{ep.language}</Badge>
            {(ep.art_style || ep.rendered_style) && <StyleBadge id={ep.art_style} rendered={ep.rendered_style} map={styleMap} />}
            {ep.animation && <AnimationBadge mode={ep.animation} />}
            {(ep.palette || ep.rendered_palette) && <PaletteBadge id={ep.palette} rendered={ep.rendered_palette} map={palMap} />}
          </div>
          <div className="muted small">#{ep.id} · created {ago(ep.created_at)} · updated {ago(ep.updated_at)}{ep.duration ? ` · ${fmtDur(ep.duration)}` : ''}</div>
          {ep.variant && Object.values(ep.variant).some((v) => v != null) && (
            <div className="head-meta variant">
              <span className="muted tiny"><Icon name="flask" size={12} /> Optimizer variant</span>
              {ep.variant.pace && <Badge size="sm" tone="blue">pace {ep.variant.pace}</Badge>}
              {ep.variant.minutes != null && <Badge size="sm" tone="blue">{ep.variant.minutes} min</Badge>}
              {ep.variant.thumb && <Badge size="sm" tone="blue">thumb {ep.variant.thumb}</Badge>}
              {ep.variant.title && <Badge size="sm" tone="blue">title {ep.variant.title}</Badge>}
              {ep.variant.style && <Badge size="sm" tone="blue">look {ep.variant.style}</Badge>}
            </div>
          )}
          {ep.why && <p className="why"><Icon name="bulb" size={14} />{ep.why}</p>}
        </div>
        <div className="detail-cta">
          {ep.youtube?.url && <a className="btn yt" href={ep.youtube.url} target="_blank" rel="noreferrer"><Icon name="play" size={15} />Watch on YouTube</a>}
          {can('approve') && <button className="btn primary" disabled={!!busy} onClick={() => setModal('approve')}><Icon name="check" size={16} strokeWidth={2.2} />Approve</button>}
          {can('publish') && <button className="btn" disabled={!!busy} onClick={() => setModal('publish')}><Icon name="rocket" size={15} />Publish now</button>}
        </div>
      </header>

      {ep.progress && ep.progress.pct != null && ep.progress.pct < 100 && <div className="card live-card"><Progress pct={ep.progress.pct} label={ep.progress.stage} tone="violet" /></div>}
      {ep.error && <div className="banner bad"><Icon name="alertCircle" size={18} /><div><b>Something went wrong</b><div className="small mono wrap">{ep.error}</div></div></div>}

      <div className="detail">
        <div className="detail-left">
          <Media ep={ep} seekRef={seekRef} />

          <section className="card actions-card">
            <div className="card-head"><h3>Actions</h3>{ep.publish_at && <span className="muted small"><Icon name="calendar" size={13} /> {shownStatus(ep) === 'published' ? 'Live since' : shownStatus(ep) === 'upcoming' ? 'Uploaded · goes public' : 'Scheduled'} {fmtDate(ep.status === 'published' ? ep.published_at || ep.publish_at : ep.publish_at)}</span>}</div>
            <div className="action-grid">
              <button className="btn" disabled={!can('restyle') || !ep.script || !!busy || live} onClick={() => setModal('restyle')}><Icon name="palette" size={15} />Restyle / re-render</button>
              <button className="btn" disabled={!can('render') || !!busy} onClick={() => act('render', () => post(`/episodes/${ep.id}/render`), 'Re-render queued')}>{busy === 'render' ? <Spinner size={14} /> : <Icon name="refresh" size={15} />}Re-render</button>
              <button className="btn" disabled={!can('rewrite') || !!busy} onClick={() => act('rewrite', () => post(`/episodes/${ep.id}/rewrite`), 'Rewrite queued')}>{busy === 'rewrite' ? <Spinner size={14} /> : <Icon name="pen" size={15} />}Rewrite script</button>
              <button className="btn" disabled={!can('edition') || !!busy} onClick={() => setModal('edition')}><Icon name="globe" size={15} />Dubbed edition</button>
              {(ep.kind || 'episode') === 'episode' && (
                <button className="btn" disabled={!can('short') || !!busy}
                  onClick={async () => { const r = await run('short', () => post(`/episodes/${ep.id}/short`), 'Short queued'); if (r?.id != null && String(r.id) !== String(ep.id)) nav(`/episodes/${r.id}`); else if (r) reload(true) }}>
                  {busy === 'short' ? <Spinner size={14} /> : <Icon name="phone" size={15} />}Cut a Short
                </button>
              )}
              <button className="btn" disabled={!can('reject') || !!busy} onClick={() => act('reject', () => post(`/episodes/${ep.id}/reject`), 'Episode rejected')}><Icon name="ban" size={15} />Reject</button>
              <button className="btn ghost danger-text" disabled={!!busy} onClick={() => setModal('delete')}><Icon name="trash" size={15} />Delete</button>
            </div>
          </section>

          <AIVideoPanel ai={ep.ai_video} onSeek={(s) => seekRef.current(s)} />

          {ep.source && (
            <section className="card source-box">
              <h3><Icon name="bookOpen" size={16} />Adapted from</h3>
              <p><b>{ep.source.title || ep.source.book}</b>{ep.source.title && ep.source.book && ep.source.book !== ep.source.title ? <> — from <i>{ep.source.book}</i></> : null}</p>
              {ep.source.authors?.length > 0 && <p className="muted small">by {Array.isArray(ep.source.authors) ? ep.source.authors.join(', ') : ep.source.authors}</p>}
              <div className="row wrap-row">
                {ep.source.license && <Badge tone="green" size="sm">{ep.source.license}</Badge>}
                {ep.source.url && <a href={ep.source.url} target="_blank" rel="noreferrer" className="link-sm">Read the original<Icon name="external" size={12} /></a>}
              </div>
            </section>
          )}

          {editions.length > 0 && (
            <section className="card">
              <h3><Icon name="globe" size={16} />Editions</h3>
              <ul className="mini-list">
                {editions.map(([code, e]) => (
                  <li key={code}>
                    <b>{langs?.find((l) => l.code === code)?.name || code}</b>
                    <span className="row">
                      <StatusPill status={shownStatus(e)} small />
                      {e.video_url && <a href={mediaUrl(e.video_url)} target="_blank" rel="noreferrer" className="link-sm">Video</a>}
                      {e.youtube?.url && <a href={e.youtube.url} target="_blank" rel="noreferrer" className="link-sm">YouTube</a>}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {ep.thumb_url && (
            <section className="card thumb-row">
              <SafeImg src={mediaUrl(ep.thumb_url)} alt="YouTube thumbnail" className="thumb-big" />
              <div className="muted small"><b>YouTube thumbnail</b><br />{ep.duration ? <>Runtime {fmtDur(ep.duration)}</> : null}</div>
            </section>
          )}
        </div>

        <div className="detail-right card flush">
          <Tabs value={tab} onChange={setTab} className="tabs-pad" tabs={[
            ['script', 'Script', null, 'file'],
            ['score', 'Scorecard', ep.critic?.score != null ? Number(ep.critic.score).toFixed(ep.critic.score % 1 ? 1 : 0) : null, 'star'],
            ['safety', 'Safety', ep.safety ? (ep.safety.ok ? '✓' : '!') : null, 'shield'],
            ['meta', 'YouTube', null, 'tag'],
            ['qa', 'QA', ep.qa ? (ep.qa.ok ? '✓' : '!') : null, 'checkCircle'],
            ['log', 'Log', ep.log?.length || null, 'activity'],
          ]} />
          <div className="tab-body">
            {tab === 'script' && <ScriptView script={ep.script} timeline={ep.timeline} cast={cast} onSeek={(s) => seekRef.current(s)} />}
            {tab === 'score' && <Scorecard critic={ep.critic} bar={settings?.quality_bar} band={band} />}
            {tab === 'safety' && <SafetyTab safety={ep.safety} />}
            {tab === 'meta' && <MetaEditor ep={ep} onSaved={setData} />}
            {tab === 'qa' && <QATab qa={ep.qa} />}
            {tab === 'log' && <LogTab log={ep.log} />}
          </div>
        </div>
      </div>

      <ApproveModal open={modal === 'approve'} ep={ep} onClose={() => setModal(null)}
        onApprove={async (publish_at) => { const r = await act('approve', () => post(`/episodes/${ep.id}/approve`, { publish_at }), (x) => `Approved${x?.publish_at ? ` — publishing ${fmtDate(x.publish_at)}` : ''}`); if (r) setModal(null) }} busy={busy === 'approve'} />

      <Modal open={modal === 'publish'} title="Publish now?" icon="rocket" onClose={() => setModal(null)}
        actions={<><button className="btn ghost" onClick={() => setModal(null)}>Cancel</button>
          <button className="btn primary" disabled={busy === 'publish'} onClick={async () => { const r = await act('publish', () => post(`/episodes/${ep.id}/publish`), 'Publishing started'); if (r) setModal(null) }}>{busy === 'publish' ? <Spinner /> : null}Publish now</button></>}>
        <p>This uploads <b>{title}</b> to YouTube immediately as <b>{settings?.youtube_privacy || 'configured privacy'}</b>, skipping the schedule.</p>
      </Modal>

      <RestyleModal open={modal === 'restyle'} ep={ep} settings={settings} onClose={() => setModal(null)} busy={busy === 'restyle'}
        onSubmit={async (body) => {
          const r = await act('restyle', async () => {
            try { return await post(`/episodes/${ep.id}/restyle`, body) } catch (e) {
              if (e.status === 404 || e.status === 405) throw new ApiError(e.status, 'Restyle isn’t available on this server yet — update the backend.')
              throw e
            }
          }, 'Restyle queued — re-rendering in the new look')
          if (r) setModal(null)
        }} />

      <EditionModal open={modal === 'edition'} ep={ep} langs={langs} onClose={() => setModal(null)} busy={busy === 'edition'}
        onSubmit={async (lang) => { const r = await act('edition', () => post(`/episodes/${ep.id}/edition`, { lang }), 'Dubbed edition queued'); if (r) setModal(null) }} />

      <Modal open={modal === 'delete'} title="Delete this episode?" icon="trash" onClose={() => setModal(null)}
        actions={<><button className="btn ghost" onClick={() => setModal(null)}>Keep it</button>
          <button className="btn danger" disabled={busy === 'delete'} onClick={async () => {
            const r = await run('delete', () => del(`/episodes/${ep.id}`))
            if (r !== undefined) { toast('Episode deleted'); nav('/episodes') }
          }}>{busy === 'delete' ? <Spinner /> : null}Delete forever</button></>}>
        <p>“{title}” and its script, renders and log will be removed. {ep.youtube?.url ? <b>The YouTube video itself is not deleted.</b> : null} This can’t be undone.</p>
      </Modal>
    </div>
  )
}

function RestyleModal({ open, ep, settings, onClose, onSubmit, busy }) {
  const { info } = useAIVideo()
  const [style, setStyle] = useState(ep.art_style || 'auto')
  const [anim, setAnim] = useState(ep.animation || 'code')
  const [pal, setPal] = useState(ep.palette || 'auto')
  const { list: palettes } = usePalettes()
  useEffect(() => { if (open) { setStyle(ep.art_style || settings?.art_style || 'auto'); setAnim(ep.animation || settings?.animation || 'code'); setPal(ep.palette || settings?.palette || 'auto') } /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [open])
  const minutes = ep.duration ? Math.max(1, Math.round(ep.duration / 60)) : settings?.target_minutes || 12
  const same = style === (ep.art_style || 'auto') && anim === (ep.animation || 'code') && pal === (ep.palette || 'auto')
  return (
    <Modal open={open} wide icon="palette" title="Restyle & re-render" onClose={onClose}
      actions={<><span className="muted small grow">{MODE_MAP[anim]?.label} · same script, voices and music</span>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={busy} onClick={() => onSubmit({ art_style: style, animation: anim, palette: pal })}>{busy ? <Spinner /> : <Icon name="refresh" size={15} />}{same ? 'Re-render' : 'Restyle'}</button></>}>
      <div className="field-label"><span>Art style</span></div>
      <StylePicker value={style} onChange={setStyle} band={ep.age_band} defaultId={settings?.art_style} compact />
      {palettes.length > 0 && <>
        <div className="field-label" style={{ marginTop: 20 }}><span>Colour palette</span></div>
        <PalettePicker value={pal} onChange={setPal} list={palettes} />
      </>}
      <div className="field-label" style={{ marginTop: 20 }}><span>Animation</span></div>
      <AnimationPicker value={anim} onChange={setAnim} info={info} compact />
      <div style={{ marginTop: 12 }}><EstimateBox mode={anim} minutes={minutes} provider={settings?.ai_video_provider} info={info} budget={anim !== 'code' ? settings?.ai_video_budget_usd : null} /></div>
    </Modal>
  )
}

function ApproveModal({ open, ep, onClose, onApprove, busy }) {
  const cal = useApi(open ? '/calendar' : null, { quiet: true }).data
  const [mode, setMode] = useState('slot')
  const [when, setWhen] = useState('')
  useEffect(() => {
    if (open) { setMode(ep.publish_at ? 'pick' : 'slot'); setWhen(toLocalInput(ep.publish_at || cal?.slots?.[0] || new Date(Date.now() + 86400000).toISOString())) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
  const slots = cal?.slots || []
  const iso = when ? new Date(when).toISOString() : null
  const past = mode === 'pick' && iso && new Date(iso) < new Date()
  return (
    <Modal open={open} title="Approve & schedule" icon="checkCircle" onClose={onClose}
      actions={<><button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={busy || (mode === 'pick' && !iso)} onClick={() => onApprove(mode === 'slot' ? null : iso)}>{busy ? <Spinner /> : null}Approve</button></>}>
      <Seg value={mode} onChange={setMode} options={[['slot', 'Next free slot', 'clock'], ['pick', 'Pick a time', 'calendar']]} label="When" />
      {mode === 'slot' ? (
        <p className="muted" style={{ marginTop: 14 }}>It’ll go out at {slots[0] ? <b>{fmtDate(slots[0])}</b> : 'the next free posting slot'} following your schedule.</p>
      ) : (
        <div style={{ marginTop: 14 }}>
          <Field label="Publish at (your local time)" hint={past ? 'That time is in the past — it will publish on the next pipeline tick.' : null}>
            <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
          </Field>
          {slots.length > 0 && (
            <div className="chips" style={{ marginTop: 10 }}>
              <span className="muted small">Free slots</span>
              {slots.slice(0, 6).map((s) => <button key={s} className={`chip ${toLocalInput(s) === when ? 'on' : ''}`} onClick={() => setWhen(toLocalInput(s))}>{fmtDate(s, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</button>)}
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

function EditionModal({ open, ep, langs, onClose, onSubmit, busy }) {
  const [lang, setLang] = useState('')
  const taken = new Set([ep.language, ...Object.keys(ep.editions || {})])
  const options = (langs || []).filter((l) => !taken.has(l.code))
  useEffect(() => { if (open) setLang(options[0]?.code || '') /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [open])
  return (
    <Modal open={open} title="Add a dubbed edition" icon="globe" onClose={onClose}
      actions={<><button className="btn ghost" onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy || !lang} onClick={() => onSubmit(lang)}>{busy ? <Spinner /> : null}Queue edition</button></>}>
      <p className="muted">The script is translated, re-voiced and rendered as a separate video for that language’s audience.</p>
      <Field label="Language">
        <select value={lang} onChange={(e) => setLang(e.target.value)}>
          {options.map((l) => <option key={l.code} value={l.code}>{l.name}{l.native && l.native !== l.name ? ` — ${l.native}` : ''}</option>)}
        </select>
      </Field>
    </Modal>
  )
}
