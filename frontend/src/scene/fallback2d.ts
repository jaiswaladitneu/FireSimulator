/** 2-D canvas fallback renderer for the town grid (issue #37).
 *
 * Used when WebGL is unavailable (or forced on), this draws the same grid the 3-D view shows
 * as a flat top-down map: one filled square per cell, coloured by fire state over the
 * land-use ground colour. The drawing helpers are pure so they can be unit-tested without a
 * real canvas.
 */
import { GROUND, type RGB } from './palette'

/** Minimal 2-D context surface the renderer needs (a real CanvasRenderingContext2D fits). */
export interface Ctx2D {
  fillStyle: string
  fillRect: (x: number, y: number, w: number, h: number) => void
}

const toCss = ([r, g, b]: RGB): string => `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`

// Fire-state colours (grid codes 1..4); unburned (0) shows the land-use ground colour.
const FIRE: Record<number, RGB> = {
  1: [0xff, 0x8a, 0x1e], // igniting -> ember hot
  2: [0xff, 0x4d, 0x0d], // burning  -> ember warm
  3: [0x24, 0x20, 0x1d], // burned   -> char
  4: [0x2c, 0x6a, 0xa3], // suppressed -> wet
}

const DEFAULT_GROUND = 3 // wild grass, when a land-use code is missing

/** CSS colour for a grid cell from its fire state (0..4) and land-use code. */
export function cellColor(state: number, landuse: number): string {
  const fire = FIRE[state]
  if (fire) return toCss(fire)
  return toCss((GROUND[landuse] ?? GROUND[DEFAULT_GROUND]).c)
}

/** Draw the grid onto a 2-D context: one ``cellPx`` square per cell. */
export function drawGrid(
  ctx: Ctx2D,
  grid: number[][],
  landuse: number[][],
  cellPx: number,
): void {
  for (let y = 0; y < grid.length; y++) {
    const row = grid[y]
    const luRow = landuse[y] ?? []
    for (let x = 0; x < row.length; x++) {
      ctx.fillStyle = cellColor(row[x], luRow[x] ?? DEFAULT_GROUND)
      ctx.fillRect(x * cellPx, y * cellPx, cellPx, cellPx)
    }
  }
}

/** True if the browser can create a WebGL context (so the 3-D view will work). */
export function hasWebGL(doc: Pick<Document, 'createElement'> = document): boolean {
  try {
    const canvas = doc.createElement('canvas') as HTMLCanvasElement
    return Boolean(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
  } catch {
    return false
  }
}
