import { describe, it, expect } from 'vitest'
import {
  fmt,
  fmtHa,
  plural,
  fmtHour,
  fmtMinutes,
  fmtDistance,
} from './format'

describe('Number formatting', () => {
  it('formats large numbers', () => {
    expect(fmt(1200)).toBe('1,200')
  })

  it('rounds decimal numbers', () => {
    expect(fmt(12.7)).toBe('13')
  })

  it('handles missing values', () => {
    expect(fmt(null)).toBe('—')
    expect(fmt(undefined)).toBe('—')
  })
})

describe('Area formatting', () => {
  it('formats small burned areas', () => {
    expect(fmtHa(5.24)).toBe('5.2 ha')
  })

  it('formats large burned areas', () => {
    expect(fmtHa(1250)).toBe('1,250 ha')
  })
})

describe('Plural formatting', () => {
  it('handles singular values', () => {
    expect(plural(1, 'building')).toBe('1 building')
  })

  it('handles plural values', () => {
    expect(plural(5, 'building')).toBe('5 buildings')
  })
})

describe('Time formatting', () => {
  it('formats hours correctly', () => {
    expect(fmtHour(8)).toBe('08:00')
  })

  it('handles midnight rollover', () => {
    expect(fmtHour(24)).toBe('00:00')
  })

  it('handles negative hours', () => {
    expect(fmtHour(-1)).toBe('23:00')
  })

  it('formats minutes below one hour', () => {
    expect(fmtMinutes(36)).toBe('36 min')
  })

  it('formats hours and minutes', () => {
    expect(fmtMinutes(84)).toBe('1 h 24 min')
  })

  it('formats exact hours', () => {
    expect(fmtMinutes(120)).toBe('2 h')
  })
})

describe('Distance formatting', () => {
  it('handles missing distance', () => {
    expect(fmtDistance(null)).toBe('—')
  })

  it('handles on-site crews', () => {
    expect(fmtDistance(0)).toBe('on site')
  })

  it('formats distance in meters', () => {
    expect(fmtDistance(250)).toBe('250 m')
  })
})
