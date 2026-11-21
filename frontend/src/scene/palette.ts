// Colour helpers and the 3-D palette for the town view.

export type RGB = [number, number, number]

export const hex = (h: string): RGB => {
  const v = parseInt(h.replace('#', ''), 16)
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255]
}

export const mix = (a: RGB, b: RGB, t: number): RGB => [
  a[0] + (b[0] - a[0]) * t,
  a[1] + (b[1] - a[1]) * t,
  a[2] + (b[2] - a[2]) * t,
]

/** Deterministic 0..1 hash of two integers (stable texture noise). */
export const hash2 = (x: number, y: number) => {
  let h = (x * 374761393 + y * 668265263) | 0
  h = (h ^ (h >>> 13)) * 1274126177
  h ^= h >>> 16
  return (h >>> 0) / 4294967295
}

/** Deterministic 0..1 hash of one integer (per-asset colour choice etc.). */
export const hash1 = (n: number) => hash2(n, 7919)

export const pick = <T>(list: readonly T[], n: number): T => list[Math.floor(hash1(n) * list.length) % list.length]

// Ground colours by land use code (engine/landuse.py order).
export const GROUND: Record<number, { c: RGB; noise: number }> = {
  0: { c: hex('#2a6a8a'), noise: 5 },    // water
  1: { c: hex('#33363b'), noise: 6 },    // road
  2: { c: hex('#6d7277'), noise: 6 },    // paved
  3: { c: hex('#8d9a50'), noise: 14 },   // wild grass
  4: { c: hex('#687a3a'), noise: 12 },   // shrub
  5: { c: hex('#33502b'), noise: 10 },   // forest floor
  6: { c: hex('#5b9a44'), noise: 9 },    // lawn
  7: { c: hex('#4e9744'), noise: 9 },    // park
  8: { c: hex('#4a4d52'), noise: 4 },    // building footprints ...
  9: { c: hex('#4a4d52'), noise: 4 },
  10: { c: hex('#4a4d52'), noise: 4 },
  11: { c: hex('#4a4d52'), noise: 4 },
  12: { c: hex('#4a4d52'), noise: 4 },
  13: { c: hex('#4a4d52'), noise: 4 },
  14: { c: hex('#4a4d52'), noise: 4 },
}

export const ROAD_CURB = hex('#7a7f86')
export const ROAD_LINE = hex('#e3c65a')
export const WATER_BANK = hex('#3f8db0')
export const UNDER_TREE = hex('#3d7434')

export const FIRE_GROUND = hex('#3a170a')
export const IGNITE_GROUND = hex('#8a3410')
export const CHAR = hex('#24201d')
export const ASH = hex('#4d4843')
export const WET = hex('#2c6aa3')

export const EMBER_HOT = hex('#ff8a1e')
export const EMBER_WARM = hex('#ff4d0d')
export const SMOULDER = hex('#7a1d06')

// Building colours.
export const HOUSE_WALLS = ['#e8dcc8', '#d9cbb3', '#cfd8dc', '#e6e1d6', '#c9d6c3', '#e0c9b1', '#d7d0e0', '#efe6d2']
export const HOUSE_ROOFS = ['#7a3b2e', '#5b4a42', '#3f4a54', '#8a5a3c', '#4f5d4a', '#6b3a3a']
export const SHOP_WALLS = ['#b9a58f', '#9fb3c8', '#c8b6a6', '#a7b8a1', '#c2a3a3', '#b8b8b8', '#d1c3a1']

export const STYLE_COLOR: Record<string, string> = {
  school: '#b5653d',
  gym: '#c98f5a',
  hospital: '#eef2f5',
  wing: '#dde6ec',
  firestation: '#a8322a',
  kiosk: '#e7e3da',
  canopy: '#eceef1',
  container: '#e3e8ec',
}

export const CHARRED = hex('#1b1918')
export const SOOT = hex('#3a3330')
export const BURN_TINT = hex('#5a2210')
