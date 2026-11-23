import { Crosshair, LifeBuoy, ListChecks, Lock, Navigation, Truck, Wind } from 'lucide-react'
import { useState } from 'react'
import type { CityState, Priority } from '../../api/types'
import { fmt, fmtDistance } from '../../lib/format'
import { KIND_META, LEVEL_LABEL, STATUS_LABEL, levelClass, statusClass } from '../../lib/kinds'

interface Props {
  city: CityState | null
  selectedId: number | null
  canDispatch: boolean
  onDispatch: (id: number) => void
  onFocus: (id: number) => void
  onSelect: (id: number) => void
}

function Row({ p, rank, selected, canDispatch, onDispatch, onFocus, onSelect }: {
  p: Priority
  rank: number
  selected: boolean
  canDispatch: boolean
  onDispatch: (id: number) => void
  onFocus: (id: number) => void
  onSelect: (id: number) => void
}) {
  const Icon = KIND_META[p.kind].icon
  const covered = p.crews.length > 0
  return (
    <li className={`prio ${levelClass(p.level)} ${selected ? 'sel' : ''}`} onClick={() => onSelect(p.id)}>
      <div className="prio-rank">{rank}</div>
      <div className="prio-main">
        <div className="prio-title">
          <Icon size={14} className="kind-ico" />
          <span className="prio-name" title={p.name}>{p.name}</span>
        </div>
        <div className="prio-tags">
          <span className={`badge ${levelClass(p.level)}`}>{LEVEL_LABEL[p.level]}</span>
          <span className={`chip ${statusClass(p.status)}`}>{STATUS_LABEL[p.status]}</span>
          <span className="chip ghost"><Navigation size={11} /> {fmtDistance(p.distance_m)}</span>
          {p.downwind && <span className="chip ghost"><Wind size={11} /> downwind</span>}
        </div>
        <div className="prio-reasons">{p.reasons.slice(1).join(' · ') || p.reasons[0]}</div>
        {covered && (
          <div className="prio-crews"><Truck size={12} /> {p.crews.join(', ')}</div>
        )}
      </div>
      <div className="prio-side">
        <div className="prio-people" title="People at risk">
          <strong>{fmt(p.at_risk)}</strong>
          <small>at risk</small>
        </div>
        {p.needs_rescue > 0 && (
          <div className="sos" title="Cannot evacuate without help"><LifeBuoy size={11} /> {p.needs_rescue}</div>
        )}
        <div className="prio-actions" onClick={(e) => e.stopPropagation()}>
          <button className="btn btn-fire btn-xs" disabled={!canDispatch} onClick={() => onDispatch(p.id)} title={canDispatch ? 'Send the nearest free crew' : 'No crews available'}>
            <Truck size={12} /> {covered ? 'Add crew' : 'Dispatch'}
          </button>
          <button className="icon-btn sm" onClick={() => onFocus(p.id)} title="Show on map" aria-label={`Show ${p.name} on map`}>
            <Crosshair size={14} />
          </button>
        </div>
      </div>
    </li>
  )
}

/** Ranked list of what to protect first: lives, then hazards. */
export function PriorityQueue({ city, selectedId, canDispatch, onDispatch, onFocus, onSelect }: Props) {
  const live = city?.priorities ?? []
  // While the pointer is over the list its order is held, so buttons don't move under the cursor.
  const [held, setHeld] = useState<number[] | null>(null)
  let items = live
  if (held) {
    const byId = new Map(live.map((p) => [p.id, p]))
    const kept = held.map((id) => byId.get(id)).filter((p): p is Priority => !!p)
    items = [...kept, ...live.filter((p) => !held.includes(p.id))]
  }
  const critical = items.filter((p) => p.level === 'critical').length
  return (
    <section className="panel grow">
      <header className="panel-head">
        <div>
          <h2><ListChecks size={15} /> Response priorities</h2>
          <p className="panel-sub">
            {held ? <><Lock size={10} /> Order held while you point at the list</> : 'Ranked by lives at risk, people who need rescue, then fuel and battery hazards'}
          </p>
        </div>
        {items.length > 0 && <span className={`count ${critical ? 'lv-critical' : ''}`}>{critical ? `${critical} critical` : items.length}</span>}
      </header>
      {items.length === 0 ? (
        <div className="empty">
          <p><strong>No areas are threatened right now.</strong></p>
          <p className="muted">When fire comes within 80 m of a home, school, hospital, road or hazardous site it appears here, ranked by urgency.</p>
        </div>
      ) : (
        <ol className="prio-list" onPointerEnter={() => setHeld(live.slice(0, 12).map((p) => p.id))} onPointerLeave={() => setHeld(null)}>
          {items.slice(0, 12).map((p, i) => (
            <Row key={p.id} p={p} rank={i + 1} selected={p.id === selectedId} canDispatch={canDispatch} onDispatch={onDispatch} onFocus={onFocus} onSelect={onSelect} />
          ))}
        </ol>
      )}
    </section>
  )
}
