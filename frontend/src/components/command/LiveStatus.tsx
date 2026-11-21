import { Activity } from 'lucide-react'
import type { AssetKind, CityState, KindStats } from '../../api/types'
import { fmt } from '../../lib/format'
import { KIND_META, KIND_ORDER } from '../../lib/kinds'

interface Props {
  city: CityState | null
}

const SEGMENTS: { key: keyof KindStats; cls: string; label: string }[] = [
  { key: 'burning', cls: 'seg-burning', label: 'on fire' },
  { key: 'blocked', cls: 'seg-blocked', label: 'blocked' },
  { key: 'threatened', cls: 'seg-threatened', label: 'threatened' },
  { key: 'damaged', cls: 'seg-damaged', label: 'damaged' },
  { key: 'destroyed', cls: 'seg-destroyed', label: 'destroyed' },
  { key: 'safe', cls: 'seg-safe', label: 'safe' },
]

function KindRow({ kind, s }: { kind: AssetKind; s: KindStats }) {
  const meta = KIND_META[kind]
  const Icon = meta.icon
  const facts = SEGMENTS.filter((g) => g.key !== 'safe' && (s[g.key] as number) > 0).map((g) => `${s[g.key]} ${g.label}`)
  return (
    <li className="kind-row">
      <div className="kind-head">
        <Icon size={14} className="kind-ico" />
        <span className="kind-name">{meta.plural}</span>
        <span className="kind-total mono">{fmt(s.total)}</span>
        <span className={`kind-risk mono ${s.at_risk > 0 ? 'hot' : ''}`} title="People at risk">{s.at_risk > 0 ? `${fmt(s.at_risk)} at risk` : `${fmt(s.present)} here`}</span>
      </div>
      <div className="stackbar" role="img" aria-label={`${meta.plural}: ${facts.join(', ') || 'all safe'}`}>
        {SEGMENTS.map((g) => {
          const v = s[g.key] as number
          return v > 0 ? <span key={g.key} className={g.cls} style={{ flexGrow: v }} title={`${v} ${g.label}`} /> : null
        })}
      </div>
      {facts.length > 0 && <div className="kind-facts">{facts.join(' · ')}</div>}
    </li>
  )
}

/** Live status of every kind of place in town. */
export function LiveStatus({ city }: Props) {
  const rows = KIND_ORDER.filter((k) => city?.by_kind[k]?.total)
  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2><Activity size={15} /> Live status by area</h2>
          <p className="panel-sub">Updated every simulated minute</p>
        </div>
      </header>
      {!city ? (
        <p className="muted small">No town yet.</p>
      ) : (
        <ul className="kind-list">
          {rows.map((k) => <KindRow key={k} kind={k} s={city.by_kind[k]!} />)}
        </ul>
      )}
      <div className="seg-legend">
        <span><i className="seg-burning" />On fire</span>
        <span><i className="seg-threatened" />Threatened</span>
        <span><i className="seg-damaged" />Damaged</span>
        <span><i className="seg-destroyed" />Destroyed</span>
        <span><i className="seg-safe" />Safe</span>
      </div>
    </section>
  )
}
