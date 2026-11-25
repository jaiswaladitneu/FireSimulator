import { describe, it, expect } from 'vitest'
import { compassName, KIND_ORDER, levelClass, severityClass, statusClass } from './kinds'

describe('Wind direction compass names', () => {
  it('names the eight main directions', () => {
    expect([0, 45, 90, 135, 180, 225, 270, 315].map(compassName)).toEqual(['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'])
  })

  it('rounds to the nearest direction', () => {
    expect(compassName(20)).toBe('N')
    expect(compassName(23)).toBe('NE')
    expect(compassName(350)).toBe('N')
  })

  it('wraps angles of 360 degrees or more', () => {
    expect(compassName(360)).toBe('N')
    expect(compassName(450)).toBe('E')
  })

  it('handles negative angles', () => {
    expect(compassName(-90)).toBe('W')
  })
})

describe('Kinds of place', () => {
  it('lists places in life-safety order: hospitals and schools first, roads last', () => {
    expect(KIND_ORDER[0]).toBe('hospital')
    expect(KIND_ORDER[1]).toBe('school')
    expect(KIND_ORDER[KIND_ORDER.length - 1]).toBe('road')
    expect(KIND_ORDER).toHaveLength(9)
  })
})

describe('CSS class helpers', () => {
  it('prefixes status, priority level and severity', () => {
    expect(statusClass('burning')).toBe('st-burning')
    expect(levelClass('critical')).toBe('lv-critical')
    expect(severityClass('warning')).toBe('sv-warning')
  })
})
