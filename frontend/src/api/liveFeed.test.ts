import { describe, it, expect } from 'vitest'
import { feedUrl } from './liveFeed'

describe('live feed WebSocket URL', () => {
  it('derives a ws:// URL from a relative base on an http page', () => {
    expect(feedUrl('/api', { protocol: 'http:', host: 'localhost:5173' })).toBe(
      'ws://localhost:5173/api/simulation/ws',
    )
  })

  it('uses wss:// on an https page', () => {
    expect(feedUrl('/api', { protocol: 'https:', host: 'app.example.com' })).toBe(
      'wss://app.example.com/api/simulation/ws',
    )
  })

  it('converts an absolute http base to a ws:// URL, ignoring the page origin', () => {
    expect(feedUrl('http://127.0.0.1:8000', { protocol: 'https:', host: 'ignored' })).toBe(
      'ws://127.0.0.1:8000/simulation/ws',
    )
  })

  it('converts an absolute https base to a wss:// URL', () => {
    expect(feedUrl('https://api.example.com', { protocol: 'http:', host: 'ignored' })).toBe(
      'wss://api.example.com/simulation/ws',
    )
  })
})
