import { describe, it, expect } from 'vitest'
import type { IncidentBrief, KindStats } from '../api/types'
import { aggregate, applyFilters, toCsv, type Filters } from './stats'

const NOW = 1_800_000_000 // fixed "current time" in seconds, so tests do not depend on the clock
const HOUR = 3600

function kind(destroyed: number, casualties: number): KindStats {
  return {
    label: '', total: 0, safe: 0, threatened: 0, burning: 0, damaged: 0, destroyed, blocked: 0,
    people: 0, present: 0, at_risk: 0, evacuated: 0, casualties,
  }
}

/** Builds an incident; only the fields a test cares about need to be passed. */
function incident(o: {
  id: string
  endedHoursAgo: number
  source?: 'live' | 'simulated'
  auto?: boolean
  casualties?: number
  destroyed?: number
  areaHa?: number
  ticks?: number
  name?: string
}): IncidentBrief {
  return {
    id: o.id,
    name: o.name ?? `Incident ${o.id}`,
    scenario_id: 'sc',
    source: o.source ?? 'live',
    outcome: 'extinguished',
    started_at: NOW - o.endedHoursAgo * HOUR - 600,
    ended_at: NOW - o.endedHoursAgo * HOUR,
    ticks: o.ticks ?? 60,
    params: {
      map_type: 'city', width: 96, height: 96, seed: 4, wind_direction: 90, wind_speed: 25, hour: 14,
      crews: 4, auto_dispatch: o.auto ?? false, ignition_points: [],
    },
    summary: {
      population: {
        total: 1000, present: 900, at_risk: 0, needs_rescue: 0, in_danger: 0, evacuated: 100,
        casualties: o.casualties ?? 0, peak_at_risk: 50,
      },
      buildings: { total: 200, threatened: 0, burning: 0, damaged: 2, destroyed: o.destroyed ?? 0, peak_burning: 0 },
      by_kind: { house: kind(o.destroyed ?? 0, o.casualties ?? 0) },
      hazards: { explosions: 1, battery_fires: 0 },
      area_burned_ha: o.areaHa ?? 0,
      dispatches: 3,
      cells_suppressed: 0,
      top_losses: [],
    },
  }
}

const ALL: Filters = { range: 'all', source: 'all', response: 'all' }

const recentLiveManual = incident({ id: 'a', endedHoursAgo: 1 })
const twoDaysSimAuto = incident({ id: 'b', endedHoursAgo: 48, source: 'simulated', auto: true })
const monthOldLive = incident({ id: 'c', endedHoursAgo: 24 * 30 })
const list = [recentLiveManual, twoDaysSimAuto, monthOldLive]

describe('Incident filters (Admin Dashboard)', () => {
  it('keeps every incident when no filter is set', () => {
    expect(applyFilters(list, ALL, NOW)).toHaveLength(3)
  })

  it('limits the time range to the last 24 hours', () => {
    expect(applyFilters(list, { ...ALL, range: '24h' }, NOW).map((r) => r.id)).toEqual(['a'])
  })

  it('limits the time range to the last 7 days', () => {
    expect(applyFilters(list, { ...ALL, range: '7d' }, NOW).map((r) => r.id)).toEqual(['a', 'b'])
  })

  it('filters by incident source', () => {
    expect(applyFilters(list, { ...ALL, source: 'simulated' }, NOW).map((r) => r.id)).toEqual(['b'])
    expect(applyFilters(list, { ...ALL, source: 'live' }, NOW).map((r) => r.id)).toEqual(['a', 'c'])
  })

  it('filters by automatic or manual crew dispatch', () => {
    expect(applyFilters(list, { ...ALL, response: 'auto' }, NOW).map((r) => r.id)).toEqual(['b'])
    expect(applyFilters(list, { ...ALL, response: 'manual' }, NOW).map((r) => r.id)).toEqual(['a', 'c'])
  })

  it('combines filters', () => {
    expect(applyFilters(list, { range: '7d', source: 'live', response: 'manual' }, NOW).map((r) => r.id)).toEqual(['a'])
  })
})

describe('Incident aggregates (Admin Dashboard KPIs)', () => {
  const a = incident({ id: 'a', endedHoursAgo: 1, auto: true, casualties: 4, destroyed: 10, areaHa: 2, ticks: 40 })
  const b = incident({ id: 'b', endedHoursAgo: 2, auto: true, casualties: 2, destroyed: 6, areaHa: 4, ticks: 80 })
  const c = incident({ id: 'c', endedHoursAgo: 3, auto: false, casualties: 9, destroyed: 20, areaHa: 6, ticks: 60 })

  it('returns zeros for an empty history', () => {
    const agg = aggregate([])
    expect(agg.incidents).toBe(0)
    expect(agg.casualties).toBe(0)
    expect(agg.peakAtRisk).toBe(0)
    expect(agg.avgMinutes).toBe(0)
    expect(agg.response.auto).toEqual({ n: 0, casualties: 0, destroyed: 0, areaHa: 0 })
  })

  it('sums totals across incidents', () => {
    const agg = aggregate([a, b, c])
    expect(agg.incidents).toBe(3)
    expect(agg.population).toBe(3000)
    expect(agg.casualties).toBe(15)
    expect(agg.destroyed).toBe(36)
    expect(agg.areaHa).toBe(12)
    expect(agg.explosions).toBe(3)
    expect(agg.dispatches).toBe(9)
    expect(agg.avgMinutes).toBe(60)
  })

  it('breaks losses down by kind of place', () => {
    const agg = aggregate([a, b, c])
    expect(agg.destroyedByKind.house).toBe(36)
    expect(agg.casualtiesByKind.house).toBe(15)
  })

  it('averages outcomes per response type so auto and manual can be compared', () => {
    const agg = aggregate([a, b, c])
    expect(agg.response.auto).toEqual({ n: 2, casualties: 3, destroyed: 8, areaHa: 3 })
    expect(agg.response.manual).toEqual({ n: 1, casualties: 9, destroyed: 20, areaHa: 6 })
  })
})

describe('CSV export', () => {
  it('writes a header row and one row per incident', () => {
    const lines = toCsv([recentLiveManual, twoDaysSimAuto]).split('\n')
    expect(lines).toHaveLength(3)
    expect(lines[0].startsWith('ended_at,name,source,outcome,minutes')).toBe(true)
    expect(lines[0].split(',')).toHaveLength(21)
    expect(lines[2].split(',')[2]).toBe('simulated')
  })

  it('writes the end time as an ISO date', () => {
    const row = toCsv([recentLiveManual]).split('\n')[1]
    expect(row.split(',')[0]).toBe(new Date((NOW - HOUR) * 1000).toISOString())
  })

  it('quotes names that contain commas or quotes', () => {
    const row = toCsv([incident({ id: 'q', endedHoursAgo: 1, name: 'Ridge "North", sector 2' })]).split('\n')[1]
    expect(row).toContain('"Ridge ""North"", sector 2"')
  })
})
