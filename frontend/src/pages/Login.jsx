import { useState } from 'react'
import { api } from '../api'
import Icon from '../components/icons'
import Sun from '../components/Sun'
import { SafeImg, Spinner } from '../components/ui'

export default function Login({ onLogin }) {
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (!pw) return
    setBusy(true); setErr('')
    try {
      const r = await api('/login', { method: 'POST', body: { password: pw } })
      if (!r?.token) throw new Error('No token returned')
      onLogin(r.token)
    } catch (e2) {
      setErr(e2.status === 401 || e2.status === 403 ? 'That password didn’t work. Try again?' : e2.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <div className="login-art" aria-hidden="true">
        <div className="login-art-inner">
          <Sun size={64} className="spin-slow" />
          <h2>Songs, stories and smiles — made by a studio that never sleeps.</h2>
          <div className="login-cast">
            {['sunny', 'hoppy', 'pip', 'mimi', 'bo'].map((id, i) => (
              <SafeImg key={id} src={`/api/cast/${id}.png?emotion=${i % 2 ? 'excited' : 'happy'}&arms=${i === 0 ? 'wave' : 'down'}&size=220`} className={`lc lc${i}`} />
            ))}
          </div>
        </div>
      </div>
      <div className="login-side">
        <form className="login-card" onSubmit={submit}>
          <div className="brand"><Sun size={36} /><span className="brand-text"><b>CartoonForge</b><small>Studio control room</small></span></div>
          <h1>Welcome back</h1>
          <p className="muted">Sign in to plan, review and publish episodes.</p>
          <label className="field">
            <span className="field-label"><span>Studio password</span></span>
            <input type="password" autoFocus autoComplete="current-password" value={pw}
              onChange={(e) => setPw(e.target.value)} placeholder="Enter the studio password" aria-invalid={!!err} />
          </label>
          {err && <div className="form-error" role="alert"><Icon name="alertCircle" size={16} />{err}</div>}
          <button className="btn primary block lg" disabled={busy || !pw}>{busy ? <Spinner /> : null}{busy ? 'Opening…' : 'Open the studio'}</button>
          <p className="tiny muted">Owner access only. Episodes are made for kids; this dashboard is not.</p>
        </form>
      </div>
    </div>
  )
}
