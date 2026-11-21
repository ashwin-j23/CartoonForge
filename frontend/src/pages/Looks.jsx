import { useState } from 'react'
import { Link } from 'react-router-dom'
import { put } from '../api'
import Icon from '../components/icons'
import { AUTO_PALETTE, AUTO_STYLE, PALETTE_GROUPS, Swatches, StyleThumb, usePalettes, useStyles } from '../components/looks'
import { Badge, Empty, Modal, PageHead, Seg, Skeleton, Spinner, useAction, useApi, useStatic, useToast } from '../components/ui'

const BAND_LABEL = { toddler: 'Toddlers', preschool: 'Preschool', early: 'Early', big: 'Big kids' }

export default function Looks() {
  const { styles, loading } = useStyles()
  const settings = useApi('/settings')
  const psych = useStatic('/psychology')
  const [band, setBand] = useState('')
  const [zoom, setZoom] = useState(null)
  const [busy, run] = useAction()
  const current = settings.data?.art_style || 'auto'
  const bands = Object.entries(psych?.bands || {})

  const setDefault = async (id) => {
    const r = await run(id, () => put('/settings', { art_style: id }), `Channel look set to ${id === 'auto' ? 'Auto' : styles?.find((s) => s.id === id)?.label || id}`)
    if (r) settings.setData(r)
  }

  const list = [AUTO_STYLE, ...(styles || [])].filter((s) => !band || s.auto || !Array.isArray(s.bands) || s.bands.includes(band))
  const cur = current === 'auto' ? AUTO_STYLE : styles?.find((s) => s.id === current)

  return (
    <div className="page">
      <PageHead title="Looks" sub="Art styles for the show. Same characters, same story — a different visual treatment. Pick a channel default here, or choose per episode when you create it." />

      <section className="look-current card">
        {cur ? <StyleThumb style={cur} className="lg" /> : <div className="style-thumb lg skel" aria-hidden="true" />}
        <div className="grow">
          <div className="eyebrow"><Icon name="check" size={13} />Channel default</div>
          <h2>{cur?.label || current}</h2>
          <p className="muted">{cur ? cur.note : '\u00a0'}</p>
          <div className="row wrap-row">
            {cur?.best_for && <Badge icon="smile">{cur.best_for}</Badge>}
            {cur?.stepped && <Badge tone="pink">Stop-motion · animated on twos</Badge>}
            <Link to="/create" className="btn sm"><Icon name="sparkles" size={15} />Create with a look</Link>
          </div>
        </div>
      </section>

      <div className="toolbar">
        <Seg value={band} onChange={setBand} size="sm" label="Filter by age band" options={[['', 'All ages'], ...bands.map(([id, b]) => [id, BAND_LABEL[id] || b.label || id])]} />
        <div className="spacer" />
        <span className="muted small">{list.length} look{list.length === 1 ? '' : 's'}</span>
      </div>

      {loading ? <div className="grid looks"><Skeleton h={457} r={22} count={6} /></div> : !styles?.length ? (
        <Empty icon="palette" title="No looks available">The art style catalogue couldn’t be loaded from the server.</Empty>
      ) : (
        <div className="grid looks">
          {list.map((s) => {
            const on = current === s.id
            return (
              <article key={s.id} className={`look-card ${on ? 'on' : ''}`}>
                <button type="button" className="look-media" onClick={() => !s.auto && setZoom(s)} aria-label={s.auto ? `${s.label} look` : `Enlarge ${s.label} sample`} disabled={s.auto}>
                  <StyleThumb style={s} />
                  {on && <span className="look-current-tag"><Icon name="check" size={13} strokeWidth={2.6} />Current</span>}
                </button>
                <div className="look-body">
                  <div className="look-title"><h3>{s.label}</h3>{s.stepped && <Badge tone="pink" size="sm">Stop-motion</Badge>}</div>
                  {s.best_for && <div className="look-ages"><Icon name="smile" size={14} />{s.best_for}</div>}
                  <p className="look-note">{s.note}</p>
                  {Array.isArray(s.bands) && <div className="chips">{s.bands.map((b) => <Badge key={b} size="sm">{BAND_LABEL[b] || b}</Badge>)}</div>}
                  {s.ai_words && (
                    <details className="look-ai">
                      <summary>AI prompt words</summary>
                      <p className="mono tiny">{s.ai_words}</p>
                    </details>
                  )}
                </div>
                <div className="look-foot">
                  {on ? <span className="muted small"><Icon name="checkCircle" size={14} /> Channel default</span> : (
                    <button className="btn sm" disabled={!!busy || !settings.data} onClick={() => setDefault(s.id)}>
                      {busy === s.id ? <Spinner size={14} /> : null}Set as default
                    </button>
                  )}
                  <Link className="btn ghost sm" to={`/create?style=${encodeURIComponent(s.id)}`}>Use for new episode</Link>
                </div>
              </article>
            )
          })}
        </div>
      )}

      <Palettes settings={settings} />

      <Modal open={!!zoom} onClose={() => setZoom(null)} title={zoom?.label} wide icon="palette"
        actions={zoom && <><span className="muted small grow">{zoom.best_for}</span>{current !== zoom.id && <button className="btn" disabled={!!busy} onClick={() => setDefault(zoom.id)}>Set as default</button>}<button className="btn primary" onClick={() => setZoom(null)}>Close</button></>}>
        {zoom && <><StyleThumb style={zoom} className="zoom" /><p className="muted" style={{ marginTop: 12 }}>{zoom.note}</p></>}
      </Modal>
    </div>
  )
}

/* -------------------------------------------------------------- colour palettes */
function Palettes({ settings }) {
  const { data, list, loading } = usePalettes()
  const [busy, run] = useAction()
  const toast = useToast()
  const current = settings.data?.palette || 'auto'
  const setDefault = async (id) => {
    const r = await run(`pal-${id}`, () => put('/settings', { palette: id }), `Colour palette set to ${id === 'auto' ? 'Auto' : list.find((p) => p.id === id)?.name || id}`)
    if (r) settings.setData(r)
  }
  const copy = (hex) => { try { navigator.clipboard.writeText(hex); toast?.(`Copied ${hex}`) } catch { /* ignore */ } }
  const cats = Object.entries(data?.by_category || {})
  return (
    <section className="pal-section" aria-labelledby="pal-h">
      <div className="section-head" style={{ marginTop: 36 }}>
        <div>
          <h2 id="pal-h">Colour palettes</h2>
          <p className="muted">One palette per episode, matched to its topic and the viewers’ age. Calm and bedtime moments switch to soft pastels,
            and colour intensity is capped by age (gentlest for toddlers). The palette colours the cards, numbers, sing-along words, chapter banners,
            name tags, logo, end card and thumbnail, and gently tints the sets.</p>
        </div>
      </div>
      <article className={`card pal-card ${current === 'auto' ? 'on' : ''}`} style={{ marginBottom: 6 }}>
        <div className="row wrap-row"><Swatches colors={AUTO_PALETTE.colors} /><b>Auto</b><span className="muted small">{AUTO_PALETTE.mood}</span>
          <div className="spacer" />{current === 'auto' ? <Badge tone="green" icon="check">Channel default</Badge>
            : <button className="btn sm" disabled={!!busy} onClick={() => setDefault('auto')}>Set as default</button>}</div>
        {cats.length > 0 && <div className="muted tiny">{cats.map(([c, p]) => `${c.replace('_', ' ')} → ${list.find((x) => x.id === p)?.name || p}`).join(' · ')}</div>}
      </article>
      {loading ? <Skeleton h={140} r={14} count={3} /> : !list.length ? (
        <Empty compact icon="palette" title="No palettes">The palette list couldn’t be loaded — restart the server to pick up the update.</Empty>
      ) : PALETTE_GROUPS.map(([g, label]) => {
        const items = list.filter((p) => p.group === g)
        if (!items.length) return null
        return (
          <div key={g}>
            <h3 className="pal-group-title">{label}</h3>
            <div className="pal-grid">
              {items.map((p) => (
                <article key={p.id} className={`card pal-card ${current === p.id ? 'on' : ''}`}>
                  <Swatches colors={p.colors} size="lg" />
                  <div><b>{p.name}</b><div className="muted small">{p.mood}</div></div>
                  <div className="pal-hexes">{p.colors.map((c, i) => <button key={`${c}-${i}`} type="button" onClick={() => copy(c)} title="Copy">{c}</button>)}</div>
                  {p.for?.length > 0 && <div className="chips">{p.for.map((c) => <Badge key={c} size="sm">{c.replace('_', ' ')}</Badge>)}</div>}
                  <div className="row">
                    {current === p.id ? <Badge tone="green" icon="check">Channel default</Badge>
                      : <button className="btn sm" disabled={!!busy} onClick={() => setDefault(p.id)}>{busy === `pal-${p.id}` ? <Spinner size={14} /> : null}Use for every episode</button>}
                  </div>
                </article>
              ))}
            </div>
          </div>
        )
      })}
      {data?.sources && (
        <p className="muted pal-sources" style={{ marginTop: 16 }}>Sources: {data.sources.map((s, i) => <span key={s.url}>{i ? ' · ' : ''}<a href={s.url} target="_blank" rel="noreferrer">{s.name}</a></span>)}</p>
      )}
    </section>
  )
}
