const nf = new Intl.NumberFormat('en-US')

export const fmt = (n: number | null | undefined) => (n == null ? '—' : nf.format(Math.round(n)))

export const fmtHa = (ha: number) => `${ha < 10 ? ha.toFixed(1) : nf.format(Math.round(ha))} ha`

export const plural = (n: number, one: string, many = `${one}s`) => `${fmt(n)} ${n === 1 ? one : many}`

export const fmtHour = (h: number) => `${String(((h % 24) + 24) % 24).padStart(2, '0')}:00`

/** Simulated minutes as "1 h 24 min" / "36 min". */
export const fmtMinutes = (m: number) => {
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const r = m % 60
  return r ? `${h} h ${r} min` : `${h} h`
}

export const fmtDate = (epochSeconds: number) =>
  new Date(epochSeconds * 1000).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

export const fmtDistance = (m: number | null) => (m == null ? '—' : m === 0 ? 'on site' : `${m} m`)
