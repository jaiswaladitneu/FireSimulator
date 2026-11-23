import { Play, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { AssetKind, IncidentFull } from '../../api/types'
import { fmt, fmtDate, fmtHa, fmtHour, fmtMinutes } from '../../lib/format'
import { KIND_META, KIND_ORDER, STATUS_LABEL, compassName, severityClass } from '../../lib/kinds'
import { ChartCard, Legend, LineChart } from './charts'
import { SERIES } from './chartUtils'

const OUTCOME = { extinguished: 'Fire out', stopped: 'Closed early', time_limit: 'Stopped at time limit' } as const

/** Side drawer with one incident's full record (render with key={id} so it resets per incident). */
export function IncidentDetail({ id, onClose, onReplay, onDelete }: {
  id: string
  onClose: () => void
  onReplay: (rec: IncidentFull) => void
  onDelete: (id: string) => void
}) {
  const [rec, setRec] = useState<IncidentFull | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    api.incident(id).then(
      (r) => alive && setRec(r),
      (e: Error) => alive && setError(e.message),
    )
    return () => {
      alive = false
    }
  }, [id])

  const s = rec?.summary
  const tl = s?.timeline ?? []
  const x = tl.map((p) => p.t)
  const kinds = KIND_ORDER.filter((k) => s?.by_kind[k as AssetKind]?.total)

  return (
    <aside className="drawer" aria-label="Incident details">
      <header className="drawer-head">
        <div>
          <h2>{rec?.name ?? 'Loading…'}</h2>
          {rec && (
            <p className="muted small">
              {fmtDate(rec.ended_at)} · {rec.source === 'live' ? 'Command center' : 'Simulated'} · {OUTCOME[rec.outcome]} after {fmtMinutes(rec.ticks)}
            </p>
          )}
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close details"><X size={16} /></button>
      </header>
      {error && <p className="danger-text">{error}</p>}
      {rec && s && (
        <div className="drawer-body">
          <div className="tiles">
            <div className="tile"><span>Peak lives at risk</span><strong>{fmt(s.population.peak_at_risk)}</strong></div>
            <div className="tile"><span>Evacuated</span><strong>{fmt(s.population.evacuated)}</strong></div>
            <div className="tile"><span>Casualties (est.)</span><strong className={s.population.casualties ? 'danger-text' : ''}>{fmt(s.population.casualties)}</strong></div>
            <div className="tile"><span>Buildings destroyed</span><strong>{fmt(s.buildings.destroyed)}</strong></div>
            <div className="tile"><span>Area burned</span><strong>{fmtHa(s.area_burned_ha)}</strong></div>
            <div className="tile"><span>Crew dispatches</span><strong>{fmt(s.dispatches)}</strong></div>
          </div>

          <p className="conditions">
            Wind {Math.round(rec.params.wind_speed)} km/h toward {compassName(rec.params.wind_direction)} · started {fmtHour(rec.params.hour)} ·{' '}
            {rec.params.crews} crews ({rec.params.auto_dispatch ? 'automatic dispatch' : 'manual dispatch'}) · {rec.params.width} × {rec.params.height} town, layout {rec.params.seed} · population {fmt(s.population.total)}
          </p>

          <ChartCard
            title="People over time"
            subtitle="At risk, evacuated (cumulative) and casualties (cumulative, estimated)"
            legend={<Legend items={[
              { label: 'At risk', color: SERIES.blue, shape: 'line' },
              { label: 'Evacuated', color: SERIES.aqua, shape: 'line' },
              { label: 'Casualties (est.)', color: SERIES.orange, shape: 'line' },
            ]} />}
            table={{ columns: ['Minute', 'At risk', 'Evacuated', 'Casualties'], rows: tl.map((p) => [p.t, p.at_risk, p.evacuated, p.casualties]) }}
          >
            <LineChart x={x} series={[
              { key: 'risk', label: 'At risk', color: SERIES.blue, values: tl.map((p) => p.at_risk), area: true },
              { key: 'evac', label: 'Evacuated', color: SERIES.aqua, values: tl.map((p) => p.evacuated) },
              { key: 'cas', label: 'Casualties (est.)', color: SERIES.orange, values: tl.map((p) => p.casualties) },
            ]} />
          </ChartCard>

          <ChartCard
            title="Buildings over time"
            subtitle="Buildings on fire at each minute, and destroyed so far"
            legend={<Legend items={[
              { label: 'On fire', color: SERIES.orange, shape: 'line' },
              { label: 'Destroyed', color: SERIES.muted, shape: 'line' },
            ]} />}
            table={{ columns: ['Minute', 'On fire', 'Destroyed'], rows: tl.map((p) => [p.t, p.bld_burning, p.bld_destroyed]) }}
          >
            <LineChart height={160} x={x} series={[
              { key: 'burning', label: 'On fire', color: SERIES.orange, values: tl.map((p) => p.bld_burning) },
              { key: 'destroyed', label: 'Destroyed', color: SERIES.muted, values: tl.map((p) => p.bld_destroyed) },
            ]} />
          </ChartCard>

          <section className="viz-card">
            <header className="viz-head"><div><h3>Losses by type of place</h3></div></header>
            <table className="viz-table">
              <thead>
                <tr><th>Place</th><th className="num">Total</th><th className="num">Destroyed</th><th className="num">Damaged</th><th className="num">Evacuated</th><th className="num">Casualties</th></tr>
              </thead>
              <tbody>
                {kinds.map((k) => {
                  const v = s.by_kind[k as AssetKind]!
                  return (
                    <tr key={k}>
                      <td>{KIND_META[k].plural}</td>
                      <td className="num">{fmt(v.total)}</td>
                      <td className="num">{fmt(v.destroyed)}</td>
                      <td className="num">{fmt(v.damaged)}</td>
                      <td className="num">{fmt(v.evacuated)}</td>
                      <td className={`num ${v.casualties ? 'danger-text' : ''}`}>{fmt(v.casualties)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          {s.top_losses.length > 0 && (
            <section className="viz-card">
              <header className="viz-head"><div><h3>Worst-hit places</h3></div></header>
              <ul className="loss-list">
                {s.top_losses.map((l, i) => {
                  const Icon = KIND_META[l.kind].icon
                  return (
                    <li key={i}>
                      <Icon size={14} />
                      <span className="grow">{l.name}</span>
                      <span className="muted">{STATUS_LABEL[l.status]}</span>
                      <strong className={l.casualties ? 'danger-text' : ''}>{fmt(l.casualties)} casualties</strong>
                    </li>
                  )
                })}
              </ul>
            </section>
          )}

          <section className="viz-card">
            <header className="viz-head"><div><h3>Key events</h3><p>Critical events in order</p></div></header>
            {s.key_events.length === 0 ? (
              <p className="muted small">No critical events: no casualties, no destroyed facilities, no hazardous-site fires.</p>
            ) : (
              <ul className="feed compact">
                {s.key_events.map((e, i) => (
                  <li key={i} className={`feed-item ${severityClass(e.severity)} ${e.type === 'explosion' ? 'boom' : ''}`}>
                    <span className="feed-time mono">{e.clock}</span>
                    <span className="feed-msg">{e.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <div className="row gap drawer-actions">
            <button className="btn btn-primary" onClick={() => onReplay(rec)}><Play size={14} /> Replay in command center</button>
            <button className="btn btn-ghost danger" onClick={() => onDelete(rec.id)}><Trash2 size={14} /> Delete</button>
          </div>
        </div>
      )}
    </aside>
  )
}
