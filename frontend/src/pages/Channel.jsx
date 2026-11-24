import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { del, get, mediaUrl, put } from '../api'
import Icon from '../components/icons'
import { Badge, ChipSelect, fmtNum, PageHead, Skeleton, Spinner, useAction, useApi, useStatic, useToast } from '../components/ui'

export default function Channel() {
  const [params, setParams] = useSearchParams()
  const toast = useToast()
  const ov = useApi('/overview')
  const st = useApi('/settings')
  const langs = useStatic('/languages')
  const dub = useApi('/dubs')
  const [busy, run] = useAction()
  const [loc, setLoc] = useState([])
  const [eds, setEds] = useState([])

  useEffect(() => {
    const yt = params.get('yt')
    if (!yt) return
    if (yt === 'dub') toast('Dubbed channel connected!', 'ok')
    else if (yt === 'ok') toast('YouTube connected!', 'ok')
    else toast(`YouTube connection failed: ${params.get('error') || yt}`, 'bad')
    setParams({}, { replace: true })
  }, [params, setParams, toast])

  useEffect(() => {
    if (st.data) { setLoc(st.data.localize_languages || []); setEds(st.data.editions || []) }
  }, [st.data])

  const ch = ov.data?.channel
  const s = st.data
  const opts = (langs || []).filter((l) => l.code !== s?.language).map((l) => ({ value: l.code, label: `${l.native || l.name}${l.native && l.native !== l.name ? ` · ${l.name}` : ''}` }))
  const dirty = s && JSON.stringify(loc) !== JSON.stringify(s.localize_languages || [])

  const langName = (c) => (langs || []).find((l) => l.code === c)?.name || c
  const when = (v) => new Date(v).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  const connect = (channel = 'main') => run('connect', async () => {
    const r = await get(`/youtube/connect?channel=${channel}`)
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
            <button className="btn" onClick={() => connect()} disabled={busy === 'connect'}><Icon name="refresh" size={15} />Reconnect</button>
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
            <button className="btn primary lg" onClick={() => connect()} disabled={busy === 'connect'}>{busy === 'connect' ? <Spinner /> : <Icon name="play" size={16} />}Connect YouTube</button>
          </>
        )}
      </section>

      <section className="card">
        <div className="card-head">
          <h2><Icon name="globe" size={18} />Dubbed channel</h2>
          {dub.data && <Badge tone={dub.data.connected ? 'green' : 'neutral'} dot>{dub.data.connected ? 'Connected' : 'Not connected'}</Badge>}
        </div>
        {!dub.data ? <Skeleton h={120} /> : (
          <>
            {dub.data.connected ? (
              <div className="channel-card dub">
                {dub.data.thumb ? <img src={mediaUrl(dub.data.thumb)} alt="" className="ch-avatar" /> : <div className="ch-avatar ph"><Icon name="globe" size={28} /></div>}
                <div className="ch-info">
                  <h3 className="h4">{dub.data.title}</h3>
                  <div className="ch-stats">
                    <span><b>{fmtNum(dub.data.subscribers)}</b> subscribers</span>
                    <span><b>{fmtNum(dub.data.views)}</b> views</span>
                    <span><b>{fmtNum(dub.data.videos)}</b> videos</span>
                  </div>
                </div>
                <button className="btn" onClick={() => connect('dub')} disabled={busy === 'connect'}><Icon name="refresh" size={15} />Reconnect</button>
                <button className="btn ghost" disabled={busy === 'disc'}
                  onClick={async () => { const r = await run('disc', () => del('/dubs/channel'), 'Dubbed channel disconnected'); if (r) dub.reload() }}>Disconnect</button>
              </div>
            ) : (
              <div className="row between wrap-row">
                <p className="muted grow">A second YouTube channel for the other languages. Your main channel stays English only. Each episode is drawn once; only the voices are new.</p>
                <button className="btn primary" onClick={() => connect('dub')} disabled={busy === 'connect' || !ch?.connected}>{busy === 'connect' ? <Spinner /> : <Icon name="plug" size={15} />}Connect dubbed channel</button>
              </div>
            )}
            {dub.data.error && <p className="small danger-text">{dub.data.error}</p>}
            {!s ? <Skeleton h={80} /> : (
              <div className="block">
                <h3 className="h4">Languages</h3>
                <p className="muted small">Every new episode is dubbed into these and uploaded to the dubbed channel after the English one is live, one at a time, in a playlist per language.</p>
                <ChipSelect options={opts} value={eds} onChange={setEds} />
                <div className="row end">
                  <button className="btn primary" disabled={JSON.stringify(eds) === JSON.stringify(s.editions || []) || busy === 'saveEds'}
                    onClick={async () => { const r = await run('saveEds', () => put('/settings', { editions: eds }), 'Dub languages saved'); if (r) st.setData(r) }}>
                    {busy === 'saveEds' ? <Spinner /> : <Icon name="save" size={15} />}Save dub languages
                  </button>
                </div>
              </div>
            )}
            {[['Coming up', dub.data.upcoming], ['Live', dub.data.recent], ['Needs attention', dub.data.failed]].map(([name, rows]) => rows?.length > 0 && (
              <div className="block" key={name}>
                <h3 className="h4">{name}</h3>
                <ul className="mini-list">
                  {rows.map((r) => (
                    <li key={`${r.episode}${r.lang}`}>
                      <span><b>{langName(r.lang)}</b> · {r.title}{r.error && <span className="small danger-text"> · {r.error}</span>}</span>
                      <span className="row">{r.publish_at && <span className="muted small">{when(r.publish_at)}</span>}{r.url && <a href={r.url} target="_blank" rel="noreferrer" className="link-sm">YouTube</a>}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
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
            <div className="row end">
              <button className="btn ghost" disabled={!dirty} onClick={() => setLoc(s.localize_languages || [])}>Undo</button>
              <button className="btn primary" disabled={!dirty || busy === 'save'}
                onClick={async () => { const r = await run('save', () => put('/settings', { localize_languages: loc }), 'Languages saved'); if (r) st.setData(r) }}>
                {busy === 'save' ? <Spinner /> : <Icon name="save" size={15} />}Save languages
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
