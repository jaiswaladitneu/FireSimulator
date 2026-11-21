import { Bot, Truck } from 'lucide-react'
import type { CityState, MapData } from '../../api/types'

interface Props {
  city: CityState | null
  map: MapData | null
  disabled: boolean
  onToggleAuto: (on: boolean) => void
  onFocus: (id: number) => void
}

const STATUS_TEXT = { available: 'Available', en_route: 'En route', working: 'On scene' } as const

/** Fire crews: where each one is and what it is doing. */
export function CrewPanel({ city, map, disabled, onToggleAuto, onFocus }: Props) {
  const crews = city?.crews ?? []
  const auto = city?.auto_dispatch ?? false
  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2><Truck size={15} /> Fire crews</h2>
          <p className="panel-sub">{city ? `${city.crews_available} of ${crews.length} available · ${city.dispatches} dispatches` : 'No incident'}</p>
        </div>
        <label className="toggle-inline" title="Crews automatically take the highest-priority uncovered target">
          <Bot size={14} />
          <span>Auto</span>
          <button className={`switch ${auto ? 'on' : ''}`} disabled={disabled || !city} onClick={() => onToggleAuto(!auto)} aria-pressed={auto} aria-label="Automatic dispatch">
            <i />
          </button>
        </label>
      </header>
      {crews.length === 0 ? (
        <p className="muted small">{city ? 'This incident has no crews.' : 'Crews appear when a town is generated.'}</p>
      ) : (
        <ul className="crew-list">
          {crews.map((c) => {
            const target = c.target != null ? map?.assets[c.target] : undefined
            return (
              <li key={c.id} className={`crew crew-${c.status}`}>
                <span className="crew-dot" />
                <span className="crew-name">{c.name}</span>
                <span className="crew-status">{STATUS_TEXT[c.status]}</span>
                {target ? (
                  <button className="link crew-target" onClick={() => onFocus(target.id)} title={target.name}>
                    {target.name}
                  </button>
                ) : (
                  <span className="crew-target muted">At station</span>
                )}
                <span className="crew-meta mono">
                  {c.status === 'en_route' ? `ETA ${c.eta} min` : c.status === 'working' ? `${c.work_left} min left` : `${c.cells_suppressed} cells`}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
