import { Bar, Empty, fmtScore, scoreScale } from './ui'

const nice = (s) => String(s).replace(/[_-]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

function Ring({ value, max, bar }) {
  const r = 52
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(1, (value || 0) / max))
  const barPct = bar != null ? Math.max(0, Math.min(1, bar / max)) : null
  const pass = bar == null || value >= bar
  const a = barPct != null ? barPct * 2 * Math.PI - Math.PI / 2 : 0
  return (
    <svg viewBox="0 0 128 128" className="ring" role="img" aria-label={`Score ${fmtScore(value)} of ${max}`}>
      <circle cx="64" cy="64" r={r} className="ring-bg" />
      <circle cx="64" cy="64" r={r} className={`ring-fg ${pass ? 'pass' : 'fail'}`} strokeDasharray={`${pct * c} ${c}`} transform="rotate(-90 64 64)" />
      {barPct != null && (
        <line x1={64 + Math.cos(a) * (r - 11)} y1={64 + Math.sin(a) * (r - 11)} x2={64 + Math.cos(a) * (r + 11)} y2={64 + Math.sin(a) * (r + 11)} className="ring-bar" />
      )}
      <text x="64" y="62" textAnchor="middle" className="ring-num">{fmtScore(value)}</text>
      <text x="64" y="82" textAnchor="middle" className="ring-sub">of {max}</text>
    </svg>
  )
}

const METRICS = [
  ['words', '📝', 'Words', (v) => v?.toLocaleString()],
  ['est_minutes', '⏱️', 'Est. minutes', (v) => (v != null ? Number(v).toFixed(1) : '—')],
  ['avg_sentence', '📏', 'Avg sentence (words)', (v) => (v != null ? Number(v).toFixed(1) : '—'), 'sentence', (v, t) => v <= t],
  ['questions', '❓', 'Questions to kids', (v) => v],
  ['interactions', '🙌', 'Interactions', (v) => v],
  ['interact_per_min', '⚡', 'Interactions / min', (v) => (v != null ? Number(v).toFixed(2) : '—'), 'interact_per_min', (v, t) => v >= t],
  ['fk_grade', '🎓', 'Reading grade (FK)', (v) => (v != null ? Number(v).toFixed(1) : '—')],
]

export default function Scorecard({ critic, bar, band }) {
  if (!critic) return <Empty emoji="🧑‍🏫" title="Not scored yet">The child-psychology critic scores the script after the writer finishes.</Empty>
  const max = scoreScale(critic.score, bar, critic.code_score, critic.model_score)
  const m = critic.metrics || {}
  const rubric = Object.entries(critic.rubric || {})
  const issues = m.issues || []
  const kw = Object.entries(m.key_word_counts || {})

  return (
    <div className="scorecard">
      <div className="score-hero">
        <Ring value={critic.score} max={max} bar={bar} />
        <div className="score-text">
          <h3>{bar == null ? 'Critic score' : critic.score >= bar ? '🎉 Clears the quality bar' : '🛠️ Below the quality bar'}</h3>
          {bar != null && <p className="muted">Quality bar is <b>{fmtScore(bar)}</b> — episodes below it are rewritten (up to the max revisions) before reaching review.</p>}
          <div className="sub-scores">
            {critic.code_score != null && <span className="badge t-neutral sm">🧮 Rule checks <b>{fmtScore(critic.code_score)}</b></span>}
            {critic.model_score != null && <span className="badge t-neutral sm">🤖 Model judge <b>{fmtScore(critic.model_score)}</b></span>}
          </div>
          {critic.summary && <p className="critic-summary">“{critic.summary}”</p>}
        </div>
      </div>

      {rubric.length > 0 && (
        <div className="block">
          <h4>Rubric</h4>
          <div className="rubric">
            {rubric.map(([k, v]) => (
              <div className="rubric-row" key={k}>
                <span className="rubric-name">{nice(k)}</span>
                <Bar value={v} max={10} tone={v >= 8 ? 'green' : v >= 6 ? 'amber' : 'red'} />
                <b className="rubric-v">{fmtScore(v)}</b>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="block">
        <h4>Script metrics {band?.label ? <small className="muted">vs. {band.label} targets</small> : null}</h4>
        <div className="metrics">
          {METRICS.filter(([k]) => m[k] != null).map(([k, emoji, label, fmt, tk, okFn]) => {
            const target = tk && band ? band[tk] : null
            const ok = target != null && okFn ? okFn(Number(m[k]), Number(target)) : null
            return (
              <div className={`metric ${ok === true ? 'ok' : ok === false ? 'bad' : ''}`} key={k}>
                <span className="metric-emoji">{emoji}</span>
                <b>{fmt(m[k])}</b>
                <span className="muted tiny">{label}</span>
                {target != null && <span className="tiny">{ok ? '✅' : '⚠️'} target {tk === 'sentence' ? '≤' : '≥'} {target}</span>}
              </div>
            )
          })}
        </div>
      </div>

      {kw.length > 0 && (
        <div className="block">
          <h4>Key-word repetition {band?.repeat_key ? <small className="muted">(aim for ≥ {band.repeat_key} each)</small> : null}</h4>
          <div className="chips">
            {kw.map(([w, n]) => (
              <span key={w} className={`badge sm ${band?.repeat_key && n < band.repeat_key ? 't-red' : 't-green'}`}>🔑 {w} × {n}</span>
            ))}
          </div>
        </div>
      )}

      <div className="block">
        <h4>Notes from the critic</h4>
        {issues.length === 0 ? <div className="banner ok"><span className="banner-ico">🌈</span>No issues flagged — lovely work.</div> : (
          <ul className="issues">
            {issues.map((s, i) => <li key={i}><span aria-hidden="true">{/too|long|fast|hard|complex|grade/i.test(s) ? '🐢' : /question|interact|engage/i.test(s) ? '🙋' : /repeat|key/i.test(s) ? '🔁' : '💭'}</span>{s}</li>)}
          </ul>
        )}
      </div>
    </div>
  )
}
