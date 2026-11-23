import { Building2, Clock, Flame, Footprints, HeartCrack, LifeBuoy, Mountain, ShieldAlert, Users } from 'lucide-react'
import type { AssetKind, SimPayload } from '../../api/types'
import { fmt, fmtHa, fmtMinutes } from '../../lib/format'
import { KIND_META, KIND_ORDER } from '../../lib/kinds'

interface Props {
  sim: SimPayload | null
}

/** Breakdown such as "12 houses · 2 shops · 1 school" for one status. */
function breakdown(sim: SimPayload, key: 'burning' | 'destroyed') {
  const byKind = sim.city?.by_kind ?? {}
  const parts: string[] = []
  for (const k of KIND_ORDER) {
    if (k === 'road' || k === 'park') continue
    const n = byKind[k as AssetKind]?.[key] ?? 0
    if (n > 0) parts.push(`${n} ${n === 1 ? KIND_META[k].label.toLowerCase() : KIND_META[k].plural.toLowerCase()}`)
  }
  return parts.slice(0, 3).join(' · ')
}

/** The life-safety strip across the top of the command center. */
export function LifeSafetyHud({ sim }: Props) {
  const city = sim?.city
  const pop = city?.population
  const bld = city?.buildings
  const atRisk = pop?.at_risk ?? 0
  const status = sim?.state ?? 'idle'

  return (
    <section className="hud" aria-label="Life safety summary">
      <div className={`hud-card hud-hero ${atRisk > 0 ? 'alert' : ''}`}>
        <div className="hud-label"><ShieldAlert size={15} /> Lives at risk</div>
        <div className="hud-value">{city ? fmt(atRisk) : '—'}</div>
        <div className="hud-sub">{pop ? `of ${fmt(pop.total)} people in town · peak ${fmt(pop.peak_at_risk)}` : 'Generate a town to begin'}</div>
      </div>
      <div className={`hud-card ${pop && pop.needs_rescue > 0 ? 'danger' : ''}`}>
        <div className="hud-label"><LifeBuoy size={14} /> Need rescue</div>
        <div className="hud-value sm">{pop ? fmt(pop.needs_rescue) : '—'}</div>
        <div className="hud-sub">cannot evacuate unaided</div>
      </div>
      <div className={`hud-card ${pop && pop.in_danger > 0 ? 'danger' : ''}`}>
        <div className="hud-label"><Users size={14} /> In immediate danger</div>
        <div className="hud-value sm">{pop ? fmt(pop.in_danger) : '—'}</div>
        <div className="hud-sub">inside burning buildings or cut-off roads</div>
      </div>
      <div className="hud-card good">
        <div className="hud-label"><Footprints size={14} /> Evacuated</div>
        <div className="hud-value sm">{pop ? fmt(pop.evacuated) : '—'}</div>
        <div className="hud-sub">moved to safety</div>
      </div>
      <div className={`hud-card ${pop && pop.casualties > 0 ? 'loss' : ''}`}>
        <div className="hud-label"><HeartCrack size={14} /> Casualties (est.)</div>
        <div className="hud-value sm">{pop ? fmt(pop.casualties) : '—'}</div>
        <div className="hud-sub">model estimate</div>
      </div>
      <div className={`hud-card ${bld && bld.burning > 0 ? 'fire' : ''}`}>
        <div className="hud-label"><Flame size={14} /> Buildings on fire</div>
        <div className="hud-value sm">{bld ? fmt(bld.burning) : '—'}</div>
        <div className="hud-sub">{sim && bld?.burning ? breakdown(sim, 'burning') : 'right now'}</div>
      </div>
      <div className="hud-card">
        <div className="hud-label"><Building2 size={14} /> Destroyed</div>
        <div className="hud-value sm">{bld ? fmt(bld.destroyed) : '—'}</div>
        <div className="hud-sub">{sim && bld?.destroyed ? breakdown(sim, 'destroyed') : bld ? `of ${fmt(bld.total)} buildings` : ''}</div>
      </div>
      <div className="hud-card">
        <div className="hud-label"><Mountain size={14} /> Area burned</div>
        <div className="hud-value sm">{city ? fmtHa(city.area_burned_ha) : '—'}</div>
        <div className="hud-sub">{city ? `${city.hazards.explosions} explosions · ${city.hazards.battery_fires} battery fires` : ''}</div>
      </div>
      <div className="hud-card hud-clock">
        <div className="hud-label"><Clock size={14} /> Incident clock</div>
        <div className="hud-value sm mono">{city?.clock ?? '--:--'}</div>
        <div className="hud-sub">
          <span className={`pill pill-${status}`}>{status}</span> {sim ? `T+${fmtMinutes(sim.tick)}` : ''}
        </div>
      </div>
    </section>
  )
}
