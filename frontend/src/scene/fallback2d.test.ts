import { describe, it, expect } from 'vitest'
import { cellColor, drawGrid, hasWebGL, type Ctx2D } from './fallback2d'

describe('2-D fallback cell colours', () => {
  it('uses fire colours for burning, burned and suppressed cells', () => {
    expect(cellColor(2, 8)).toBe('rgb(255, 77, 13)') // burning overrides land use
    expect(cellColor(3, 3)).toBe('rgb(36, 32, 29)') // burned -> char
    expect(cellColor(4, 3)).toBe('rgb(44, 106, 163)') // suppressed -> wet
  })

  it('uses the land-use ground colour for unburned cells', () => {
    expect(cellColor(0, 0)).toBe('rgb(42, 106, 138)') // water #2a6a8a
    expect(cellColor(0, 8)).toBe('rgb(74, 77, 82)') // house footprint #4a4d52
  })

  it('falls back to grass for an unknown land-use code', () => {
    expect(cellColor(0, 999)).toBe(cellColor(0, 3))
  })
})

describe('2-D fallback grid drawing', () => {
  it('fills one square per cell at the right position and colour', () => {
    const calls: Array<[string, number, number, number, number]> = []
    const ctx: Ctx2D = {
      fillStyle: '',
      fillRect: (x, y, w, h) => calls.push([ctx.fillStyle, x, y, w, h]),
    }
    drawGrid(ctx, [[2, 0]], [[8, 0]], 10)
    expect(calls).toEqual([
      ['rgb(255, 77, 13)', 0, 0, 10, 10], // burning cell
      ['rgb(42, 106, 138)', 10, 0, 10, 10], // water cell at x=1
    ])
  })
})

describe('WebGL detection', () => {
  const docWith = (getContext: () => unknown) =>
    ({ createElement: () => ({ getContext }) }) as unknown as Pick<Document, 'createElement'>

  it('is true when a webgl context is available', () => {
    expect(hasWebGL(docWith(() => ({})))).toBe(true)
  })

  it('is false when no context is available', () => {
    expect(hasWebGL(docWith(() => null))).toBe(false)
  })

  it('is false when creating a context throws', () => {
    expect(
      hasWebGL(docWith(() => {
        throw new Error('no canvas')
      })),
    ).toBe(false)
  })
})
