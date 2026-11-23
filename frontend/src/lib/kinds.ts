import {
  BatteryCharging,
  Car,
  Fuel,
  Hospital,
  House,
  School,
  Siren,
  Store,
  Trees,
  type LucideIcon,
} from 'lucide-react'
import type { AssetKind, AssetStatus, PriorityLevel, Severity } from '../api/types'

export interface KindMeta {
  label: string
  plural: string
  icon: LucideIcon
  /** Short noun for the people at this kind of place. */
  people: string
  /** Shown first in summaries (life-safety order). */
  order: number
}

export const KIND_META: Record<AssetKind, KindMeta> = {
  hospital: { label: 'Hospital', plural: 'Hospitals', icon: Hospital, people: 'patients & staff', order: 0 },
  school: { label: 'School', plural: 'Schools', icon: School, people: 'students & staff', order: 1 },
  house: { label: 'House', plural: 'Houses', icon: House, people: 'residents', order: 2 },
  commercial: { label: 'Shop / office', plural: 'Shops & offices', icon: Store, people: 'shoppers & staff', order: 3 },
  fuel_station: { label: 'Fuel station', plural: 'Fuel stations', icon: Fuel, people: 'customers & staff', order: 4 },
  battery_storage: { label: 'Battery storage', plural: 'Battery storage', icon: BatteryCharging, people: 'staff', order: 5 },
  fire_station: { label: 'Fire station', plural: 'Fire stations', icon: Siren, people: 'firefighters', order: 6 },
  park: { label: 'Park', plural: 'Parks', icon: Trees, people: 'visitors', order: 7 },
  road: { label: 'Road', plural: 'Road segments', icon: Car, people: 'people in vehicles', order: 8 },
}

export const KIND_ORDER = (Object.keys(KIND_META) as AssetKind[]).sort(
  (a, b) => KIND_META[a].order - KIND_META[b].order,
)

export const STATUS_LABEL: Record<AssetStatus, string> = {
  safe: 'Safe',
  threatened: 'Threatened',
  burning: 'On fire',
  damaged: 'Damaged',
  destroyed: 'Destroyed',
  blocked: 'Blocked',
}

export const LEVEL_LABEL: Record<PriorityLevel, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

/** CSS class suffix per status / level / severity (colours live in the stylesheet). */
export const statusClass = (s: AssetStatus) => `st-${s}`
export const levelClass = (l: PriorityLevel) => `lv-${l}`
export const severityClass = (s: Severity) => `sv-${s}`

export const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'] as const
export const compassName = (deg: number) => COMPASS[Math.round((((deg % 360) + 360) % 360) / 45) % 8]
