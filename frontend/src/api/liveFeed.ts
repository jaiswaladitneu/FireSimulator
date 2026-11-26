/** WebSocket live feed for the simulation state (issue #36).
 *
 * The command center opens this feed while a run is playing: the server advances the
 * simulation and pushes each frame, so the UI shows the fire live without polling. If the
 * socket cannot be opened the caller falls back to driving ticks over HTTP.
 */
import type { SimPayload } from './types'

/** API base: the Vite proxy by default, or VITE_API_URL (kept in step with the REST client). */
const BASE: string = import.meta.env.VITE_API_URL ?? '/api'

/** Minimal view of ``window.location`` the feed URL needs (injectable for tests). */
export interface Loc {
  protocol: string
  host: string
}

/**
 * Build the WebSocket URL for the live feed from the REST ``base``.
 *
 * An absolute ``http(s)://host`` base becomes ``ws(s)://host/simulation/ws``; a relative base
 * such as ``/api`` is resolved against the page's origin, using ``wss`` on an https page.
 */
export function feedUrl(base: string = BASE, loc: Loc = window.location): string {
  const path = '/simulation/ws'
  if (/^https?:\/\//.test(base)) return base.replace(/^http/, 'ws') + path
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${loc.host}${base}${path}`
}

/** A handle to an open live feed; call ``close`` to stop it. */
export interface Feed {
  close: () => void
}

/**
 * Open the live feed and deliver each frame to ``onFrame``.
 *
 * ``onError`` is called once if the socket fails to open or closes unexpectedly, so the
 * caller can fall back to HTTP; a close triggered by ``close()`` does not call it.
 */
export function openFeed(
  onFrame: (sim: SimPayload) => void,
  onError: () => void,
  url: string = feedUrl(),
): Feed {
  let closed = false
  let ws: WebSocket
  try {
    ws = new WebSocket(url)
  } catch {
    if (!closed) onError()
    return { close: () => { closed = true } }
  }
  ws.onmessage = (ev) => {
    if (closed) return
    try {
      onFrame(JSON.parse(ev.data) as SimPayload)
    } catch {
      /* ignore a malformed frame */
    }
  }
  ws.onerror = () => {
    if (!closed) onError()
  }
  ws.onclose = () => {
    if (!closed) onError()
  }
  return {
    close: () => {
      closed = true
      try {
        ws.close()
      } catch {
        /* already closing */
      }
    },
  }
}
