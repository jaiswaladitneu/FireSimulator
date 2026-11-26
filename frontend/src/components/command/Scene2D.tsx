import { type MouseEvent, useEffect, useRef } from 'react'
import type { MapData, SimPayload } from '../../api/types'
import { drawGrid } from '../../scene/fallback2d'

interface Props {
  map: MapData | null
  sim: SimPayload | null
  onCellClick: (x: number, y: number) => void
}

/** Flat 2-D canvas view of the grid, used as a fallback when WebGL is unavailable. */
export function Scene2D({ map, sim, onCellClick }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const cellRef = useRef(1)

  useEffect(() => {
    const canvas = canvasRef.current
    const grid = sim?.grid
    if (!canvas || !grid?.length) return
    const h = grid.length
    const w = grid[0].length
    const host = canvas.parentElement
    const box = Math.min(host?.clientWidth || 640, host?.clientHeight || 640)
    const cellPx = Math.max(1, Math.floor(box / Math.max(w, h)))
    cellRef.current = cellPx
    canvas.width = w * cellPx
    canvas.height = h * cellPx
    const ctx = canvas.getContext('2d')
    if (ctx) drawGrid(ctx, grid, map?.landuse ?? [], cellPx)
  }, [sim, map])

  const handleClick = (e: MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const x = Math.floor(((e.clientX - rect.left) * (canvas.width / rect.width)) / cellRef.current)
    const y = Math.floor(((e.clientY - rect.top) * (canvas.height / rect.height)) / cellRef.current)
    onCellClick(x, y)
  }

  return (
    <div className="scene-host scene-2d">
      <canvas
        ref={canvasRef}
        onClick={handleClick}
        style={{ maxWidth: '100%', maxHeight: '100%', display: 'block', margin: 'auto', cursor: 'crosshair' }}
      />
    </div>
  )
}
