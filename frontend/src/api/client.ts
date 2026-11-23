import type {
  IncidentBrief,
  IncidentFull,
  MapData,
  ScenarioParams,
  SimPayload,
} from './types'

/** API base: the Vite proxy by default, or VITE_API_URL (e.g. http://127.0.0.1:8000). */
const BASE: string = import.meta.env.VITE_API_URL ?? '/api'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the simulation API. Is it running on port 8000?')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  health: () => request<{ status: string }>('/health'),

  createScenario: (params: ScenarioParams) => post<{ id: string; name: string }>('/scenarios', params),
  scenarios: () => request<{ id: string; name: string }[]>('/scenarios'),
  state: () => request<SimPayload>('/simulation/state'),
  map: () => request<MapData>('/simulation/map'),

  play: () => post<SimPayload>('/simulation/play'),
  pause: () => post<SimPayload>('/simulation/pause'),
  step: () => post<SimPayload>('/simulation/step'),
  tick: () => post<SimPayload>('/simulation/tick'),
  reset: () => post<SimPayload>('/simulation/reset'),
  speed: (speed: number) => post<SimPayload>('/simulation/speed', { speed }),
  end: () => post<SimPayload>('/simulation/end'),

  ignite: (x: number, y: number) => post<SimPayload>('/simulation/ignite', { x, y }),
  dispatch: (assetId: number) => post<SimPayload>('/simulation/dispatch', { asset_id: assetId }),
  autoDispatch: (enabled: boolean) => post<SimPayload>('/simulation/auto-dispatch', { enabled }),

  incidents: () => request<IncidentBrief[]>('/incidents'),
  incident: (id: string) => request<IncidentFull>(`/incidents/${encodeURIComponent(id)}`),
  deleteIncident: (id: string) =>
    request<void>(`/incidents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  clearIncidents: () => request<{ deleted: number }>('/incidents', { method: 'DELETE' }),
  simulateIncidents: (count: number, size = 80) =>
    post<IncidentBrief[]>('/incidents/simulate', { count, size }),
}
