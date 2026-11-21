import { Flame, LayoutDashboard, Radar } from 'lucide-react'
import type { SimPayload } from '../api/types'
import type { Route } from '../lib/useHashRoute'

interface Props {
  route: Route
  go: (r: Route) => void
  online: boolean | null
  sim: SimPayload | null
}

export function TopBar({ route, go, online, sim }: Props) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark"><Flame size={18} /></span>
        <div>
          <strong>FireSim</strong>
          <span>Incident Command</span>
        </div>
      </div>
      <nav className="tabs" aria-label="Views">
        <button className={route === 'command' ? 'on' : ''} onClick={() => go('command')} aria-current={route === 'command' ? 'page' : undefined}>
          <Radar size={15} /> Command Center
        </button>
        <button className={route === 'dashboard' ? 'on' : ''} onClick={() => go('dashboard')} aria-current={route === 'dashboard' ? 'page' : undefined}>
          <LayoutDashboard size={15} /> Admin Dashboard
        </button>
      </nav>
      <div className="topbar-right">
        {sim && (
          <span className="incident-name" title={sim.scenario.name}>
            <span className={`pill pill-${sim.state}`}>{sim.state}</span> {sim.scenario.name}
          </span>
        )}
        <span className={`api-status ${online ? 'ok' : online === false ? 'down' : ''}`}>
          <i /> {online ? 'API online' : online === false ? 'API offline' : 'Connecting…'}
        </span>
      </div>
    </header>
  )
}
