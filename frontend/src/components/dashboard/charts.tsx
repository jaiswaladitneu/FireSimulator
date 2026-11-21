// Small SVG chart kit for the admin dashboard (no chart library).
// Specs follow the team's data-viz rules: bars <= 24px with a 4px rounded data end and a
// square baseline, 2px lines, hairline solid gridlines, ~10% area washes, legends for >= 2
// series, hover tooltips on every mark, and a table view for every chart.
import { useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { Table2, BarChart3 } from 'lucide-react'
import { fmt } from '../../lib/format'
import { SERIES, niceScale, useWidth } from './chartUtils'

const axisNum = (n: number, useCompact: boolean) =>
  useCompact ? `${n / 1000 >= 100 ? Math.round(n / 1000) : Math.round(n / 100) / 10}K` : fmt(n)

/** Path for a column: square at the baseline, rounded data end (top). */
function columnPath(x: number, y: number, w: number, h: number, r = 4) {
  if (h <= 0) return ''
  const rr = Math.min(r, w / 2, h)
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`
}

interface TipState {
  x: number
  y: number
  content: ReactNode
}

function Tooltip({ tip }: { tip: TipState | null }) {
  if (!tip) return null
  return (
    <div className="viz-tip" style={{ left: tip.x, top: tip.y }}>
      {tip.content}
    </div>
  )
}

// ---- chart card with a table-view toggle -------------------------------------------------
export function ChartCard({ title, subtitle, table, legend, children, className = '' }: {
  title: string
  subtitle?: string
  table: { columns: string[]; rows: (string | number)[][] }
  legend?: ReactNode
  children: ReactNode
  className?: string
}) {
  const [asTable, setAsTable] = useState(false)
  return (
    <section className={`viz-card ${className}`}>
      <header className="viz-head">
        <div>
          <h3>{title}</h3>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <button className="icon-btn sm" onClick={() => setAsTable(!asTable)} title={asTable ? 'Show chart' : 'Show as table'} aria-label={asTable ? 'Show chart' : 'Show as table'}>
          {asTable ? <BarChart3 size={14} /> : <Table2 size={14} />}
        </button>
      </header>
      {!asTable && legend}
      {asTable ? (
        <div className="viz-table-wrap">
          <table className="viz-table">
            <thead>
              <tr>{table.columns.map((c) => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i}>{r.map((v, j) => <td key={j} className={typeof v === 'number' ? 'num' : ''}>{typeof v === 'number' ? fmt(v) : v}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        children
      )}
    </section>
  )
}

export function Legend({ items }: { items: { label: string; color: string; shape?: 'rect' | 'line' }[] }) {
  return (
    <div className="viz-legend">
      {items.map((it) => (
        <span key={it.label}>
          <i className={it.shape === 'line' ? 'key-line' : 'key-rect'} style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  )
}

// ---- column chart (one series, optional emphasis on a selected column) ---------------------
export function ColumnChart({ data, unit, selectedId, onSelect, height = 200 }: {
  data: { id: string; label: string; sub?: string; value: number }[]
  unit: string
  selectedId?: string | null
  onSelect?: (id: string) => void
  height?: number
}) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [tip, setTip] = useState<TipState | null>(null)
  const m = { l: 40, r: 10, t: 18, b: 26 }
  const iw = Math.max(10, width - m.l - m.r)
  const ih = height - m.t - m.b
  const { max, step } = niceScale(Math.max(...data.map((d) => d.value), 0))
  const band = data.length ? iw / data.length : iw
  const barW = Math.min(24, band * 0.62)
  const y = (v: number) => m.t + ih - (v / max) * ih
  const ticks: number[] = []
  for (let v = 0; v <= max + 1e-9; v += step) ticks.push(v)
  const useCompact = max >= 10000
  const peak = data.reduce((best, d, i) => (d.value > (data[best]?.value ?? -1) ? i : best), 0)
  const emphasis = selectedId != null && data.some((d) => d.id === selectedId)
  const labelEvery = Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(iw / 46))))

  return (
    <div className="viz" ref={ref} style={{ height }} onPointerLeave={() => setTip(null)}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={`${unit} per incident`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={m.l} x2={m.l + iw} y1={y(t)} y2={y(t)} className={t === 0 ? 'viz-base' : 'viz-grid'} />
              <text x={m.l - 8} y={y(t)} className="viz-tick" textAnchor="end" dominantBaseline="middle">{axisNum(t, useCompact)}</text>
            </g>
          ))}
          {data.map((d, i) => {
            const x = m.l + i * band + (band - barW) / 2
            const top = y(d.value)
            const isSel = d.id === selectedId
            const color = emphasis && !isSel ? SERIES.muted : SERIES.blue
            const showLabel = i === peak || isSel
            return (
              <g key={d.id}>
                <path d={columnPath(x, top, barW, m.t + ih - top)} style={{ fill: color }} className={isSel ? 'viz-mark sel' : 'viz-mark'} />
                {showLabel && d.value > 0 && (
                  <text x={x + barW / 2} y={top - 5} className="viz-value" textAnchor="middle">{fmt(d.value)}</text>
                )}
                {i % labelEvery === 0 && (
                  <text x={x + barW / 2} y={height - 8} className="viz-tick" textAnchor="middle">{d.label}</text>
                )}
                <rect
                  x={m.l + i * band}
                  y={m.t}
                  width={band}
                  height={ih}
                  fill="transparent"
                  tabIndex={0}
                  className="viz-hit"
                  onPointerMove={(e) => {
                    const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
                    setTip({ x: e.clientX - r.left, y: e.clientY - r.top, content: <><strong>{fmt(d.value)}</strong> {unit}<br /><span>{d.sub ?? d.label}</span></> })
                  }}
                  onFocus={() => setTip({ x: x + barW / 2, y: top, content: <><strong>{fmt(d.value)}</strong> {unit}<br /><span>{d.sub ?? d.label}</span></> })}
                  onBlur={() => setTip(null)}
                  onClick={() => onSelect?.(d.id)}
                />
              </g>
            )
          })}
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  )
}

// ---- ranked horizontal bars (one hue, largest first) --------------------------------------
export function RankedBars({ data, unit, emptyText = 'Nothing recorded yet.' }: {
  data: { key: string; label: string; value: number; icon?: ReactNode }[]
  unit: string
  emptyText?: string
}) {
  const [tip, setTip] = useState<TipState | null>(null)
  const rows = [...data].filter((d) => d.value > 0).sort((a, b) => b.value - a.value)
  const max = Math.max(1, ...rows.map((d) => d.value))
  if (!rows.length) return <p className="muted small viz-empty">{emptyText}</p>
  return (
    <div className="ranked" onPointerLeave={() => setTip(null)}>
      {rows.map((d) => (
        <div
          key={d.key}
          className="ranked-row"
          tabIndex={0}
          onPointerMove={(e) => {
            const r = (e.currentTarget.parentElement as HTMLElement).getBoundingClientRect()
            setTip({ x: e.clientX - r.left, y: e.clientY - r.top, content: <><strong>{fmt(d.value)}</strong> {unit}<br /><span>{d.label}</span></> })
          }}
          onFocus={() => setTip({ x: 120, y: 0, content: <><strong>{fmt(d.value)}</strong> {unit}<br /><span>{d.label}</span></> })}
          onBlur={() => setTip(null)}
        >
          <span className="ranked-label">{d.icon}{d.label}</span>
          <span className="ranked-track">
            <span className="ranked-bar" style={{ width: `${(d.value / max) * 100}%` }} />
            <span className="ranked-value">{fmt(d.value)}</span>
          </span>
        </div>
      ))}
      <Tooltip tip={tip} />
    </div>
  )
}

// ---- small multiples: one mini column chart per measure ----------------------------------
export function CompareBars({ measures, series }: {
  measures: { label: string; values: number[]; format?: (v: number) => string }[]
  series: { label: string; color: string; n: number }[]
}) {
  const [tip, setTip] = useState<TipState | null>(null)
  const H = 150
  const m = { t: 22, b: 30 }
  const ih = H - m.t - m.b
  return (
    <div className="multiples" onPointerLeave={() => setTip(null)}>
      {measures.map((ms) => {
        const max = Math.max(1e-9, ...ms.values)
        const f = ms.format ?? ((v: number) => fmt(v))
        return (
          <div className="multiple" key={ms.label}>
            <div className="multiple-title">{ms.label}</div>
            <svg width="100%" height={H} viewBox={`0 0 ${series.length * 70} ${H}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label={ms.label}>
              <line x1={0} x2={series.length * 70} y1={m.t + ih} y2={m.t + ih} className="viz-base" />
              {series.map((s, i) => {
                const v = ms.values[i] ?? 0
                const h = (v / max) * ih
                const x = i * 70 + 23
                return (
                  <g key={s.label}>
                    <path d={columnPath(x, m.t + ih - h, 24, h)} style={{ fill: s.color }} className="viz-mark" />
                    <text x={x + 12} y={m.t + ih - h - 6} className="viz-value" textAnchor="middle">{s.n ? f(v) : '—'}</text>
                    <text x={x + 12} y={H - 10} className="viz-tick" textAnchor="middle">{s.label}</text>
                    <rect
                      x={i * 70}
                      y={0}
                      width={70}
                      height={H}
                      fill="transparent"
                      className="viz-hit"
                      onPointerMove={(e) => {
                        const r = (e.currentTarget.closest('.multiples') as HTMLElement).getBoundingClientRect()
                        setTip({ x: e.clientX - r.left, y: e.clientY - r.top, content: <><strong>{s.n ? f(v) : 'no data'}</strong> {ms.label.toLowerCase()}<br /><span>{s.label} · {s.n} incidents</span></> })
                      }}
                    />
                  </g>
                )
              })}
            </svg>
          </div>
        )
      })}
      <Tooltip tip={tip} />
    </div>
  )
}

// ---- tall segmented bar (one whole, <= 6 parts) -------------------------------------------
export function SegmentedBar({ parts, unit }: { parts: { label: string; value: number; color: string; ink?: string }[]; unit: string }) {
  const [tip, setTip] = useState<TipState | null>(null)
  const total = parts.reduce((s, p) => s + p.value, 0)
  const [ref, width] = useWidth<HTMLDivElement>()
  if (total <= 0) return <p className="muted small viz-empty">Nothing recorded yet.</p>
  return (
    <div className="segbar-wrap" onPointerLeave={() => setTip(null)}>
      <div className="segbar" ref={ref} role="img" aria-label={parts.map((p) => `${p.label} ${fmt(p.value)}`).join(', ')}>
        {parts.filter((p) => p.value > 0).map((p) => {
          const share = p.value / total
          const text = `${Math.round(share * 100)}%`
          const fits = share * width > text.length * 7.5 + 14
          return (
            <span
              key={p.label}
              className="segbar-part"
              style={{ flexGrow: p.value, background: p.color, color: p.ink ?? '#fff' }}
              tabIndex={0}
              onPointerMove={(e) => {
                const r = (e.currentTarget.parentElement!.parentElement as HTMLElement).getBoundingClientRect()
                setTip({ x: e.clientX - r.left, y: e.clientY - r.top, content: <><strong>{fmt(p.value)}</strong> {unit} · {text}<br /><span>{p.label}</span></> })
              }}
            >
              {fits ? text : ''}
            </span>
          )
        })}
      </div>
      <Legend items={parts.map((p) => ({ label: `${p.label} (${fmt(p.value)})`, color: p.color }))} />
      <Tooltip tip={tip} />
    </div>
  )
}

// ---- line chart with crosshair (one shared y-axis) ----------------------------------------
export function LineChart({ x, series, height = 190, xLabel = (t: number) => `${t} min` }: {
  x: number[]
  series: { key: string; label: string; color: string; values: number[]; area?: boolean }[]
  height?: number
  xLabel?: (t: number) => string
}) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const m = { l: 42, r: 12, t: 12, b: 24 }
  const iw = Math.max(10, width - m.l - m.r)
  const ih = height - m.t - m.b
  const n = x.length
  const allMax = Math.max(0, ...series.flatMap((s) => s.values))
  const { max, step } = niceScale(allMax)
  const xMin = x[0] ?? 0
  const xMax = x[n - 1] ?? 1
  const px = (t: number) => m.l + ((t - xMin) / Math.max(1, xMax - xMin)) * iw
  const py = (v: number) => m.t + ih - (v / max) * ih
  const ticks: number[] = []
  for (let v = 0; v <= max + 1e-9; v += step) ticks.push(v)
  const xticks = n ? Array.from({ length: 5 }, (_, i) => Math.round(xMin + ((xMax - xMin) * i) / 4)) : []
  const useCompact = max >= 10000

  const onMove = (e: ReactPointerEvent<SVGRectElement>) => {
    const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
    const t = xMin + ((e.clientX - r.left - m.l) / iw) * (xMax - xMin)
    let best = 0
    for (let i = 1; i < n; i++) if (Math.abs(x[i] - t) < Math.abs(x[best] - t)) best = i
    setHover(best)
  }

  return (
    <div className="viz" ref={ref} style={{ height }} onPointerLeave={() => setHover(null)}>
      {width > 0 && n > 0 && (
        <svg width={width} height={height} role="img" aria-label={series.map((s) => s.label).join(', ')}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={m.l} x2={m.l + iw} y1={py(t)} y2={py(t)} className={t === 0 ? 'viz-base' : 'viz-grid'} />
              <text x={m.l - 8} y={py(t)} className="viz-tick" textAnchor="end" dominantBaseline="middle">{axisNum(t, useCompact)}</text>
            </g>
          ))}
          {xticks.map((t, i) => (
            <text key={i} x={px(t)} y={height - 6} className="viz-tick" textAnchor={i === 0 ? 'start' : i === 4 ? 'end' : 'middle'}>{xLabel(t)}</text>
          ))}
          {series.map((s) => {
            const d = s.values.map((v, i) => `${i ? 'L' : 'M'}${px(x[i]).toFixed(1)},${py(v).toFixed(1)}`).join('')
            return (
              <g key={s.key}>
                {s.area && <path d={`${d}L${px(xMax)},${py(0)}L${px(xMin)},${py(0)}Z`} style={{ fill: s.color }} className="viz-area" />}
                <path d={d} style={{ stroke: s.color }} className="viz-line" />
              </g>
            )
          })}
          {hover != null && (
            <g>
              <line x1={px(x[hover])} x2={px(x[hover])} y1={m.t} y2={m.t + ih} className="viz-cross" />
              {series.map((s) => (
                <circle key={s.key} cx={px(x[hover])} cy={py(s.values[hover])} r={4} style={{ fill: s.color }} className="viz-dot" />
              ))}
            </g>
          )}
          <rect x={m.l} y={m.t} width={iw} height={ih} fill="transparent" onPointerMove={onMove} />
        </svg>
      )}
      {hover != null && width > 0 && (
        <div className="viz-tip" style={{ left: px(x[hover]), top: m.t }}>
          <div className="tip-head">{xLabel(x[hover])}</div>
          {series.map((s) => (
            <div key={s.key} className="tip-row">
              <i className="key-line" style={{ background: s.color }} />
              <strong>{fmt(s.values[hover])}</strong>
              <span>{s.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
