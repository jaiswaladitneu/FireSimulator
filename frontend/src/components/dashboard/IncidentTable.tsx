import { ArrowDown, ArrowUp, Bot, Hand } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { IncidentBrief } from '../../api/types'
import { fmt, fmtDate, fmtHa, fmtHour, fmtMinutes } from '../../lib/format'
import { compassName } from '../../lib/kinds'

type SortKey = 'date' | 'name' | 'minutes' | 'risk' | 'evacuated' | 'casualties' | 'destroyed' | 'area'

const COLS: { key: SortKey; label: string; num?: boolean; get: (r: IncidentBrief) => number | string }[] = [
  { key: 'date', label: 'Ended', get: (r) => r.ended_at },
  { key: 'name', label: 'Incident', get: (r) => r.name.toLowerCase() },
  { key: 'minutes', label: 'Duration', num: true, get: (r) => r.ticks },
  { key: 'risk', label: 'Peak at risk', num: true, get: (r) => r.summary.population.peak_at_risk },
  { key: 'evacuated', label: 'Evacuated', num: true, get: (r) => r.summary.population.evacuated },
  { key: 'casualties', label: 'Casualties (est.)', num: true, get: (r) => r.summary.population.casualties },
  { key: 'destroyed', label: 'Buildings lost', num: true, get: (r) => r.summary.buildings.destroyed },
  { key: 'area', label: 'Area', num: true, get: (r) => r.summary.area_burned_ha },
]

const OUTCOME = { extinguished: 'Fire out', stopped: 'Closed early', time_limit: 'Time limit' } as const

/** Every recorded incident, sortable; click a row for details. */
export function IncidentTable({ list, selectedId, onSelect }: {
  list: IncidentBrief[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'date', desc: true })
  const rows = useMemo(() => {
    const col = COLS.find((c) => c.key === sort.key)!
    return [...list].sort((a, b) => {
      const va = col.get(a)
      const vb = col.get(b)
      const c = va < vb ? -1 : va > vb ? 1 : 0
      return sort.desc ? -c : c
    })
  }, [list, sort])

  return (
    <section className="viz-card table-card">
      <header className="viz-head">
        <div>
          <h3>Incident history</h3>
          <p>{list.length} incidents · click a row for its timeline, losses and key events</p>
        </div>
      </header>
      <div className="table-scroll">
        <table className="incident-table">
          <thead>
            <tr>
              {COLS.map((c) => (
                <th key={c.key} className={c.num ? 'num' : ''} aria-sort={sort.key === c.key ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
                  <button onClick={() => setSort((s) => ({ key: c.key, desc: s.key === c.key ? !s.desc : c.key !== 'name' }))}>
                    {c.label}
                    {sort.key === c.key && (sort.desc ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}
                  </button>
                </th>
              ))}
              <th>Conditions</th>
              <th>Response</th>
              <th>Outcome</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={r.id === selectedId ? 'sel' : ''} onClick={() => onSelect(r.id)} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && onSelect(r.id)}>
                <td className="nowrap muted">{fmtDate(r.ended_at)}</td>
                <td className="name-cell">
                  <span>{r.name}</span>
                  <small className={`src src-${r.source}`}>{r.source === 'live' ? 'Command center' : 'Simulated'}</small>
                </td>
                <td className="num">{fmtMinutes(r.ticks)}</td>
                <td className="num">{fmt(r.summary.population.peak_at_risk)}</td>
                <td className="num">{fmt(r.summary.population.evacuated)}</td>
                <td className={`num ${r.summary.population.casualties > 0 ? 'danger-text' : ''}`}>{fmt(r.summary.population.casualties)}</td>
                <td className="num">{fmt(r.summary.buildings.destroyed)}</td>
                <td className="num">{fmtHa(r.summary.area_burned_ha)}</td>
                <td className="nowrap muted">{Math.round(r.params.wind_speed)} km/h to {compassName(r.params.wind_direction)} · {fmtHour(r.params.hour)}</td>
                <td className="nowrap">
                  {r.params.auto_dispatch ? <span className="chip ghost"><Bot size={11} /> Auto</span> : <span className="chip ghost"><Hand size={11} /> Manual</span>}
                  <span className="muted"> {r.params.crews} crews</span>
                </td>
                <td className="nowrap">{OUTCOME[r.outcome]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
