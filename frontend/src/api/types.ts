// Shapes of the Fire Simulator API payloads (see api/main.py and engine/city.py).

export type SimStatus = 'idle' | 'running' | 'paused' | 'completed'
export type MapType = 'wildland' | 'city'
export type AssetKind =
  | 'house'
  | 'commercial'
  | 'school'
  | 'hospital'
  | 'fuel_station'
  | 'battery_storage'
  | 'fire_station'
  | 'park'
  | 'road'
export type PriorityLevel = 'critical' | 'high' | 'medium' | 'low'
export type Severity = 'critical' | 'warning' | 'info'

/** Asset status codes, in the order the API uses them. */
export const STATUS_NAMES = ['safe', 'threatened', 'burning', 'damaged', 'destroyed', 'blocked'] as const
export type AssetStatus = (typeof STATUS_NAMES)[number]

/** Cell states of the fire grid. */
export const CELL = { UNBURNED: 0, IGNITING: 1, BURNING: 2, BURNED: 3, SUPPRESSED: 4 } as const

/** Land use codes (engine/landuse.py). */
export const LU = {
  WATER: 0, ROAD: 1, PAVED: 2, GRASS: 3, SHRUB: 4, FOREST: 5, LAWN: 6, PARK: 7, HOUSE: 8,
  COMMERCIAL: 9, SCHOOL: 10, HOSPITAL: 11, FUEL_STATION: 12, BATTERY: 13, FIRE_STATION: 14,
} as const

/** Fuel codes (engine/cell.py). */
export const FUEL = { NONE: 0, GRASS: 1, SHRUB: 2, FOREST: 3, STRUCTURE: 4, MASONRY: 5, HAZMAT: 6 } as const

export interface AssetPart {
  x: number
  y: number
  w: number
  h: number
  height: number
  style: string
}

export interface Asset {
  id: number
  kind: AssetKind
  name: string
  street: string
  x: number
  y: number
  w: number
  h: number
  floors: number
  capacity: number
  occupants0: number
  parts: AssetPart[]
}

export interface MapData {
  map_type: MapType
  width: number
  height: number
  cell_size_m: number
  landuse: number[][]
  fuel: number[][]
  elevation: number[][]
  assets: Asset[]
  station: { x: number; y: number } | null
  crews: { id: number; name: string }[]
  hour: number
  kinds: Record<string, { label: string; vulnerability: number; hazard: number }>
}

export interface Priority {
  id: number
  kind: AssetKind
  name: string
  status: AssetStatus
  level: PriorityLevel
  score: number
  at_risk: number
  needs_rescue: number
  distance_m: number | null
  downwind: boolean
  reasons: string[]
  crews: string[]
}

export interface Crew {
  id: number
  name: string
  status: 'available' | 'en_route' | 'working'
  target: number | null
  x: number
  y: number
  eta: number
  work_left: number
  cells_suppressed: number
}

export interface SimEvent {
  tick: number
  clock: string
  type: string
  message: string
  asset_id: number | null
  severity: Severity
}

export interface KindStats {
  label: string
  total: number
  safe: number
  threatened: number
  burning: number
  damaged: number
  destroyed: number
  blocked: number
  people: number
  present: number
  at_risk: number
  evacuated: number
  casualties: number
}

export interface Population {
  total: number
  present: number
  at_risk: number
  needs_rescue: number
  in_danger: number
  evacuated: number
  casualties: number
  peak_at_risk: number
}

export interface BuildingStats {
  total: number
  threatened: number
  burning: number
  damaged: number
  destroyed: number
  peak_burning: number
}

export interface TimelinePoint {
  t: number
  burning: number
  burned: number
  at_risk: number
  casualties: number
  evacuated: number
  bld_burning: number
  bld_destroyed: number
}

export interface CityState {
  clock: string
  hour: number
  minutes: number
  population: Population
  buildings: BuildingStats
  by_kind: Partial<Record<AssetKind, KindStats>>
  assets: {
    status: number[]
    occupants: number[]
    evacuated: number[]
    casualties: number[]
    at_risk: number[]
    needs_rescue: number[]
    burning: number[]
    burned: number[]
    dist: number[]
  }
  priorities: Priority[]
  crews: Crew[]
  crews_available: number
  auto_dispatch: boolean
  dispatches: number
  cells_suppressed: number
  events: SimEvent[]
  hazards: { explosions: number; battery_fires: number }
  area_burned_ha: number
  timeline: TimelinePoint | null
}

export interface SimPayload {
  state: SimStatus
  tick: number
  speed: number
  counts: Record<string, number>
  grid: number[][]
  map_type: MapType
  scenario: { id: string; name: string }
  /** Direction the wind blows toward (degrees, 0 = N) and speed in km/h. */
  wind: { direction: number; speed: number }
  incident_id: string | null
  city: CityState | null
}

export interface ScenarioParams {
  name: string
  width: number
  height: number
  seed: number
  wind_direction: number
  wind_speed: number
  map_type: MapType
  hour: number
  crews: number
  auto_dispatch: boolean
  ignition_points?: { x: number; y: number }[]
}

export interface IncidentParams {
  map_type: MapType
  width: number
  height: number
  seed: number
  wind_direction: number
  wind_speed: number
  hour: number
  crews: number
  auto_dispatch: boolean
  ignition_points: { x: number; y: number; tick: number }[]
}

export interface TopLoss {
  name: string
  kind: AssetKind
  casualties: number
  status: AssetStatus
}

export interface IncidentSummary {
  population: Population
  buildings: BuildingStats
  by_kind: Partial<Record<AssetKind, KindStats>>
  hazards: { explosions: number; battery_fires: number }
  area_burned_ha: number
  dispatches: number
  cells_suppressed: number
  top_losses: TopLoss[]
}

export interface IncidentBrief {
  id: string
  name: string
  scenario_id: string
  source: 'live' | 'simulated'
  outcome: 'extinguished' | 'stopped' | 'time_limit'
  started_at: number
  ended_at: number
  ticks: number
  params: IncidentParams
  summary: IncidentSummary
}

export interface IncidentFull extends Omit<IncidentBrief, 'summary'> {
  summary: IncidentSummary & { timeline: TimelinePoint[]; key_events: SimEvent[] }
}
