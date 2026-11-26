import { useEffect, useRef, useState } from 'react'
import type { MapData, SimPayload } from '../../api/types'
import { CityScene } from '../../scene/CityScene'
import { hasWebGL } from '../../scene/fallback2d'
import { Scene2D } from './Scene2D'

export interface FocusRequest {
  id: number | 'overview'
  nonce: number
}

interface Props {
  map: MapData | null
  sim: SimPayload | null
  active: boolean
  selectedId: number | null
  igniteMode: boolean
  focus: FocusRequest | null
  onSelect: (id: number | null) => void
  onHover: (id: number | null, x: number, y: number) => void
  onCellClick: (x: number, y: number) => void
}

/** True when the 2-D view is forced via ?view=2d or a saved preference. */
function prefers2D(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get('view') === '2d') return true
    return window.localStorage.getItem('firesim:view') === '2d'
  } catch {
    return false
  }
}

/** Shows the 3-D town, or the 2-D canvas fallback when WebGL is unavailable or forced. */
export function SceneView(props: Props) {
  const [use2D] = useState(() => prefers2D() || !hasWebGL())
  if (use2D) {
    return <Scene2D map={props.map} sim={props.sim} onCellClick={props.onCellClick} />
  }
  return <Scene3D {...props} />
}

/** Hosts the Three.js scene and forwards React state to it. */
function Scene3D(props: Props) {
  const host = useRef<HTMLDivElement>(null)
  const scene = useRef<CityScene | null>(null)
  const handlers = useRef(props)

  useEffect(() => {
    handlers.current = props
  })

  useEffect(() => {
    const s = new CityScene(host.current!, {
      onSelect: (id) => handlers.current.onSelect(id),
      onHover: (id, x, y) => handlers.current.onHover(id, x, y),
      onCellClick: (x, y) => handlers.current.onCellClick(x, y),
    })
    scene.current = s
    return () => {
      s.dispose()
      scene.current = null
    }
  }, [])

  const { map, sim, active, selectedId, igniteMode, focus } = props
  useEffect(() => {
    if (map) scene.current?.setMap(map)
  }, [map])
  useEffect(() => {
    if (sim) scene.current?.update(sim)
  }, [sim, map])
  useEffect(() => {
    scene.current?.setSelected(selectedId)
  }, [selectedId, map])
  useEffect(() => {
    scene.current?.setIgniteMode(igniteMode)
  }, [igniteMode])
  useEffect(() => {
    scene.current?.setPaused(!active)
  }, [active])
  useEffect(() => {
    if (!focus) return
    if (focus.id === 'overview') scene.current?.overview()
    else scene.current?.focus(focus.id)
  }, [focus])

  return <div className="scene-host" ref={host} />
}
