import { describe, it, expect } from 'vitest'
import { niceScale } from './chartUtils'

describe('Chart axis scale', () => {
  it('uses a default axis when there is no data', () => {
    expect(niceScale(0)).toEqual({ max: 4, step: 1 })
    expect(niceScale(-5)).toEqual({ max: 4, step: 1 })
  })

  it('never uses a step below 1 for small counts', () => {
    expect(niceScale(3)).toEqual({ max: 3, step: 1 })
  })

  it('rounds the step to 1, 2, 2.5, 5 or 10 times a power of ten', () => {
    expect(niceScale(37)).toEqual({ max: 40, step: 10 })
    expect(niceScale(100)).toEqual({ max: 100, step: 25 })
    expect(niceScale(1234)).toEqual({ max: 1500, step: 500 })
  })

  it('always covers the largest value', () => {
    for (const max of [1, 7, 19, 55, 99, 101, 999, 4321]) {
      const s = niceScale(max)
      expect(s.max).toBeGreaterThanOrEqual(max)
      expect(s.max % s.step).toBe(0)
    }
  })
})
