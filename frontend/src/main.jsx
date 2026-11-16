import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { auth, LOGOUT_EVENT } from './api'
import { ToastProvider } from './components/ui'
import Layout from './components/Layout'
import Login from './pages/Login'
import Home from './pages/Home'
import Episodes from './pages/Episodes'
import EpisodeDetail from './pages/EpisodeDetail'
import Create from './pages/Create'
import Characters from './pages/Characters'
import Looks from './pages/Looks'
import Library from './pages/Library'
import Insights from './pages/Insights'
import Calendar from './pages/Calendar'
import Channel from './pages/Channel'
import Settings from './pages/Settings'
import Activity from './pages/Activity'
import Feedback from './pages/Feedback'
import './styles.css'

const THEME_KEY = 'ks_theme'

function useTheme() {
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem(THEME_KEY) || 'auto' } catch { return 'auto' } })
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'auto') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    try { localStorage.setItem(THEME_KEY, theme) } catch { /* ignore */ }
  }, [theme])
  return [theme, setTheme]
}

function App() {
  const [token, setToken] = useState(auth.get())
  const [theme, setTheme] = useTheme()

  useEffect(() => {
    const out = () => setToken(null)
    window.addEventListener(LOGOUT_EVENT, out)
    return () => window.removeEventListener(LOGOUT_EVENT, out)
  }, [])

  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const h = () => setHash(window.location.hash)
    window.addEventListener('hashchange', h)
    return () => window.removeEventListener('hashchange', h)
  }, [])
  if (hash.startsWith('#/feedback')) return <Feedback />          // public page for parents: no sign-in

  if (!token) return <Login onLogin={(t) => { auth.set(t); setToken(t) }} />

  const logout = () => { auth.clear(); setToken(null) }

  return (
    <HashRouter>
      <Routes>
        <Route element={<Layout theme={theme} setTheme={setTheme} onLogout={logout} />}>
          <Route index element={<Home />} />
          <Route path="episodes" element={<Episodes />} />
          <Route path="episodes/:id" element={<EpisodeDetail />} />
          <Route path="create" element={<Create />} />
          <Route path="characters" element={<Characters />} />
          <Route path="looks" element={<Looks />} />
          <Route path="library" element={<Navigate to="/library/trends" replace />} />
          <Route path="library/:tab" element={<Library />} />
          <Route path="insights" element={<Navigate to="/insights/analytics" replace />} />
          <Route path="insights/:tab" element={<Insights />} />
          <Route path="calendar" element={<Calendar />} />
          <Route path="channel" element={<Channel />} />
          <Route path="settings" element={<Settings />} />
          <Route path="activity" element={<Activity />} />
          {/* old routes → new homes */}
          <Route path="books" element={<Navigate to="/library/books" replace />} />
          <Route path="trends" element={<Navigate to="/library/trends" replace />} />
          <Route path="cast" element={<Navigate to="/characters" replace />} />
          <Route path="analytics" element={<Navigate to="/insights/analytics" replace />} />
          <Route path="growth" element={<Navigate to="/insights/growth" replace />} />
          <Route path="psychology" element={<Navigate to="/insights/playbook" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ToastProvider>
      <App />
    </ToastProvider>
  </React.StrictMode>,
)
