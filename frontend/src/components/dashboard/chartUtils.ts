import { useLayoutEffect, useRef, useState } from 'react'

/** Chart colours (CSS tokens, validated against the dashboard surface). */
export const SERIES = {
  blue: 'var(--series-1)',
  orange: 'var(--series-2)',
  aqua: 'var(--series-3)',
  muted: 'var(--series-muted)',
} as const

/** Width of an element, kept up to date with a ResizeObserver. */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => setWidth(entries[0].contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}

/** Clean axis maximum and step for counts (integers). */
export function niceScale(max: number, ticks = 4) {
  if (max <= 0) return { max: ticks, step: 1 }
  const raw = max / ticks
  const mag = 10 ** Math.floor(Math.log10(raw))
  const n = raw / mag
  let step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag
  step = Math.max(1, Math.round(step))
  return { max: Math.ceil(max / step) * step, step }
}
