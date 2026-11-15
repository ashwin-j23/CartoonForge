import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from '../components/icons'
import { ago, Empty, fmtDate, PageHead, Seg, Skeleton, useApi } from '../components/ui'

const LEVELS = [['all', 'All'], ['info', 'Info'], ['warn', 'Warnings'], ['error', 'Errors']]
const norm = (l) => (l === 'warning' ? 'warn' : l === 'err' || l === 'critical' ? 'error' : l || 'info')

export default function Activity() {
  const [limit, setLimit] = useState(200)
  const { data, loading } = useApi(`/events?limit=${limit}`, { ms: 10000 })
  const [level, setLevel] = useState('all')
  const [q, setQ] = useState('')
  const list = useMemo(() => (data || []).filter((e) => (level === 'all' || norm(e.level) === level) && (!q || String(e.msg).toLowerCase().includes(q.toLowerCase()))), [data, level, q])

  return (
    <div className="page">
      <PageHead title="Activity" sub="Everything the studio did, newest first. Refreshes every 10 seconds." />
      <div className="toolbar">
        <label className="search-box">
          <Icon name="search" size={16} />
          <input type="search" placeholder="Filter messages" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter messages" />
        </label>
        <Seg value={level} onChange={setLevel} size="sm" options={LEVELS} label="Level" />
      </div>
      <div className="card flush">
        {loading && !data ? <div className="pad"><Skeleton h={22} count={12} style={{ marginBottom: 8 }} /></div> : list.length === 0 ? <Empty icon="activity" title="Quiet so far">Nothing matches.</Empty> : (
          <ul className="log events">
            {list.map((e, i) => (
              <li key={i} className={`lvl-${norm(e.level)}`}>
                <span className="log-time mono" title={fmtDate(e.created_at)}>{ago(e.created_at)}</span>
                <span className="log-lvl">{norm(e.level)}</span>
                <span className="log-msg">{e.msg}</span>
                {e.episode_id != null && <Link to={`/episodes/${e.episode_id}`} className="log-ep">#{e.episode_id}</Link>}
              </li>
            ))}
          </ul>
        )}
        {data?.length >= limit && <div className="center pad"><button className="btn ghost sm" onClick={() => setLimit(limit + 200)}>Load more</button></div>}
      </div>
    </div>
  )
}
