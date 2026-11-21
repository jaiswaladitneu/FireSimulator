import {
  BatteryCharging,
  Car,
  Flame,
  Footprints,
  HeartCrack,
  House,
  Info,
  Radio,
  Truck,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { SimEvent } from '../../api/types'
import { severityClass } from '../../lib/kinds'

interface Props {
  events: SimEvent[]
  onSelect: (assetId: number) => void
}

const ICONS: Record<string, LucideIcon> = {
  evacuation: Footprints,
  fire: Flame,
  destroyed: House,
  casualties: HeartCrack,
  explosion: Zap,
  hazmat: BatteryCharging,
  road: Car,
  dispatch: Truck,
  arrival: Truck,
  cleared: Truck,
  auto: Info,
}

/** Live incident log, newest first. */
export function EventFeed({ events, onSelect }: Props) {
  return (
    <section className="panel grow feed-panel">
      <header className="panel-head">
        <div>
          <h2><Radio size={15} /> Incident log</h2>
          <p className="panel-sub">Evacuations, fires, losses and crew movements</p>
        </div>
      </header>
      {events.length === 0 ? (
        <p className="muted small">Nothing yet. Press play to start the fire.</p>
      ) : (
        <ul className="feed">
          {events.map((e, i) => {
            const Icon = ICONS[e.type] ?? Info
            const clickable = e.asset_id != null
            return (
              <li
                key={`${e.tick}-${i}-${e.message}`}
                className={`feed-item ${severityClass(e.severity)} ${e.type === 'explosion' ? 'boom' : ''} ${clickable ? 'clickable' : ''}`}
                onClick={clickable ? () => onSelect(e.asset_id!) : undefined}
              >
                <span className="feed-time mono">{e.clock}</span>
                <Icon size={13} className="feed-ico" />
                <span className="feed-msg">{e.message}</span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
