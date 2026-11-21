import { Download, FlaskConical, HeartCrack, Radar, RefreshCw, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { AssetKind, IncidentBrief, IncidentFull } from '../../api/types'
import type { Simulation } from '../../hooks/useSimulation'
import { fmt, fmtHa, fmtMinutes } from '../../lib/format'
import { KIND_META } from '../../lib/kinds'
import { aggregate, applyFilters, toCsv, type Filters } from '../../lib/stats'
import { ChartCard, ColumnChart, CompareBars, RankedBars, SegmentedBar } from './charts'
import { SERIES } from './chartUtils'
import { IncidentDetail } from './IncidentDetail'
import { IncidentTable } from './IncidentTable'

interface Props {
  sim: Simulation
  onOpenCommand: () => void
}

const RANGES = [
  { key: 'all', label: 'All time' },
  { key: '24h', label: 'Last 24 h' },
  { key: '7d', label: 'Last 7 days' },
] as const
const SOURCES = [
  { key: 'all', label: 'All sources' },
  { key: 'live', label: 'Command center' },
  { key: 'simulated', label: 'Simulated' },
] as const
const RESPONSES = [
  { key: 'all', label: 'Any response' },
  { key: 'auto', label: 'Auto-dispatch' },
  { key: 'manual', label: 'Manual' },
] as const

function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T
  options: readonly { key: T; label: string }[]
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.key} className={value === o.key ? 'on' : ''} onClick={() => onChange(o.key)}>{o.label}</button>
      ))}
    </div>
  )
}

/** Admin dashboard: history and analytics of every recorded incident. */
export function AdminDashboard({ sim, onOpenCommand }: Props) {
  const [list, setList] = useState<IncidentBrief[] | null>(null)
  const [refetching, setRefetching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<Filters>({ range: 'all', source: 'all', response: 'all' })
  const [selected, setSelected] = useState<string | null>(null)
  const [batch, setBatch] = useState(6)
  const [simulating, setSimulating] = useState(false)

  // Fetch the history; state is only set after the request settles.
  const fetchList = useCallback(async () => {
    try {
      const incidents = await api.incidents()
      setList(incidents)
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  // User-triggered reloads keep the previous render at reduced opacity meanwhile.
  const load = useCallback(async () => {
    setRefetching(true)
    await fetchList()
    setRefetching(false)
  }, [fetchList])

  // Load on open, and again whenever a live incident gets recorded.
  const recorded = sim.sim?.incident_id
  useEffect(() => {
    let alive = true
    api.incidents().then(
      (incidents) => {
        if (!alive) return
        setList(incidents)
        setError(null)
      },
      (e: Error) => alive && setError(e.message),
    )
    return () => {
      alive = false
    }
  }, [recorded])

  const filtered = useMemo(() => (list ? applyFilters(list, filters) : []), [list, filters])
  const agg = useMemo(() => aggregate(filtered), [filtered])
  const chrono = useMemo(() => [...filtered].sort((a, b) => a.ended_at - b.ended_at), [filtered])

  const simulate = async () => {
    setSimulating(true)
    try {
      await api.simulateIncidents(batch, 80)
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSimulating(false)
    }
  }

  const exportCsv = () => {
    const blob = new Blob([toCsv(filtered)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `firesim-incidents-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const clearAll = async () => {
    if (!window.confirm(`Delete all ${list?.length ?? 0} recorded incidents? This cannot be undone.`)) return
    await api.clearIncidents().catch((e: Error) => setError(e.message))
    setSelected(null)
    await load()
  }

  const remove = async (id: string) => {
    if (!window.confirm('Delete this incident from the history?')) return
    await api.deleteIncident(id).catch((e: Error) => setError(e.message))
    setSelected(null)
    await load()
  }

  const replay = async (rec: IncidentFull) => {
    const ok = await sim.create({
      name: `${rec.name} (replay)`,
      width: rec.params.width,
      height: rec.params.height,
      seed: rec.params.seed,
      wind_direction: rec.params.wind_direction,
      wind_speed: rec.params.wind_speed,
      map_type: 'city',
      hour: rec.params.hour,
      crews: rec.params.crews,
      auto_dispatch: rec.params.auto_dispatch,
      ignition_points: rec.params.ignition_points.map(({ x, y }) => ({ x, y })),
    })
    if (ok) onOpenCommand()
  }

  const live = sim.sim && sim.sim.map_type === 'city' && sim.sim.state !== 'completed' && sim.sim.tick > 0 ? sim.sim : null
  const unaffected = Math.max(0, agg.population - agg.evacuated - agg.casualties)
  const buildingKinds: AssetKind[] = ['house', 'commercial', 'school', 'hospital', 'fuel_station', 'battery_storage', 'fire_station']
  const placeKinds: AssetKind[] = ['house', 'hospital', 'school', 'commercial', 'fuel_station', 'battery_storage', 'fire_station', 'park', 'road']
  const icon = (k: AssetKind) => {
    const I = KIND_META[k].icon
    return <I size={13} />
  }

  return (
    <div className="dashboard">
      <header className="dash-head">
        <div>
          <h1>Incident analytics</h1>
          <p className="muted">Every finished incident from the command center and from simulated batches. Casualty figures are model estimates from a training simulation.</p>
        </div>
        <div className="dash-actions">
          <label className="inline-select">
            <span className="sr-only">Number of incidents to simulate</span>
            <select value={batch} onChange={(e) => setBatch(Number(e.target.value))} disabled={simulating}>
              {[3, 6, 10].map((n) => <option key={n} value={n}>{n} incidents</option>)}
            </select>
          </label>
          <button className="btn btn-primary" onClick={simulate} disabled={simulating}>
            <FlaskConical size={14} /> {simulating ? 'Simulating…' : 'Simulate'}
          </button>
          <button className="btn btn-ghost" onClick={exportCsv} disabled={!filtered.length}><Download size={14} /> Export CSV</button>
          <button className="icon-btn" onClick={() => void load()} title="Refresh" aria-label="Refresh"><RefreshCw size={15} /></button>
          <button className="icon-btn danger" onClick={clearAll} disabled={!list?.length} title="Clear history" aria-label="Clear history"><Trash2 size={15} /></button>
        </div>
      </header>

      {live && (
        <div className="live-card">
          <span className="live-dot" />
          <div className="grow">
            <strong>Live incident: {live.scenario.name}</strong>
            <span className="muted"> · {live.city?.clock} · {fmt(live.city?.population.at_risk ?? 0)} lives at risk · {fmt(live.city?.buildings.burning ?? 0)} buildings on fire</span>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onOpenCommand}><Radar size={14} /> Open command center</button>
        </div>
      )}

      <div className="filter-row">
        <Segmented label="Time range" value={filters.range} options={RANGES} onChange={(range) => setFilters({ ...filters, range })} />
        <Segmented label="Source" value={filters.source} options={SOURCES} onChange={(source) => setFilters({ ...filters, source })} />
        <Segmented label="Response" value={filters.response} options={RESPONSES} onChange={(response) => setFilters({ ...filters, response })} />
        <span className="muted small">{filtered.length} of {list?.length ?? 0} incidents</span>
      </div>

      {error && <div className="toast-inline" role="alert">{error}</div>}

      {list && list.length === 0 && (
        <div className="dash-empty">
          <HeartCrack size={26} className="muted" />
          <h3>No incidents recorded yet</h3>
          <p className="muted">Incidents are recorded when a city fire burns out or when you press <strong>End incident</strong> in the command center. You can also run a batch of simulated incidents with varied wind, time of day and crews.</p>
          <div className="row gap center">
            <button className="btn btn-primary" onClick={simulate} disabled={simulating}><FlaskConical size={14} /> {simulating ? 'Simulating…' : `Simulate ${batch} incidents`}</button>
            <button className="btn btn-ghost" onClick={onOpenCommand}><Radar size={14} /> Go to command center</button>
          </div>
        </div>
      )}

      {list && list.length > 0 && (
        <div className={`dash-grid ${refetching || simulating ? 'refetching' : ''}`}>
          <section className="hero-row">
            <div className="hero">
              <span className="hero-label">Lives lost (estimated)</span>
              <span className="hero-value">{fmt(agg.casualties)}</span>
              <span className="muted small">across {fmt(agg.incidents)} incidents · {fmt(agg.evacuated)} people evacuated</span>
            </div>
            <div className="kpis">
              <div className="kpi"><span>Incidents</span><strong>{fmt(agg.incidents)}</strong></div>
              <div className="kpi"><span>People evacuated</span><strong>{fmt(agg.evacuated)}</strong></div>
              <div className="kpi"><span>Buildings destroyed</span><strong>{fmt(agg.destroyed)}</strong></div>
              <div className="kpi"><span>Area burned</span><strong>{fmtHa(agg.areaHa)}</strong></div>
              <div className="kpi"><span>Highest lives at risk</span><strong>{fmt(agg.peakAtRisk)}</strong></div>
              <div className="kpi"><span>Average duration</span><strong>{fmtMinutes(Math.round(agg.avgMinutes))}</strong></div>
              <div className="kpi"><span>Fuel-station explosions</span><strong>{fmt(agg.explosions)}</strong></div>
              <div className="kpi"><span>Battery-site fires</span><strong>{fmt(agg.batteryFires)}</strong></div>
            </div>
          </section>

          <div className="dash-charts">
            <ChartCard
              className="span-2"
              title="Casualties (est.) per incident"
              subtitle="Oldest to newest · click a column for that incident's details"
              table={{ columns: ['Incident', 'Ended', 'Casualties (est.)'], rows: chrono.map((r) => [r.name, new Date(r.ended_at * 1000).toLocaleString(), r.summary.population.casualties]) }}
            >
              <ColumnChart
                unit="casualties (est.)"
                selectedId={selected}
                onSelect={setSelected}
                data={chrono.map((r, i) => ({ id: r.id, label: `#${i + 1}`, sub: r.name, value: r.summary.population.casualties }))}
              />
            </ChartCard>

            <ChartCard
              title="What happened to the people"
              subtitle="Everyone in town at the start of each incident"
              table={{ columns: ['Outcome', 'People'], rows: [['Evacuated', agg.evacuated], ['Casualties (est.)', agg.casualties], ['Not reached by the fire', unaffected]] }}
            >
              <SegmentedBar
                unit="people"
                parts={[
                  { label: 'Evacuated', value: agg.evacuated, color: SERIES.aqua },
                  { label: 'Casualties (est.)', value: agg.casualties, color: SERIES.orange },
                  { label: 'Not reached by the fire', value: unaffected, color: SERIES.muted },
                ]}
              />
            </ChartCard>

            <ChartCard
              title="Buildings destroyed by type"
              subtitle="All filtered incidents"
              table={{ columns: ['Type', 'Destroyed'], rows: buildingKinds.map((k) => [KIND_META[k].plural, agg.destroyedByKind[k] ?? 0]) }}
            >
              <RankedBars unit="destroyed" emptyText="No buildings destroyed." data={buildingKinds.map((k) => ({ key: k, label: KIND_META[k].plural, value: agg.destroyedByKind[k] ?? 0, icon: icon(k) }))} />
            </ChartCard>

            <ChartCard
              title="Casualties (est.) by place"
              subtitle="Where people were when they were harmed"
              table={{ columns: ['Place', 'Casualties (est.)'], rows: placeKinds.map((k) => [KIND_META[k].plural, agg.casualtiesByKind[k] ?? 0]) }}
            >
              <RankedBars unit="casualties (est.)" emptyText="No casualties recorded." data={placeKinds.map((k) => ({ key: k, label: KIND_META[k].plural, value: agg.casualtiesByKind[k] ?? 0, icon: icon(k) }))} />
            </ChartCard>

            <ChartCard
              title="Does fast response help?"
              subtitle="Average per incident, automatic dispatch vs manual dispatch"
              legend={<div className="viz-legend"><span><i className="key-rect" style={{ background: SERIES.blue }} />Auto-dispatch ({agg.response.auto.n})</span><span><i className="key-rect" style={{ background: SERIES.orange }} />Manual ({agg.response.manual.n})</span></div>}
              table={{
                columns: ['Measure (average per incident)', 'Auto-dispatch', 'Manual'],
                rows: [
                  ['Casualties (est.)', agg.response.auto.casualties.toFixed(1), agg.response.manual.casualties.toFixed(1)],
                  ['Buildings destroyed', agg.response.auto.destroyed.toFixed(1), agg.response.manual.destroyed.toFixed(1)],
                  ['Area burned (ha)', agg.response.auto.areaHa.toFixed(1), agg.response.manual.areaHa.toFixed(1)],
                ],
              }}
            >
              <CompareBars
                series={[
                  { label: 'Auto', color: SERIES.blue, n: agg.response.auto.n },
                  { label: 'Manual', color: SERIES.orange, n: agg.response.manual.n },
                ]}
                measures={[
                  { label: 'Casualties (est.)', values: [agg.response.auto.casualties, agg.response.manual.casualties], format: (v) => v.toFixed(1) },
                  { label: 'Buildings destroyed', values: [agg.response.auto.destroyed, agg.response.manual.destroyed], format: (v) => v.toFixed(1) },
                  { label: 'Area burned (ha)', values: [agg.response.auto.areaHa, agg.response.manual.areaHa], format: (v) => v.toFixed(1) },
                ]}
              />
            </ChartCard>
          </div>

          <IncidentTable list={filtered} selectedId={selected} onSelect={setSelected} />
        </div>
      )}

      {selected && <IncidentDetail key={selected} id={selected} onClose={() => setSelected(null)} onReplay={replay} onDelete={remove} />}
    </div>
  )
}
