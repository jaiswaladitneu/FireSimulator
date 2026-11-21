import * as THREE from 'three'
import { CELL, LU } from '../api/types'
import {
  ASH,
  CHAR,
  EMBER_HOT,
  EMBER_WARM,
  FIRE_GROUND,
  GROUND,
  IGNITE_GROUND,
  ROAD_CURB,
  ROAD_LINE,
  SMOULDER,
  UNDER_TREE,
  WATER_BANK,
  WET,
  hash2,
  mix,
  type RGB,
} from './palette'

const SMOULDER_TICKS = 6

/**
 * Paints the ground as two textures: colour (land use + fire state) and emissive
 * (glowing fire and smouldering embers). Each cell covers S x S texels so roads get
 * curbs and lane markings. Only cells whose state changed are repainted per tick.
 */
export class GroundPainter {
  readonly colorTex: THREE.DataTexture
  readonly glowTex: THREE.DataTexture
  readonly S: number
  private W: number
  private H: number
  private TW: number
  private base: Float32Array
  // Clamped arrays: noisy colours outside 0..255 clamp instead of wrapping around.
  private color: Uint8ClampedArray
  private glow: Uint8ClampedArray
  private prev: Int8Array
  private burnedAt: Int32Array
  private smouldering = new Set<number>()

  constructor(landuse: number[][], fuel: number[][]) {
    this.H = landuse.length
    this.W = landuse[0].length
    this.S = this.W <= 100 ? 4 : this.W <= 170 ? 3 : 2
    this.TW = this.W * this.S
    const TH = this.H * this.S
    const n = this.TW * TH
    this.base = new Float32Array(n * 3)
    this.color = new Uint8ClampedArray(n * 4)
    this.glow = new Uint8ClampedArray(n * 4)
    this.prev = new Int8Array(this.W * this.H).fill(-1)
    this.burnedAt = new Int32Array(this.W * this.H).fill(-1)
    this.paintBase(landuse, fuel)

    this.colorTex = new THREE.DataTexture(this.color, this.TW, TH, THREE.RGBAFormat)
    this.colorTex.colorSpace = THREE.SRGBColorSpace
    this.glowTex = new THREE.DataTexture(this.glow, this.TW, TH, THREE.RGBAFormat)
    this.glowTex.colorSpace = THREE.SRGBColorSpace
    for (const t of [this.colorTex, this.glowTex]) {
      t.magFilter = THREE.NearestFilter
      t.minFilter = THREE.LinearFilter
      t.generateMipmaps = false
      t.anisotropy = 4
    }
    const empty = landuse.map((row) => row.map(() => CELL.UNBURNED))
    this.update(empty, 0)
  }

  /** Texel index for sub-texel (sx, sy) of cell (x, y); texture row 0 is the south edge. */
  private texel(x: number, y: number, sx: number, sy: number) {
    const tx = x * this.S + sx
    const ty = (this.H - 1 - y) * this.S + (this.S - 1 - sy)
    return ty * this.TW + tx
  }

  private paintBase(lu: number[][], fuel: number[][]) {
    const { W, H, S } = this
    const isRoad = (x: number, y: number) => x >= 0 && y >= 0 && x < W && y < H && lu[y][x] === LU.ROAD
    const isWater = (x: number, y: number) => x < 0 || y < 0 || x >= W || y >= H || lu[y][x] === LU.WATER
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const l = lu[y][x]
        const g = GROUND[l] ?? GROUND[LU.GRASS]
        let c: RGB = g.c
        if ((l === LU.LAWN || l === LU.PARK) && fuel[y][x] === 3) c = UNDER_TREE
        // Road furniture: 2-wide roads get a dashed centre line, edges get a curb.
        const hBand = l === LU.ROAD && isRoad(x, y + 1) && !isRoad(x, y - 1) && !isRoad(x, y + 2)
        const vBand = l === LU.ROAD && isRoad(x + 1, y) && !isRoad(x - 1, y) && !isRoad(x + 2, y)
        for (let sy = 0; sy < S; sy++) {
          for (let sx = 0; sx < S; sx++) {
            const i = this.texel(x, y, sx, sy)
            const tx = x * S + sx
            const ty = y * S + sy
            const nz = (hash2(tx, ty) - 0.5) * 2 * g.noise
            let px: RGB = [c[0] + nz, c[1] + nz, c[2] + nz * 0.7]
            if (l === LU.LAWN && ((tx >> 1) & 1)) px = [px[0] + 4, px[1] + 5, px[2] + 3]
            if (l === LU.ROAD) {
              const edge =
                (sy === 0 && !isRoad(x, y - 1) && y > 0) ||
                (sy === S - 1 && !isRoad(x, y + 1) && y < H - 1) ||
                (sx === 0 && !isRoad(x - 1, y) && x > 0) ||
                (sx === S - 1 && !isRoad(x + 1, y) && x < W - 1)
              if (edge) px = ROAD_CURB
              if (hBand && sy === S - 1 && x % 2 === 0 && sx > 0) px = ROAD_LINE
              if (vBand && sx === S - 1 && y % 2 === 0 && sy > 0) px = ROAD_LINE
            }
            if (l === LU.WATER) {
              const bank =
                (sy === 0 && !isWater(x, y - 1)) || (sy === S - 1 && !isWater(x, y + 1)) ||
                (sx === 0 && !isWater(x - 1, y)) || (sx === S - 1 && !isWater(x + 1, y))
              if (bank) px = mix(px, WATER_BANK, 0.7)
            }
            this.base.set(px, i * 3)
          }
        }
      }
    }
  }

  /** Repaint cells whose fire state changed since the last call. */
  update(grid: number[][], tick: number) {
    const { W, H } = this
    let dirty = false
    const touched: number[] = []
    for (let y = 0; y < H; y++) {
      const row = grid[y]
      for (let x = 0; x < W; x++) {
        const k = y * W + x
        const s = row[x]
        if (s === this.prev[k]) continue
        if (s === CELL.BURNED && this.prev[k] !== -1 && this.prev[k] !== CELL.BURNED) {
          this.burnedAt[k] = tick
          this.smouldering.add(k)
        }
        if (s !== CELL.BURNED) {
          this.burnedAt[k] = -1
          this.smouldering.delete(k)
        }
        this.prev[k] = s
        touched.push(k)
      }
    }
    // Smouldering cells fade every tick, so repaint them too.
    for (const k of this.smouldering) {
      if (tick - this.burnedAt[k] > SMOULDER_TICKS) this.smouldering.delete(k)
      touched.push(k)
    }
    for (const k of touched) {
      const x = k % W
      const y = (k / W) | 0
      this.paintCell(x, y, this.prev[k], tick)
      dirty = true
    }
    if (dirty) {
      this.colorTex.needsUpdate = true
      this.glowTex.needsUpdate = true
    }
  }

  private paintCell(x: number, y: number, state: number, tick: number) {
    const S = this.S
    const k = y * this.W + x
    for (let sy = 0; sy < S; sy++) {
      for (let sx = 0; sx < S; sx++) {
        const i = this.texel(x, y, sx, sy)
        const b: RGB = [this.base[i * 3], this.base[i * 3 + 1], this.base[i * 3 + 2]]
        const n = hash2(x * S + sx + 911, y * S + sy + 37)
        let c: RGB = b
        let e: RGB = [0, 0, 0]
        if (state === CELL.BURNING) {
          c = mix(b, FIRE_GROUND, 0.7)
          e = mix(EMBER_WARM, EMBER_HOT, n)
          const k2 = 0.55 + 0.45 * n
          e = [e[0] * k2, e[1] * k2, e[2] * k2]
        } else if (state === CELL.IGNITING) {
          c = mix(b, IGNITE_GROUND, 0.55)
          e = [EMBER_WARM[0] * 0.45 * n, EMBER_WARM[1] * 0.45 * n, EMBER_WARM[2] * 0.45 * n]
        } else if (state === CELL.BURNED) {
          c = n > 0.86 ? ASH : mix(CHAR, ASH, n * 0.25)
          const age = this.burnedAt[k] < 0 ? 99 : tick - this.burnedAt[k]
          if (age <= SMOULDER_TICKS && n > 0.55) {
            const f = (1 - age / (SMOULDER_TICKS + 1)) * (n - 0.55) * 2
            e = [SMOULDER[0] * f, SMOULDER[1] * f, SMOULDER[2] * f]
          }
        } else if (state === CELL.SUPPRESSED) {
          c = mix(b, WET, 0.55)
        }
        const o = i * 4
        this.color[o] = c[0]
        this.color[o + 1] = c[1]
        this.color[o + 2] = c[2]
        this.color[o + 3] = 255
        this.glow[o] = e[0]
        this.glow[o + 1] = e[1]
        this.glow[o + 2] = e[2]
        this.glow[o + 3] = 255
      }
    }
  }

  dispose() {
    this.colorTex.dispose()
    this.glowTex.dispose()
  }
}
