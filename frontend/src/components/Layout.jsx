import { Suspense, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { post } from '../api'
import Icon from './icons'
import Sun from './Sun'
import { ErrorBoundary, Spinner, useAction, useApi } from './ui'

const NAV = [
  [null, [
    ['/', 'home', 'Home'],
    ['/episodes', 'film', 'Episodes', 'review'],
    ['/calendar', 'calendar', 'Schedule'],
  ]],
  ['Studio', [
    ['/characters', 'users', 'Characters'],
    ['/looks', 'palette', 'Looks'],
    ['/library', 'bookOpen', 'Library'],
  ]],
  ['Grow', [
    ['/insights', 'chart', 'Insights'],
    ['/channel', 'tv', 'Channel'],
  ]],
  ['System', [
    ['/settings', 'settings', 'Settings'],
    ['/activity', 'activity', 'Activity'],
  ]],
]

const THEMES = [['auto', 'monitor', 'System theme'], ['light', 'sun', 'Light theme'], ['dark', 'moon', 'Dark theme']]

export default function Layout({ theme, setTheme, onLogout }) {
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  const { data: ov } = useApi('/overview', { ms: (d) => (d?.worker?.busy ? 5000 : 20000), quiet: true })
  const [busy, run] = useAction()
  useEffect(() => { setOpen(false); window.scrollTo(0, 0) }, [loc.pathname])
  useEffect(() => {
    if (!open) return undefined
    const k = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [open])

  const review = ov?.counts?.review || 0
  const name = ov?.settings_summary?.channel_name || 'Hoppy Hop Hop'
  const w = ov?.worker

  return (
    <div className={`app ${open ? 'nav-open' : ''}`}>
      <a className="skip-link" href="#main">Skip to content</a>

      <header className="topbar">
        <button className="icon-btn" onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open}><Icon name="menu" size={20} /></button>
        <Link to="/" className="brand mini"><Sun size={28} /><b>CartoonForge</b></Link>
        <Link to="/create" className="btn primary sm"><Icon name="plus" size={16} />New</Link>
      </header>

      <div className="scrim" onClick={() => setOpen(false)} aria-hidden="true" />

      <aside className="sidebar" aria-label="Main navigation">
        <div className="sb-top">
          <Link to="/" className="brand">
            <Sun size={34} />
            <span className="brand-text">
              <b>CartoonForge</b>
              <small>{name}</small>
            </span>
          </Link>
          <button className="icon-btn sb-close" onClick={() => setOpen(false)} aria-label="Close menu"><Icon name="x" /></button>
        </div>

        <Link to="/create" className="btn primary block sb-create"><Icon name="plus" size={17} strokeWidth={2.2} />New episode</Link>

        <div className="sb-scroll">
          {NAV.map(([group, items]) => (
            <nav className="sb-group" key={group || 'main'} aria-label={group || 'Main'}>
              {group && <div className="sb-label">{group}</div>}
              {items.map(([to, icon, label, badge]) => (
                <NavLink key={to} to={to} end={to === '/'} className="sb-link">
                  <Icon name={icon} size={18} />
                  <span>{label}</span>
                  {badge === 'review' && review > 0 && <span className="sb-count" title={`${review} waiting for review`}>{review}</span>}
                </NavLink>
              ))}
            </nav>
          ))}
        </div>

        <div className="sb-foot">
          <div className={`worker ${w?.busy ? 'busy' : ''}`}>
            <span className="worker-dot" />
            <div className="worker-text">
              <b>{w?.busy ? 'Studio is working' : 'Studio idle'}</b>
              <small>
                {w?.busy && w.current
                  ? <>Ep <Link to={`/episodes/${w.current.id}`}>#{w.current.id}</Link> · {w.current.stage}{w.current.pct != null ? ` ${Math.round(w.current.pct)}%` : ''}</>
                  : ov?.settings_summary ? (ov.settings_summary.autopilot ? 'Autopilot on' : 'Review before publish') : '…'}
                {w?.mode ? ` · ${w.mode}` : ''}
              </small>
            </div>
            <button className="icon-btn" disabled={busy === 'tick'} title="Run the pipeline now" aria-label="Run the pipeline now"
              onClick={() => run('tick', () => post('/tick'), (r) => `Pipeline ran${r?.result ? `: ${typeof r.result === 'string' ? r.result : JSON.stringify(r.result)}` : ''}`)}>
              {busy === 'tick' ? <Spinner size={14} /> : <Icon name="play" size={15} />}
            </button>
          </div>
          <div className="sb-row">
            <div className="theme-seg" role="radiogroup" aria-label="Theme">
              {THEMES.map(([id, icon, label]) => (
                <button key={id} role="radio" aria-checked={theme === id} className={theme === id ? 'on' : ''} onClick={() => setTheme(id)} title={label} aria-label={label}>
                  <Icon name={icon} size={15} />
                </button>
              ))}
            </div>
            <button className="btn ghost sm" onClick={onLogout}><Icon name="logout" size={15} />Sign out</button>
          </div>
        </div>
      </aside>

      <main className="main" id="main" tabIndex={-1}>
        <ErrorBoundary resetKey={loc.pathname}>
          <Suspense fallback={<div className="page-loading" aria-busy="true" />}><Outlet /></Suspense>
        </ErrorBoundary>
      </main>
    </div>
  )
}
