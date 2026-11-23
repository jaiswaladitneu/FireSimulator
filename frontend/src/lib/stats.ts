import type { AssetKind, IncidentBrief } from '../api/types'

export type TimeRange = 'all' | '24h' | '7d'
export type SourceFilter = 'all' | 'live' | 'simulated'
export type ResponseFilter = 'all' | 'auto' | 'manual'

export interface Filters {
  range: TimeRange
  source: SourceFilter
  response: ResponseFilter
}

export function applyFilters(list: IncidentBrief[], f: Filters, now = Date.now() / 1000): IncidentBrief[] {
  const since = f.range === '24h' ? now - 86400 : f.range === '7d' ? now - 7 * 86400 : 0
  return list.filter(
    (r) =>
      r.ended_at >= since &&
      (f.source === 'all' || r.source === f.source) &&
      (f.response === 'all' || (f.response === 'auto') === r.params.auto_dispatch),
  )
}

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0)
const avg = (xs: number[]) => (xs.length ? sum(xs) / xs.length : 0)

export interface Aggregate {
  incidents: number
  population: number
  peakAtRisk: number
  evacuated: number
  casualties: number
  destroyed: number
  damaged: number
  areaHa: number
  explosions: number
  batteryFires: number
  avgMinutes: number
  dispatches: number
  destroyedByKind: Partial<Record<AssetKind, number>>
  casualtiesByKind: Partial<Record<AssetKind, number>>
  response: Record<'auto' | 'manual', { n: number; casualties: number; destroyed: number; areaHa: number }>
}

export function aggregate(list: IncidentBrief[]): Aggregate {
  const destroyedByKind: Partial<Record<AssetKind, number>> = {}
  const casualtiesByKind: Partial<Record<AssetKind, number>> = {}
  for (const r of list) {
    for (const [k, v] of Object.entries(r.summary.by_kind) as [AssetKind, { destroyed: number; casualties: number }][]) {
      destroyedByKind[k] = (destroyedByKind[k] ?? 0) + (v?.destroyed ?? 0)
      casualtiesByKind[k] = (casualtiesByKind[k] ?? 0) + (v?.casualties ?? 0)
    }
  }
  const group = (auto: boolean) => {
    const g = list.filter((r) => r.params.auto_dispatch === auto)
    return {
      n: g.length,
      casualties: avg(g.map((r) => r.summary.population.casualties)),
      destroyed: avg(g.map((r) => r.summary.buildings.destroyed)),
      areaHa: avg(g.map((r) => r.summary.area_burned_ha)),
    }
  }
  return {
    incidents: list.length,
    population: sum(list.map((r) => r.summary.population.total)),
    peakAtRisk: Math.max(0, ...list.map((r) => r.summary.population.peak_at_risk)),
    evacuated: sum(list.map((r) => r.summary.population.evacuated)),
    casualties: sum(list.map((r) => r.summary.population.casualties)),
    destroyed: sum(list.map((r) => r.summary.buildings.destroyed)),
    damaged: sum(list.map((r) => r.summary.buildings.damaged)),
    areaHa: sum(list.map((r) => r.summary.area_burned_ha)),
    explosions: sum(list.map((r) => r.summary.hazards.explosions)),
    batteryFires: sum(list.map((r) => r.summary.hazards.battery_fires)),
    avgMinutes: avg(list.map((r) => r.ticks)),
    dispatches: sum(list.map((r) => r.summary.dispatches)),
    destroyedByKind,
    casualtiesByKind,
    response: { auto: group(true), manual: group(false) },
  }
}

/** CSV of the incident list (opens in Excel). */
export function toCsv(list: IncidentBrief[]): string {
  const head = [
    'ended_at', 'name', 'source', 'outcome', 'minutes', 'wind_toward_deg', 'wind_kmh', 'start_hour',
    'crews', 'auto_dispatch', 'population', 'peak_at_risk', 'evacuated', 'casualties_est',
    'buildings_destroyed', 'buildings_damaged', 'area_ha', 'explosions', 'battery_fires', 'dispatches', 'seed',
  ]
  const esc = (v: string | number | boolean) => {
    const s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const rows = list.map((r) => [
    new Date(r.ended_at * 1000).toISOString(), r.name, r.source, r.outcome, r.ticks,
    r.params.wind_direction, r.params.wind_speed, r.params.hour, r.params.crews, r.params.auto_dispatch,
    r.summary.population.total, r.summary.population.peak_at_risk, r.summary.population.evacuated,
    r.summary.population.casualties, r.summary.buildings.destroyed, r.summary.buildings.damaged,
    r.summary.area_burned_ha, r.summary.hazards.explosions, r.summary.hazards.battery_fires,
    r.summary.dispatches, r.params.seed,
  ])
  return [head, ...rows].map((r) => r.map(esc).join(',')).join('\n')
}
