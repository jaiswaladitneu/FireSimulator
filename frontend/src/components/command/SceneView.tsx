import { useEffect, useRef } from 'react'
import type { MapData, SimPayload } from '../../api/types'
import { CityScene } from '../../scene/CityScene'

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

/** Hosts the Three.js scene and forwards React state to it. */
export function SceneView(props: Props) {
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
