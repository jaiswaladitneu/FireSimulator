import { ChevronDown, ChevronUp, Crosshair, Dices, Flame, Moon, Sun, Truck } from 'lucide-react'
import { useState } from 'react'
import type { Simulation } from '../../hooks/useSimulation'
import { fmtHour } from '../../lib/format'
import { COMPASS, compassName } from '../../lib/kinds'

interface Props {
  sim: Simulation
  igniteMode: boolean
  onIgniteMode: (on: boolean) => void
}

const SIZES = [
  { label: 'Small', value: 64 },
  { label: 'Medium', value: 96 },
  { label: 'Large', value: 128 },
]

// Compass rose positions in a 3 x 3 grid (centre cell shows the arrow).
const ROSE: (number | null)[] = [315, 0, 45, 270, null, 90, 225, 180, 135]

function hourHint(h: number) {
  if (h >= 8 && h <= 14) return 'School in session · homes mostly empty'
  if (h >= 23 || h <= 5) return 'Night · residents asleep, slower evacuation'
  if ((h >= 7 && h <= 9) || (h >= 16 && h <= 18)) return 'Rush hour · busy roads'
  return 'Evening · most people at home'
}

/** Incident setup: town, wind, time of day and response resources. */
export function ScenarioPanel({ sim, igniteMode, onIgniteMode }: Props) {
  const hasScenario = !!sim.sim
  const [open, setOpen] = useState(!hasScenario)
  const [name, setName] = useState('Ridgeview wildfire')
  const [size, setSize] = useState(96)
  const [seed, setSeed] = useState(4)
  const [windDir, setWindDir] = useState(90)
  const [windSpeed, setWindSpeed] = useState(25)
  const [hour, setHour] = useState(14)
  const [crews, setCrews] = useState(4)
  const [auto, setAuto] = useState(false)

  const expanded = open || !hasScenario
  const idle = sim.sim?.state === 'idle' && sim.sim.tick === 0

  const submit = async () => {
    const ok = await sim.create({
      name: name.trim() || 'Untitled incident',
      width: size,
      height: size,
      seed,
      wind_direction: windDir,
      wind_speed: windSpeed,
      map_type: 'city',
      hour,
      crews,
      auto_dispatch: auto,
    })
    if (ok) setOpen(false)
  }

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2><Flame size={15} /> Incident setup</h2>
          {!expanded && sim.sim && <p className="panel-sub">{sim.sim.scenario.name}</p>}
        </div>
        {hasScenario && (
          <button className="icon-btn" onClick={() => setOpen(!open)} aria-label={expanded ? 'Collapse setup' : 'Expand setup'}>
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        )}
      </header>

      {!expanded && sim.sim && (
        <div className="setup-summary">
          {idle ? (
            <>
              <p className="hint">Town ready. Fire starts upwind of town by default. Add more ignition points by clicking the map.</p>
              <button className={`btn ${igniteMode ? 'btn-fire' : 'btn-ghost'} btn-block`} onClick={() => onIgniteMode(!igniteMode)}>
                <Crosshair size={15} /> {igniteMode ? 'Click the map to ignite… (done)' : 'Add ignition point'}
              </button>
            </>
          ) : (
            <p className="hint">Incident in progress. Use “New incident” to start over with a different town or weather.</p>
          )}
          <button className="btn btn-ghost btn-block" onClick={() => setOpen(true)}>New incident…</button>
        </div>
      )}

      {expanded && (
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <label className="field">
            <span>Incident name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
          </label>

          <div className="field">
            <span>Town size</span>
            <div className="segmented">
              {SIZES.map((s) => (
                <button type="button" key={s.value} className={size === s.value ? 'on' : ''} onClick={() => setSize(s.value)}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <label className="field">
            <span>Town layout (seed)</span>
            <div className="row">
              <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value) || 0)} />
              <button type="button" className="icon-btn" title="Random layout" aria-label="Random layout" onClick={() => setSeed(Math.floor(Math.random() * 100000))}>
                <Dices size={16} />
              </button>
            </div>
          </label>

          <div className="field">
            <span>Wind blows toward · {compassName(windDir)} (from {compassName(windDir + 180)})</span>
            <div className="wind-picker">
              <div className="rose">
                {ROSE.map((deg, i) =>
                  deg === null ? (
                    <div key={i} className="rose-center">
                      <div className="rose-arrow" style={{ transform: `rotate(${windDir}deg)` }}>➤</div>
                    </div>
                  ) : (
                    <button type="button" key={i} className={windDir === deg ? 'on' : ''} onClick={() => setWindDir(deg)} aria-label={`Toward ${COMPASS[deg / 45]}`}>
                      {COMPASS[deg / 45]}
                    </button>
                  ),
                )}
              </div>
              <div className="wind-speed">
                <strong className="mono">{windSpeed}</strong>
                <small>km/h</small>
                <input type="range" min={0} max={50} value={windSpeed} onChange={(e) => setWindSpeed(Number(e.target.value))} aria-label="Wind speed" />
                <small className="muted">{windSpeed < 10 ? 'light' : windSpeed < 25 ? 'moderate' : windSpeed < 38 ? 'strong' : 'extreme'}</small>
              </div>
            </div>
          </div>

          <label className="field">
            <span>
              Start time · {fmtHour(hour)} {hour >= 7 && hour < 19 ? <Sun size={12} /> : <Moon size={12} />}
            </span>
            <input type="range" min={0} max={23} value={hour} onChange={(e) => setHour(Number(e.target.value))} />
            <small className="muted">{hourHint(hour)}</small>
          </label>

          <div className="field two">
            <label>
              <span><Truck size={12} /> Fire crews</span>
              <input type="number" min={0} max={12} value={crews} onChange={(e) => setCrews(Math.max(0, Math.min(12, Number(e.target.value) || 0)))} />
            </label>
            <label className="toggle-field">
              <span>Auto-dispatch</span>
              <button type="button" className={`switch ${auto ? 'on' : ''}`} onClick={() => setAuto(!auto)} aria-pressed={auto} aria-label="Automatic dispatch">
                <i />
              </button>
            </label>
          </div>

          <button className="btn btn-primary btn-block" type="submit" disabled={sim.busy || sim.online === false}>
            {sim.busy ? 'Generating town…' : hasScenario ? 'Generate new town' : 'Generate town'}
          </button>
          {sim.online === false && <p className="hint danger-text">API offline — start it with <code>uvicorn api.main:app</code>.</p>}
        </form>
      )}
    </section>
  )
}
