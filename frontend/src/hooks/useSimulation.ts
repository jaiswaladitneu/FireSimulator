import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api/client'
import { openFeed } from '../api/liveFeed'
import type { MapData, ScenarioParams, SimPayload } from '../api/types'

export const SPEEDS = [0.5, 1, 2, 4, 8] as const

export interface Simulation {
  map: MapData | null
  sim: SimPayload | null
  online: boolean | null
  error: string | null
  busy: boolean
  speed: number
  clearError: () => void
  create: (params: ScenarioParams) => Promise<boolean>
  play: () => void
  pause: () => void
  step: () => void
  reset: () => void
  end: () => void
  setSpeed: (speed: number) => void
  ignite: (x: number, y: number) => void
  dispatch: (assetId: number) => void
  setAutoDispatch: (enabled: boolean) => void
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e))

/** Live connection to the simulation API: state, playback loop and commands. */
export function useSimulation(): Simulation {
  const [map, setMap] = useState<MapData | null>(null)
  const [sim, setSim] = useState<SimPayload | null>(null)
  const [online, setOnline] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [speed, setSpeedState] = useState<number>(2)
  const speedRef = useRef(speed)
  useEffect(() => {
    speedRef.current = speed   // the playback loop reads the latest speed without restarting
  }, [speed])

  // Resume a session that already exists on the server (e.g. after a page reload).
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        // Only ask for the live state if a scenario exists (avoids a 409 on a fresh API).
        const existing = await api.scenarios()
        if (!existing.length) return
        const s = await api.state()
        const m = await api.map()
        if (!alive) return
        setMap(m)
        setSim(s)
        if (s.speed && (SPEEDS as readonly number[]).includes(s.speed)) setSpeedState(s.speed)
      } catch {
        /* no active scenario yet */
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  // API health indicator.
  useEffect(() => {
    let alive = true
    const check = () =>
      api.health().then(
        () => alive && setOnline(true),
        () => alive && setOnline(false),
      )
    check()
    const id = window.setInterval(check, 8000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [])

  // Playback while running: prefer the server-pushed WebSocket feed (the server advances the
  // run and streams each frame); fall back to driving one tick per 1/speed seconds over HTTP
  // if the socket cannot be opened.
  const running = sim?.state === 'running'
  useEffect(() => {
    if (!running) return
    let cancelled = false
    let httpStarted = false
    let timer = 0
    let feed: { close: () => void } | null = null

    const httpLoop = async () => {
      const started = performance.now()
      try {
        const next = await api.tick()
        if (cancelled) return
        setSim(next)
        if (next.state !== 'running') return
      } catch (e) {
        if (!cancelled) setError(message(e))
        return
      }
      const wait = Math.max(0, 1000 / speedRef.current - (performance.now() - started))
      timer = window.setTimeout(httpLoop, wait)
    }

    const startHttp = () => {
      if (httpStarted || cancelled) return
      httpStarted = true
      feed?.close() // stop the socket; HTTP ticking drives from here
      timer = window.setTimeout(httpLoop, 1000 / speedRef.current)
    }

    feed = openFeed((next) => {
      if (!cancelled && !httpStarted) setSim(next)
    }, startHttp)

    return () => {
      cancelled = true
      feed?.close()
      window.clearTimeout(timer)
    }
  }, [running])

  const run = useCallback(async (action: () => Promise<SimPayload>) => {
    try {
      setSim(await action())
      setError(null)
    } catch (e) {
      setError(message(e))
    }
  }, [])

  const create = useCallback(async (params: ScenarioParams) => {
    setBusy(true)
    try {
      await api.createScenario(params)
      const [m, s] = await Promise.all([api.map(), api.state()])
      setMap(m)
      setSim(s)
      setError(null)
      api.speed(speedRef.current).catch(() => undefined)
      return true
    } catch (e) {
      setError(e instanceof ApiError && e.status === 422 ? `Invalid scenario: ${e.message}` : message(e))
      return false
    } finally {
      setBusy(false)
    }
  }, [])

  const setSpeed = useCallback((value: number) => {
    setSpeedState(value)
    api.speed(value).catch(() => undefined) // keep the server's value in sync; not critical
  }, [])

  return {
    map,
    sim,
    online,
    error,
    busy,
    speed,
    clearError: () => setError(null),
    create,
    play: () => run(api.play),
    pause: () => run(api.pause),
    step: () => run(api.step),
    reset: () => run(api.reset),
    end: () => run(api.end),
    setSpeed,
    ignite: (x, y) => run(() => api.ignite(x, y)),
    dispatch: (id) => run(() => api.dispatch(id)),
    setAutoDispatch: (enabled) => run(() => api.autoDispatch(enabled)),
  }
}
