import {
  ArrowRight, Bot, Crosshair, Flame, Fullscreen, LayoutDashboard, LifeBuoy, ListChecks, Minimize2,
  MousePointerClick, Scan, Truck, ZoomIn,
} from 'lucide-react'
import type { Asset, CityState, SimPayload } from '../../api/types'
import { STATUS_NAMES } from '../../api/types'
import { fmt, fmtMinutes } from '../../lib/format'
import { KIND_META, LEVEL_LABEL, STATUS_LABEL, compassName, levelClass, statusClass } from '../../lib/kinds'

export function WindCompass({ sim }: { sim: SimPayload | null }) {
  if (!sim) return null
  const { direction, speed } = sim.wind
  return (
    <div className="overlay compass" title={`Wind blowing toward ${compassName(direction)} at ${speed} km/h`}>
      <div className="compass-dial">
        <span className="n">N</span>
        <div className="compass-needle" style={{ transform: `rotate(${direction}deg)` }} />
      </div>
      <div className="compass-text">
        <strong className="mono">{Math.round(speed)}</strong>
        <small>km/h</small>
        <small className="muted">to {compassName(direction)}</small>
      </div>
    </div>
  )
}

export function MapToolbar({ igniteMode, canIgnite, bigScreen, onIgnite, onOverview, onBigScreen }: {
  igniteMode: boolean
  canIgnite: boolean
  bigScreen: boolean
  onIgnite: (on: boolean) => void
  onOverview: () => void
  onBigScreen: () => void
}) {
  return (
    <div className="overlay toolbar">
      <button
        className={`icon-btn ${bigScreen ? 'active' : ''}`}
        onClick={onBigScreen}
        title={bigScreen ? 'Exit big screen (Esc)' : 'Big-screen view: show the map on the whole screen (F)'}
        aria-pressed={bigScreen}
        aria-label={bigScreen ? 'Exit big-screen view' : 'Big-screen view'}
      >
        {bigScreen ? <Minimize2 size={16} /> : <Fullscreen size={16} />}
      </button>
      <button className="icon-btn" onClick={onOverview} title="Whole-town view: fit the whole town on screen" aria-label="Whole-town view"><Scan size={16} /></button>
      <button
        className={`icon-btn ${igniteMode ? 'active-fire' : ''}`}
        onClick={() => onIgnite(!igniteMode)}
        disabled={!canIgnite}
        title={igniteMode ? 'Ignition mode on: click the map to start a fire' : 'Start a fire by clicking the map'}
        aria-pressed={igniteMode}
        aria-label="Ignition mode"
      >
        <Flame size={16} />
      </button>
    </div>
  )
}

/** Compact life-safety strip shown on top of the map in big-screen view. */
export function BigScreenHud({ sim }: { sim: SimPayload | null }) {
  const c = sim?.city
  if (!sim || !c) return null
  const p = c.population
  const b = c.buildings
  return (
    <div className="overlay bs-hud" aria-label="Live summary">
      <div className={`bs-card bs-hero ${p.at_risk > 0 ? 'alert' : ''}`}>
        <span>Lives at risk</span>
        <strong>{fmt(p.at_risk)}</strong>
        <small>of {fmt(p.total)} in town</small>
      </div>
      <div className={`bs-card ${p.needs_rescue > 0 ? 'danger' : ''}`}><span>Need rescue</span><strong>{fmt(p.needs_rescue)}</strong></div>
      <div className={`bs-card ${b.burning > 0 ? 'fire' : ''}`}><span>Buildings on fire</span><strong>{fmt(b.burning)}</strong></div>
      <div className="bs-card"><span>Destroyed</span><strong>{fmt(b.destroyed)}</strong></div>
      <div className="bs-card good"><span>Evacuated</span><strong>{fmt(p.evacuated)}</strong></div>
      <div className={`bs-card ${p.casualties > 0 ? 'loss' : ''}`}><span>Casualties (est.)</span><strong>{fmt(p.casualties)}</strong></div>
      <div className="bs-card">
        <span className="bs-name" title={sim.scenario.name}>{sim.scenario.name}</span>
        <strong className="mono">{c.clock}</strong>
        <small><span className={`pill pill-${sim.state}`}>{sim.state}</span> T+{fmtMinutes(sim.tick)}</small>
      </div>
    </div>
  )
}

/** Top priorities with dispatch, shown in big-screen view (the side panels are hidden there). */
export function BigScreenPriorities({ city, canDispatch, onDispatch, onFocus }: {
  city: CityState | null
  canDispatch: boolean
  onDispatch: (id: number) => void
  onFocus: (id: number) => void
}) {
  if (!city) return null
  const items = city.priorities.slice(0, 5)
  return (
    <div className="overlay bs-prios">
      <div className="bs-prios-head">
        <span><ListChecks size={14} /> Top priorities</span>
        <span className="muted small">
          <Truck size={12} /> {city.crews_available}/{city.crews.length} free{city.auto_dispatch && <> · <Bot size={12} /> auto</>}
        </span>
      </div>
      {items.length === 0 ? (
        <p className="muted small">No areas are threatened right now.</p>
      ) : (
        <ol>
          {items.map((p, i) => {
            const Icon = KIND_META[p.kind].icon
            return (
              <li key={p.id} className={`bs-prio ${levelClass(p.level)}`}>
                <span className="bs-rank">{i + 1}</span>
                <div className="bs-main">
                  <strong title={p.name}><Icon size={12} /> {p.name}</strong>
                  <small>
                    {LEVEL_LABEL[p.level]} · {STATUS_LABEL[p.status]} · {fmt(p.at_risk)} at risk
                    {p.needs_rescue > 0 ? ` · ${p.needs_rescue} need help` : ''}
                    {p.crews.length > 0 ? ` · ${p.crews.join(', ')}` : ''}
                  </small>
                </div>
                <button className="btn btn-fire btn-xs" disabled={!canDispatch} onClick={() => onDispatch(p.id)} title="Send the nearest free crew">
                  <Truck size={12} />
                </button>
                <button className="icon-btn sm" onClick={() => onFocus(p.id)} title="Show on map" aria-label={`Show ${p.name} on map`}>
                  <Crosshair size={13} />
                </button>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

export function Legend() {
  return (
    <div className="overlay legend">
      <span><i className="sw sw-burning" />Burning</span>
      <span><i className="sw sw-burned" />Burned</span>
      <span><i className="sw sw-wet" />Suppressed</span>
      <span><i className="sw sw-crit" />Critical priority</span>
      <span className="muted"><ZoomIn size={12} /> Zoom in for people counts</span>
    </div>
  )
}

export function HoverCard({ asset, city, x, y }: { asset: Asset | null; city: CityState | null; x: number; y: number }) {
  if (!asset) return null
  const meta = KIND_META[asset.kind]
  const Icon = meta.icon
  const a = city?.assets
  const status = a ? STATUS_NAMES[a.status[asset.id]] ?? 'safe' : 'safe'
  const people = a ? a.occupants[asset.id] : asset.occupants0
  const rescue = a ? a.needs_rescue[asset.id] : 0
  return (
    <div className="hovercard" style={{ left: x + 14, top: y + 14 }}>
      <div className="hc-title"><Icon size={13} /> {asset.name}</div>
      <div className="hc-row">
        <span className={`chip ${statusClass(status)}`}>{STATUS_LABEL[status]}</span>
        <span><strong>{fmt(people)}</strong> {asset.kind === 'road' ? 'in vehicles' : meta.people}</span>
      </div>
      {rescue > 0 && <div className="hc-sos"><LifeBuoy size={12} /> {rescue} need help to evacuate</div>}
    </div>
  )
}

export function EmptyState({ online }: { online: boolean | null }) {
  return (
    <div className="map-empty">
      <div className="map-empty-card">
        <Flame size={28} className="fire-text" />
        <h3>Incident command center</h3>
        <p>Generate a town in <strong>Incident setup</strong>: homes, schools, a hospital, shops, parks, fuel stations and a battery-storage site, surrounded by forested hills.</p>
        <ul>
          <li><MousePointerClick size={14} /> Click buildings and roads to see who is there right now</li>
          <li><ZoomIn size={14} /> Zoom in to see people counts on every house and street</li>
          <li><Crosshair size={14} /> Dispatch crews from the priority list, lives first</li>
        </ul>
        {online === false && <p className="danger-text">The simulation API is not reachable on port 8000.</p>}
      </div>
    </div>
  )
}

export function CompletionBanner({ sim, onDashboard, onDismiss }: { sim: SimPayload; onDashboard: () => void; onDismiss: () => void }) {
  const p = sim.city?.population
  const b = sim.city?.buildings
  return (
    <div className="overlay done-banner">
      <div>
        <strong>{sim.counts.burning + sim.counts.igniting > 0 ? 'Incident closed' : 'Fire is out'}</strong> after {fmtMinutes(sim.tick)}.
        {p && b && (
          <span className="muted"> {fmt(p.evacuated)} evacuated · {fmt(p.casualties)} casualties (est.) · {fmt(b.destroyed)} buildings destroyed.</span>
        )}
        {sim.incident_id && <span className="muted"> Recorded in the incident history.</span>}
      </div>
      <div className="row gap">
        {sim.incident_id && (
          <button className="btn btn-primary btn-sm" onClick={onDashboard}><LayoutDashboard size={14} /> View in dashboard <ArrowRight size={14} /></button>
        )}
        <button className="btn btn-ghost btn-sm" onClick={onDismiss}>Dismiss</button>
      </div>
    </div>
  )
}
