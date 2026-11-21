import { Crosshair, LifeBuoy, MapPin, Truck, X } from 'lucide-react'
import type { Asset, CityState } from '../../api/types'
import { STATUS_NAMES } from '../../api/types'
import { fmt, fmtDistance } from '../../lib/format'
import { KIND_META, STATUS_LABEL, statusClass } from '../../lib/kinds'

interface Props {
  asset: Asset | null
  city: CityState | null
  canDispatch: boolean
  onDispatch: (id: number) => void
  onFocus: (id: number) => void
  onClose: () => void
}

/** Details of the building, park or road the user clicked. */
export function Inspector({ asset, city, canDispatch, onDispatch, onFocus, onClose }: Props) {
  if (!asset) {
    return (
      <section className="panel inspector empty-inspector">
        <p className="muted small"><MapPin size={13} /> Click any building, park or road on the map to see how many people are there right now. Zoom in to see counts on every house and street.</p>
      </section>
    )
  }
  const meta = KIND_META[asset.kind]
  const Icon = meta.icon
  const i = asset.id
  const a = city?.assets
  const status = a ? STATUS_NAMES[a.status[i]] ?? 'safe' : 'safe'
  const present = a ? a.occupants[i] : asset.occupants0
  const crews = city?.crews.filter((c) => c.target === i) ?? []
  const dist = a ? a.dist[i] : 99
  const pctBurned = a ? Math.round(a.burned[i] * 100) : 0
  const pctBurning = a ? Math.round(a.burning[i] * 100) : 0

  return (
    <section className="panel inspector">
      <header className="panel-head">
        <div className="insp-title">
          <span className="insp-ico"><Icon size={16} /></span>
          <div>
            <h2>{asset.name}</h2>
            <p className="panel-sub">{meta.label}{asset.street && asset.kind !== 'road' ? ` · ${asset.street}` : ''}</p>
          </div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close details"><X size={16} /></button>
      </header>
      <div className="insp-status">
        <span className={`chip ${statusClass(status)}`}>{STATUS_LABEL[status]}</span>
        <span className="chip ghost">Fire {dist > 12 ? '> 120 m' : fmtDistance(dist * 10)}</span>
        {(pctBurning > 0 || pctBurned > 0) && <span className="chip ghost">{pctBurning}% burning · {pctBurned}% burned</span>}
      </div>
      <div className="insp-people">
        <div className="big-stat">
          <strong>{fmt(present)}</strong>
          <span>{asset.kind === 'road' ? 'people in vehicles now' : `${meta.people} here now`}</span>
        </div>
        <dl className="insp-grid">
          <div><dt>Normally here at this hour</dt><dd>{fmt(asset.occupants0)}</dd></div>
          <div><dt>Capacity</dt><dd>{fmt(asset.capacity)}</dd></div>
          <div><dt>Evacuated</dt><dd className="good-text">{a ? fmt(a.evacuated[i]) : '—'}</dd></div>
          <div><dt>Casualties (est.)</dt><dd className={a && a.casualties[i] > 0 ? 'danger-text' : ''}>{a ? fmt(a.casualties[i]) : '—'}</dd></div>
          {asset.kind !== 'road' && asset.kind !== 'park' && <div><dt>Floors</dt><dd>{asset.floors}</dd></div>}
          <div><dt>At risk now</dt><dd className={a && a.at_risk[i] > 0 ? 'danger-text' : ''}>{a ? fmt(a.at_risk[i]) : '—'}</dd></div>
        </dl>
        {a && a.needs_rescue[i] > 0 && (
          <div className="sos-banner"><LifeBuoy size={14} /> {a.needs_rescue[i]} {a.needs_rescue[i] === 1 ? 'person' : 'people'} cannot leave without a crew</div>
        )}
      </div>
      {crews.length > 0 && <p className="small"><Truck size={12} /> {crews.map((c) => `${c.name} (${c.status === 'working' ? 'on scene' : `ETA ${c.eta} min`})`).join(', ')}</p>}
      <div className="row gap">
        <button className="btn btn-fire" disabled={!canDispatch || status === 'destroyed'} onClick={() => onDispatch(i)}>
          <Truck size={14} /> Dispatch crew
        </button>
        <button className="btn btn-ghost" onClick={() => onFocus(i)}><Crosshair size={14} /> Focus</button>
      </div>
    </section>
  )
}
