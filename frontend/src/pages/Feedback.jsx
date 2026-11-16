import { useEffect, useState } from 'react'

/** Public page for grown-ups: feedback on an episode (YouTube disables comments on made-for-kids videos).
 *  Reached from the link in every video description: /#/feedback?v=<episode id>. No sign-in, nothing personal. */

const ENJOY = [['loved', '😍', 'Loved it'], ['ok', '🙂', 'It was OK'], ['not_really', '😕', 'Not really']]
const RATE = [['style', 'Look & design', 'Colours, characters, backgrounds'], ['animation', 'Animation', 'Movement, expressions, pace'],
  ['voices', 'Songs & voices', 'Music, singing, how the friends talk'], ['learning', 'Learning', 'Did your child learn something?']]
const AGES = [['toddler', '1–3'], ['preschool', '3–5'], ['early', '5–8'], ['big', '8–12']]
const ROLES = [['parent', 'Parent / family'], ['teacher', 'Teacher / carer'], ['other', 'Other']]

function param(name) {
  const q = window.location.hash.split('?')[1] || ''
  return new URLSearchParams(q).get(name) || ''
}

async function call(path, body) {
  const res = await fetch(`/api${path}`, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Something went wrong, please try again.')
  return data
}

function Stars({ value, onChange, label }) {
  return (
    <div className="fb-stars" role="radiogroup" aria-label={label}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button type="button" key={n} role="radio" aria-checked={value === n} aria-label={`${n} star${n > 1 ? 's' : ''}`}
          className={n <= (value || 0) ? 'on' : ''} onClick={() => onChange(value === n ? null : n)}>★</button>
      ))}
    </div>
  )
}

export default function Feedback() {
  const v = param('v')
  const [ep, setEp] = useState(null)
  const [f, setF] = useState({ enjoyed: null, style: null, animation: null, voices: null, learning: null, change: '', request: '', age_band: null, role: null, website: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [done, setDone] = useState(false)
  const set = (k, val) => setF((x) => ({ ...x, [k]: val }))

  useEffect(() => { document.title = 'Hoppy Hop Hop · Feedback' }, [])
  useEffect(() => { if (v) call(`/public/episode/${encodeURIComponent(v)}`).then(setEp, () => setEp(null)) }, [v])

  const send = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      await call('/public/feedback', { ...f, episode_id: v || null })
      setDone(true); window.scrollTo(0, 0)
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }

  return (
    <div className="fb-page">
      <header className="fb-head">
        <img src="/hoppy-logo.png" alt="Hoppy Hop Hop" className="fb-logo" />
      </header>
      <main className="fb-card">
        {done ? (
          <div className="fb-done">
            <img src="/hoppy-avatar.png" alt="" width="96" height="96" />
            <h1>Thank you! 💚</h1>
            <p>Hoppy and friends read every answer. Your ideas shape the next episodes.</p>
            {ep?.youtube_url && <a className="btn primary" href={ep.youtube_url}>Back to the video</a>}
          </div>
        ) : (
          <form onSubmit={send}>
            <h1>How was this episode?</h1>
            <p className="fb-sub">For grown-ups · takes 1 minute · every question is optional</p>
            {ep && (
              <div className="fb-ep">
                {ep.thumb_url && <img src={ep.thumb_url} alt="" />}
                <b>{ep.title}</b>
              </div>
            )}

            <fieldset>
              <legend>Did your child enjoy it?</legend>
              <div className="fb-enjoy">
                {ENJOY.map(([id, emoji, label]) => (
                  <button type="button" key={id} className={f.enjoyed === id ? 'on' : ''} aria-pressed={f.enjoyed === id}
                    onClick={() => set('enjoyed', f.enjoyed === id ? null : id)}>
                    <span aria-hidden="true">{emoji}</span>{label}
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend>Rate what you saw</legend>
              {RATE.map(([k, label, hint]) => (
                <div className="fb-rate" key={k}>
                  <div><b>{label}</b><small>{hint}</small></div>
                  <Stars value={f[k]} onChange={(n) => set(k, n)} label={label} />
                </div>
              ))}
            </fieldset>

            <fieldset>
              <legend>What would you change?</legend>
              <textarea rows={3} maxLength={600} value={f.change} onChange={(e) => set('change', e.target.value)}
                placeholder="Slower songs, more counting, a different voice, longer stories…" />
            </fieldset>

            <fieldset>
              <legend>What should Hoppy learn next?</legend>
              <input maxLength={160} value={f.request} onChange={(e) => set('request', e.target.value)}
                placeholder="e.g. dinosaurs, brushing teeth, shapes, the planets" />
            </fieldset>

            <fieldset>
              <legend>Your child's age</legend>
              <div className="fb-chips">
                {AGES.map(([id, label]) => (
                  <button type="button" key={id} className={f.age_band === id ? 'on' : ''} aria-pressed={f.age_band === id}
                    onClick={() => set('age_band', f.age_band === id ? null : id)}>{label}</button>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend>I am a…</legend>
              <div className="fb-chips">
                {ROLES.map(([id, label]) => (
                  <button type="button" key={id} className={f.role === id ? 'on' : ''} aria-pressed={f.role === id}
                    onClick={() => set('role', f.role === id ? null : id)}>{label}</button>
                ))}
              </div>
            </fieldset>

            <input className="fb-hp" tabIndex={-1} autoComplete="off" aria-hidden="true" value={f.website}
              onChange={(e) => set('website', e.target.value)} name="website" />
            <p className="fb-privacy">Please don't include your child's name or any personal details. We don't ask for an email and we never share answers.</p>
            {err && <p className="fb-err" role="alert">{err}</p>}
            <button className="btn primary block fb-send" disabled={busy}>{busy ? 'Sending…' : 'Send feedback'}</button>
          </form>
        )}
      </main>
    </div>
  )
}
