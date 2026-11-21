import { CircleStop, Pause, Play, RotateCcw, SkipForward } from 'lucide-react'
import { SPEEDS, type Simulation } from '../../hooks/useSimulation'

interface Props {
  sim: Simulation
}

/** Play / pause / step / reset, speed and "end incident". */
export function PlaybackBar({ sim }: Props) {
  const s = sim.sim
  if (!s) return null
  const running = s.state === 'running'
  const done = s.state === 'completed'
  return (
    <div className="overlay playback" role="toolbar" aria-label="Simulation controls">
      {running ? (
        <button className="btn btn-primary" onClick={sim.pause} aria-label="Pause"><Pause size={15} /> <span className="btn-label">Pause</span></button>
      ) : (
        <button className="btn btn-primary" onClick={sim.play} disabled={done} aria-label={s.tick === 0 ? 'Start fire' : 'Resume'}>
          <Play size={15} /> <span className="btn-label">{s.tick === 0 ? 'Start fire' : 'Resume'}</span>
        </button>
      )}
      <button className="icon-btn" onClick={sim.step} disabled={running || done} title="Advance one minute" aria-label="Step one minute">
        <SkipForward size={16} />
      </button>
      <button className="icon-btn" onClick={sim.reset} title="Back to the start of this incident" aria-label="Reset">
        <RotateCcw size={16} />
      </button>
      <div className="segmented speed" role="group" aria-label="Speed">
        {SPEEDS.map((v) => (
          <button key={v} className={sim.speed === v ? 'on' : ''} onClick={() => sim.setSpeed(v)} title={`${v} simulated minute${v === 1 ? '' : 's'} per second`}>
            {v}×
          </button>
        ))}
      </div>
      {s.map_type === 'city' && (
        <button className="btn btn-ghost" onClick={sim.end} disabled={done || s.tick === 0} title="Close the incident now and record it in the history" aria-label="End incident">
          <CircleStop size={15} /> <span className="btn-label">End incident</span>
        </button>
      )}
    </div>
  )
}
