import { useCallback, useEffect, useRef, useState } from 'react'
import type { Simulation } from '../../hooks/useSimulation'
import { CrewPanel } from './CrewPanel'
import { EventFeed } from './EventFeed'
import { Inspector } from './Inspector'
import { LifeSafetyHud } from './LifeSafetyHud'
import { LiveStatus } from './LiveStatus'
import {
  BigScreenHud, BigScreenPriorities, CompletionBanner, EmptyState, HoverCard, Legend, MapToolbar, WindCompass,
} from './MapOverlays'
import { PlaybackBar } from './PlaybackBar'
import { PriorityQueue } from './PriorityQueue'
import { ScenarioPanel } from './ScenarioPanel'
import { SceneView, type FocusRequest } from './SceneView'

interface Props {
  sim: Simulation
  active: boolean
  onOpenDashboard: () => void
}

/** Live incident view: life-safety HUD, 3-D town, priorities, crews and log. */
export function CommandCenter({ sim, active, onOpenDashboard }: Props) {
  const { map, sim: state } = sim
  const city = state?.city ?? null
  const [selected, setSelected] = useState<number | null>(null)
  const [hover, setHover] = useState<{ id: number | null; x: number; y: number }>({ id: null, x: 0, y: 0 })
  const [igniteMode, setIgniteMode] = useState(false)
  const [focus, setFocus] = useState<FocusRequest | null>(null)
  const [bannerFor, setBannerFor] = useState<string | null>(null)
  const [seenMap, setSeenMap] = useState(map)
  const [bigScreen, setBigScreen] = useState(false)
  const nonce = useRef(0)
  const mapWrap = useRef<HTMLDivElement>(null)
  const bigRef = useRef(false)

  // Big-screen view: the map panel goes fullscreen (browser Fullscreen API). If the browser
  // refuses, the .big class still makes it cover the whole window.
  const enterBigScreen = useCallback(async () => {
    setBigScreen(true)
    const el = mapWrap.current
    if (el && !document.fullscreenElement && el.requestFullscreen) {
      try {
        await el.requestFullscreen({ navigationUI: 'hide' })
      } catch {
        /* fullscreen not allowed: the CSS fallback covers the window */
      }
    }
    setFocus({ id: 'overview', nonce: ++nonce.current })
  }, [])
  const exitBigScreen = useCallback(async () => {
    setBigScreen(false)
    if (document.fullscreenElement) await document.exitFullscreen().catch(() => undefined)
    setFocus({ id: 'overview', nonce: ++nonce.current })
  }, [])

  useEffect(() => {
    bigRef.current = bigScreen
  }, [bigScreen])

  // Esc (handled by the browser in fullscreen) and the F shortcut.
  useEffect(() => {
    const onFullscreen = () => {
      if (!document.fullscreenElement && bigRef.current) void exitBigScreen()
    }
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (!active || !map || e.ctrlKey || e.metaKey || e.altKey) return
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return
      if (e.key === 'f' || e.key === 'F') {
        e.preventDefault()
        void (bigRef.current ? exitBigScreen() : enterBigScreen())
      } else if (e.key === 'Escape' && bigRef.current) {
        void exitBigScreen()   // browsers usually exit fullscreen themselves; this covers the rest
      }
    }
    document.addEventListener('fullscreenchange', onFullscreen)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('fullscreenchange', onFullscreen)
      window.removeEventListener('keydown', onKey)
    }
  }, [active, map, enterBigScreen, exitBigScreen])

  // A new town clears the selection, ignition mode and banner (reset when the prop changes).
  if (map !== seenMap) {
    setSeenMap(map)
    setSelected(null)
    setIgniteMode(false)
    setBannerFor(null)
  }

  const completed = state?.state === 'completed'
  const igniting = igniteMode && !completed   // ignition only before / during a run
  const focusOn = (id: number | 'overview') => setFocus({ id, nonce: ++nonce.current })
  const select = (id: number | null) => setSelected(id)
  const onHover = (id: number | null, x: number, y: number) => {
    const r = mapWrap.current?.getBoundingClientRect()
    setHover({ id, x: r ? x - r.left : x, y: r ? y - r.top : y })
  }
  const canDispatch = !!city && city.crews_available > 0 && !completed
  const selectedAsset = selected != null ? map?.assets[selected] ?? null : null
  const hoverAsset = hover.id != null ? map?.assets[hover.id] ?? null : null
  const doneKey = completed && state ? `${state.scenario.id}:${state.tick}` : null

  return (
    <div className="command" hidden={!active}>
      <LifeSafetyHud sim={state} />
      <div className="command-body">
        <aside className="side side-left">
          <ScenarioPanel sim={sim} igniteMode={igniting} onIgniteMode={setIgniteMode} />
          <LiveStatus city={city} />
          <EventFeed events={city?.events ?? []} onSelect={(id) => { select(id); focusOn(id) }} />
        </aside>

        <main className={`map-wrap ${bigScreen ? 'big' : ''}`} ref={mapWrap}>
          <SceneView
            map={map}
            sim={state}
            active={active}
            selectedId={selected}
            igniteMode={igniting}
            focus={focus}
            onSelect={select}
            onHover={onHover}
            onCellClick={(x, y) => sim.ignite(x, y)}
          />
          {!map && <EmptyState online={sim.online} />}
          {map && (
            <>
              <WindCompass sim={state} />
              <MapToolbar
                igniteMode={igniting}
                canIgnite={!completed}
                bigScreen={bigScreen}
                onIgnite={setIgniteMode}
                onOverview={() => focusOn('overview')}
                onBigScreen={() => void (bigScreen ? exitBigScreen() : enterBigScreen())}
              />
              {bigScreen && (
                <>
                  <BigScreenHud sim={state} />
                  <BigScreenPriorities
                    city={city}
                    canDispatch={canDispatch}
                    onDispatch={sim.dispatch}
                    onFocus={(id) => { select(id); focusOn(id) }}
                  />
                </>
              )}
              <Legend />
              {igniting && <div className="overlay ignite-hint">Ignition mode: click grass, forest or a building to start a fire</div>}
              <PlaybackBar sim={sim} />
              {state && doneKey && bannerFor !== doneKey && (
                <CompletionBanner sim={state} onDashboard={onOpenDashboard} onDismiss={() => setBannerFor(doneKey)} />
              )}
              {hoverAsset && <HoverCard asset={hoverAsset} city={city} x={hover.x} y={hover.y} />}
            </>
          )}
          {sim.error && (
            <div className="overlay toast" role="alert">
              <span>{sim.error}</span>
              <button className="link" onClick={sim.clearError}>Dismiss</button>
            </div>
          )}
        </main>

        <aside className="side side-right">
          <PriorityQueue
            city={city}
            selectedId={selected}
            canDispatch={canDispatch}
            onDispatch={sim.dispatch}
            onFocus={(id) => { select(id); focusOn(id) }}
            onSelect={select}
          />
          <CrewPanel
            city={city}
            map={map}
            disabled={completed}
            onToggleAuto={sim.setAutoDispatch}
            onFocus={(id) => { select(id); focusOn(id) }}
          />
          <Inspector
            asset={selectedAsset}
            city={city}
            canDispatch={canDispatch}
            onDispatch={sim.dispatch}
            onFocus={focusOn}
            onClose={() => select(null)}
          />
        </aside>
      </div>
    </div>
  )
}
