import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { get, mediaUrl, put } from '../api'
import Icon from '../components/icons'
import { Badge, ChipSelect, fmtNum, PageHead, Skeleton, Spinner, useAction, useApi, useStatic, useToast } from '../components/ui'

export default function Channel() {
  const [params, setParams] = useSearchParams()
  const toast = useToast()
  const ov = useApi('/overview')
  const st = useApi('/settings')
  const langs = useStatic('/languages')
  const [busy, run] = useAction()
  const [loc, setLoc] = useState([])
  const [eds, setEds] = useState([])

  useEffect(() => {
    const yt = params.get('yt')
    if (!yt) return
    if (yt === 'ok') toast('YouTube connected!', 'ok')
    else toast(`YouTube connection failed: ${params.get('error') || yt}`, 'bad')
    setParams({}, { replace: true })
  }, [params, setParams, toast])

  useEffect(() => {
    if (st.data) { setLoc(st.data.localize_languages || []); setEds(st.data.editions || []) }
  }, [st.data])

  const ch = ov.data?.channel
  const s = st.data
  const opts = (langs || []).filter((l) => l.code !== s?.language).map((l) => ({ value: l.code, label: `${l.native || l.name}${l.native && l.native !== l.name ? ` · ${l.name}` : ''}` }))
  const dirty = s && (JSON.stringify(loc) !== JSON.stringify(s.localize_languages || []) || JSON.stringify(eds) !== JSON.stringify(s.editions || []))

  const connect = () => run('connect', async () => {
    const r = await get('/youtube/connect')
    if (!r?.url) throw new Error('Backend did not return a Google sign-in URL')
    window.location.href = r.url
  })

  return (
    <div className="page">
      <PageHead title="Channel" sub="Where episodes go, and who they reach." />

      <section className={`card channel-card ${ch?.connected ? 'on' : ''}`}>
        {!ov.data ? (
          <>
            <div className="ch-avatar ph skel" aria-hidden="true" />
            <div className="ch-info" aria-busy="true"><Skeleton h={22} w={96} r={999} /><Skeleton h={28} w="70%" /><Skeleton h={20} w="85%" /></div>
            <span className="btn skel" style={{ width: 120 }} aria-hidden="true" />
          </>
        ) : ch?.connected ? (
          <>
            {ch.thumb ? <img src={mediaUrl(ch.thumb)} alt="" className="ch-avatar" /> : <div className="ch-avatar ph"><Icon name="tv" size={28} /></div>}
            <div className="ch-info">
              <Badge tone="green" dot>Connected</Badge>
              <h2>{ch.title}</h2>
              <div className="ch-stats">
                <span><b>{fmtNum(ch.subscribers)}</b> subscribers</span>
                <span><b>{fmtNum(ch.views)}</b> views</span>
                <span><b>{fmtNum(ch.videos)}</b> videos</span>
              </div>
            </div>
            <button className="btn" onClick={connect} disabled={busy === 'connect'}><Icon name="refresh" size={15} />Reconnect</button>
          </>
        ) : (
          <>
            <div className="ch-avatar ph"><Icon name="plug" size={28} /></div>
            <div className="ch-info">
              <Badge tone="red" dot>Not connected</Badge>
              <h2>Connect your YouTube channel</h2>
              <p className="muted">Sign in with Google to let the studio upload, schedule and read analytics. Set YT_CLIENT_ID and YT_CLIENT_SECRET in Settings → Keys first.</p>
              {ch?.error && <p className="small danger-text">{ch.error}</p>}
            </div>
            <button className="btn primary lg" onClick={connect} disabled={busy === 'connect'}>{busy === 'connect' ? <Spinner /> : <Icon name="play" size={16} />}Connect YouTube</button>
          </>
        )}
      </section>

      <section className="card mfk">
        <div className="mfk-head">
          <span className="mfk-lock"><Icon name="lock" size={20} /></span>
          <div className="grow">
            <h2>Made for kids — always on</h2>
            <p className="muted small">Locked. This can’t be turned off from the studio.</p>
          </div>
          <Badge tone="green" icon="check">On</Badge>
        </div>
        <p>Every upload is marked <b>made for kids</b>, as required by COPPA and YouTube’s policies for content aimed at children. On made-for-kids videos YouTube switches off:</p>
        <ul className="mfk-list">
          <li><Icon name="file" size={16} /><div><b>Comments</b> — so the show never asks kids to comment.</div></li>
          <li><Icon name="bell" size={16} /><div><b>The notification bell</b> — so we never say “ring the bell”.</div></li>
          <li><Icon name="target" size={16} /><div><b>Personalised ads</b> and some other features — only contextual ads can run.</div></li>
        </ul>
        <div className="banner info">
          <Icon name="users" size={18} />
          <div><b>Subscribe still works.</b> Each episode ends with <i>one</i> short line addressed to grown-ups, plus the description and end card. Kids are never asked to subscribe, click or comment.</div>
        </div>
      </section>

      <section className="card">
        <div className="card-head"><h2><Icon name="globe" size={18} />Reach more families</h2></div>
        {!s ? <Skeleton h={120} /> : (
          <>
            <div className="block">
              <h3 className="h4">Localized titles &amp; descriptions</h3>
              <p className="muted small">Translated metadata on the same video — cheap, and helps search in other languages.</p>
              <ChipSelect options={opts} value={loc} onChange={setLoc} />
            </div>
            <div className="block">
              <h3 className="h4">Dubbed editions</h3>
              <p className="muted small">A fully re-voiced copy of each episode, rendered and uploaded as its own video. Costs more voice and render time per language.</p>
              <ChipSelect options={opts} value={eds} onChange={setEds} />
            </div>
            <div className="row end">
              <button className="btn ghost" disabled={!dirty} onClick={() => { setLoc(s.localize_languages || []); setEds(s.editions || []) }}>Undo</button>
              <button className="btn primary" disabled={!dirty || busy === 'save'}
                onClick={async () => { const r = await run('save', () => put('/settings', { localize_languages: loc, editions: eds }), 'Languages saved'); if (r) st.setData(r) }}>
                {busy === 'save' ? <Spinner /> : <Icon name="save" size={15} />}Save languages
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
