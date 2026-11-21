import * as THREE from 'three'
import { MapControls } from 'three/addons/controls/MapControls.js'
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js'
import { CELL, FUEL, LU, STATUS_NAMES, type Asset, type MapData, type SimPayload } from '../api/types'
import { GroundPainter } from './ground'
import { Particles, spriteTexture } from './particles'
import * as P from './palette'

export interface SceneCallbacks {
  onHover: (assetId: number | null, clientX: number, clientY: number) => void
  onSelect: (assetId: number | null) => void
  onCellClick: (x: number, y: number) => void
}

const HEIGHT_SCALE = 7      // elevation 0..1 -> world units
const FLOOR = 0.9           // world height of one storey
const BASE_Y = -2.6         // bottom of the diorama edge
const FACILITIES = new Set(['school', 'hospital', 'fuel_station', 'battery_storage', 'fire_station', 'park'])
const STATUS = { SAFE: 0, THREATENED: 1, BURNING: 2, DAMAGED: 3, DESTROYED: 4, BLOCKED: 5 }

const PERSON_SVG =
  '<svg viewBox="0 0 24 24" width="11" height="11" aria-hidden="true"><circle cx="12" cy="7" r="4.2" fill="currentColor"/><path d="M3.5 22c0-4.9 3.8-8.6 8.5-8.6s8.5 3.7 8.5 8.6z" fill="currentColor"/></svg>'
const CAR_SVG =
  '<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><path d="M5 11l1.6-4.4A2 2 0 0 1 8.5 5h7a2 2 0 0 1 1.9 1.6L19 11h.5A1.5 1.5 0 0 1 21 12.5V17h-2v1.5a1 1 0 0 1-2 0V17H7v1.5a1 1 0 0 1-2 0V17H3v-4.5A1.5 1.5 0 0 1 4.5 11zm2.2 0h9.6l-1.1-3.4a.8.8 0 0 0-.8-.6H9a.8.8 0 0 0-.8.6z" fill="currentColor"/></svg>'

type Role = 'body' | 'roof' | 'cap' | 'canopy' | 'pillar' | 'cross'

interface Piece {
  mesh: THREE.InstancedMesh
  i: number
  asset: number
  role: Role
  x: number          // world centre
  z: number
  ground: number     // world y of the ground
  sx: number         // base scale
  sy: number
  sz: number
  lift: number       // height of the body below this piece (roofs, caps, crosses)
  color: THREE.Color
}

interface FlameSpot {
  x: number
  y: number
  z: number
  h: number
  w: number
  phase: number
  hazmat: boolean
}

interface Beacon {
  group: THREE.Group
  ring: THREE.Mesh
  beam: THREE.Mesh
}

interface Truck {
  group: THREE.Group
  light: THREE.MeshBasicMaterial
  pos: THREE.Vector3
  goal: THREE.Vector3
  heading: number
  status: string
  target: number | null
  line: THREE.Line
}

const tmpM = new THREE.Matrix4()
const tmpQ = new THREE.Quaternion()
const tmpV = new THREE.Vector3()
const tmpS = new THREE.Vector3()
const tmpC = new THREE.Color()
const UP = new THREE.Vector3(0, 1, 0)
const toColor = (rgb: P.RGB) => new THREE.Color().setRGB(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, THREE.SRGBColorSpace)
const BURN_COLOR = toColor(P.BURN_TINT)
const SOOT_COLOR = toColor(P.SOOT)
const CHAR_COLOR = toColor(P.CHARRED)

function disposeTree(obj: THREE.Object3D) {
  obj.traverse((o) => {
    const m = o as THREE.Mesh
    if (m.geometry) m.geometry.dispose()
    const mat = m.material as THREE.Material | THREE.Material[] | undefined
    if (Array.isArray(mat)) mat.forEach((x) => x.dispose())
    else if (mat) mat.dispose()
  })
}

function colored(geo: THREE.BufferGeometry, color: string): THREE.BufferGeometry {
  const g = geo.index ? geo.toNonIndexed() : geo
  const c = new THREE.Color(color)
  const n = g.attributes.position.count
  const arr = new Float32Array(n * 3)
  for (let i = 0; i < n; i++) arr.set([c.r, c.g, c.b], i * 3)
  g.setAttribute('color', new THREE.BufferAttribute(arr, 3))
  return g
}

/**
 * The 3-D town: terrain, trees, buildings, fire, smoke, crews, priority beacons
 * and people labels. React owns the UI around it and talks to it through
 * setMap / update / setSelected / focus.
 */
export class CityScene {
  private container: HTMLElement
  private cb: SceneCallbacks
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private controls: MapControls
  private hemi: THREE.HemisphereLight
  private sun: THREE.DirectionalLight
  private fireLight: THREE.PointLight
  private world = new THREE.Group()
  private labelsRoot: HTMLDivElement
  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2()
  private timer = new THREE.Timer()
  private raf = 0
  private resizeObs: ResizeObserver
  private disposed = false
  private paused = false

  // map-dependent state
  private map: MapData | null = null
  private W = 0
  private H = 0
  private corner: Float32Array = new Float32Array(0)
  private ground: GroundPainter | null = null
  private terrain: THREE.Mesh | null = null
  private assetGrid: Int32Array = new Int32Array(0)
  private pieces: Piece[] = []
  private piecesByAsset = new Map<number, Piece[]>()
  private pieceLookup = new Map<THREE.Object3D, Piece[]>()
  private pickables: THREE.Object3D[] = []
  private assetTop: Float32Array = new Float32Array(0)   // world y of each asset's top (labels)
  private cellTop: Float32Array = new Float32Array(0)    // building height per cell (flames)
  private trees: { mesh: THREE.InstancedMesh; cell: Int32Array; base: Float32Array; mats: Float32Array }[] = []
  private cellTrees = new Map<number, [number, number][]>()
  private flames: THREE.InstancedMesh | null = null
  private flameSpots: FlameSpot[] = []
  private trucks: Truck[] = []
  private labels = new Map<number, HTMLDivElement>()
  private labelOrder: number[] = []
  private labelsDirty = true

  // dynamic state
  private prevGrid: Int8Array = new Int8Array(0)
  private assetStatus: Int8Array = new Int8Array(0)
  private lastSim: SimPayload | null = null
  private selected: number | null = null
  private hovered: number | null = null
  private igniteMode = false
  private wind = new THREE.Vector2()
  private daylight = 1   // 0 at night, 1 at noon (smoke is unlit, so it is shaded by hand)
  private fireCentroid = new THREE.Vector3()
  private fireCount = 0
  private seenExplosions = new Set<string>()
  private flashes: { mesh: THREE.Mesh; ring: THREE.Mesh; t: number }[] = []
  private beacons: Beacon[] = []
  private beaconTargets: { id: number; level: string }[] = []
  private selBox: THREE.LineSegments
  private hoverBox: THREE.LineSegments
  private smoke: Particles
  private embers: Particles
  private water: Particles
  private fly: { from: THREE.Vector3; to: THREE.Vector3; tFrom: THREE.Vector3; tTo: THREE.Vector3; t: number } | null = null
  private downAt: { x: number; y: number } | null = null

  constructor(container: HTMLElement, callbacks: SceneCallbacks) {
    this.container = container
    this.cb = callbacks
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFShadowMap
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.05
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.domElement.className = 'scene-canvas'
    container.appendChild(this.renderer.domElement)

    this.labelsRoot = document.createElement('div')
    this.labelsRoot.className = 'scene-labels'
    container.appendChild(this.labelsRoot)

    this.scene.background = new THREE.Color('#0a0f19')
    this.scene.fog = new THREE.Fog('#0a0f19', 140, 420)
    this.scene.add(this.world)

    this.camera = new THREE.PerspectiveCamera(42, 1, 0.3, 1200)
    this.camera.position.set(40, 60, 70)
    this.controls = new MapControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.screenSpacePanning = false
    this.controls.maxPolarAngle = 1.28
    this.controls.minDistance = 5
    this.controls.zoomSpeed = 1.1
    this.controls.addEventListener('change', () => (this.labelsDirty = true))

    this.hemi = new THREE.HemisphereLight('#cfe0ff', '#3a3020', 0.9)
    this.sun = new THREE.DirectionalLight('#fff4e0', 2.4)
    this.sun.castShadow = true
    this.sun.shadow.mapSize.set(2048, 2048)
    this.sun.shadow.bias = -0.0006
    this.sun.shadow.normalBias = 0.04
    this.fireLight = new THREE.PointLight('#ff7a2a', 0, 70, 1.4)
    this.scene.add(this.hemi, this.sun, this.sun.target, this.fireLight)

    this.smoke = new Particles({
      capacity: 2600, texture: spriteTexture('smoke'), blending: THREE.NormalBlending,
      buoyancy: 0.35, gravity: 0, windFollow: 0.35, fadeIn: 0.12, flicker: 0,
    })
    this.embers = new Particles({
      capacity: 900, texture: spriteTexture('ember'), blending: THREE.AdditiveBlending,
      buoyancy: 0.4, gravity: 0.9, windFollow: 0.8, fadeIn: 0.05, flicker: 0.5,
    })
    this.water = new Particles({
      capacity: 900, texture: spriteTexture('ember'), blending: THREE.AdditiveBlending,
      buoyancy: 0, gravity: 9.5, windFollow: 0, fadeIn: 0.05, flicker: 0.15,
    })
    this.scene.add(this.smoke.points, this.embers.points, this.water.points)

    const boxEdges = new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0))
    this.selBox = new THREE.LineSegments(boxEdges, new THREE.LineBasicMaterial({ color: '#38bdf8' }))
    this.hoverBox = new THREE.LineSegments(boxEdges.clone(), new THREE.LineBasicMaterial({ color: '#f8fafc', transparent: true, opacity: 0.7 }))
    this.selBox.visible = this.hoverBox.visible = false
    this.scene.add(this.selBox, this.hoverBox)

    for (let i = 0; i < 8; i++) this.beacons.push(this.makeBeacon())

    const el = this.renderer.domElement
    el.addEventListener('pointermove', this.onPointerMove)
    el.addEventListener('pointerdown', this.onPointerDown)
    el.addEventListener('pointerup', this.onPointerUp)
    el.addEventListener('pointerleave', this.onPointerLeave)
    el.addEventListener('dblclick', this.onDoubleClick)

    this.resizeObs = new ResizeObserver(() => this.resize())
    this.resizeObs.observe(container)
    this.resize()
    this.setTimeOfDay(14)
    this.loop()
  }

  // ---- public API ------------------------------------------------------------
  /** Stop rendering while the view is hidden (e.g. the dashboard tab is open). */
  setPaused(paused: boolean) {
    if (paused === this.paused || this.disposed) return
    this.paused = paused
    if (paused) cancelAnimationFrame(this.raf)
    else {
      this.timer.update()   // don't count the hidden time as one huge frame
      this.resize()
      this.loop()
    }
  }

  setIgniteMode(on: boolean) {
    this.igniteMode = on
    this.renderer.domElement.style.cursor = on ? 'crosshair' : ''
  }

  setSelected(id: number | null) {
    this.selected = id
    this.placeBox(this.selBox, id)
    this.labelsDirty = true
    this.refreshLabelClasses()
  }

  /** Smoothly move the camera to look at an asset. */
  focus(id: number) {
    const a = this.map?.assets[id]
    if (!a) return
    const [cx, cz] = this.toWorld(a.x + a.w / 2, a.y + a.h / 2)
    const target = new THREE.Vector3(cx, this.heightAt(a.x + a.w / 2, a.y + a.h / 2), cz)
    const dir = this.camera.position.clone().sub(this.controls.target).normalize()
    const dist = Math.max(14, Math.min(26, Math.max(a.w, a.h) * 2.4))
    this.fly = {
      from: this.camera.position.clone(),
      to: target.clone().add(dir.multiplyScalar(dist)),
      tFrom: this.controls.target.clone(),
      tTo: target,
      t: 0,
    }
  }

  /** Camera pose that frames the whole town for the current screen shape. */
  private overviewPose() {
    const size = Math.max(this.W, this.H)
    const target = new THREE.Vector3(0, this.heightAt(this.W / 2, this.H / 2), 0)
    // Framing is tuned on a 1.4:1 view; narrower views back off so the town still fits side to side.
    const dist = size * 0.96 * Math.max(1, 1.4 / Math.max(0.3, this.camera.aspect))
    const dir = new THREE.Vector3(0.32, 0.62, 0.66).normalize()
    return { target, position: target.clone().add(dir.multiplyScalar(dist)) }
  }

  /** Fly the camera to the whole-town view. */
  overview() {
    if (!this.map) return
    const pose = this.overviewPose()
    this.fly = {
      from: this.camera.position.clone(),
      to: pose.position,
      tFrom: this.controls.target.clone(),
      tTo: pose.target,
      t: 0,
    }
  }

  setMap(map: MapData) {
    this.clearWorld()
    this.map = map
    this.W = map.width
    this.H = map.height
    this.buildTerrain(map)
    this.buildAssetGrid(map)
    this.buildTrees(map)
    this.buildBuildings(map)
    this.buildFlames()
    this.buildTrucks(map)
    this.buildLabels(map)
    this.prevGrid = new Int8Array(this.W * this.H).fill(-1)
    this.assetStatus = new Int8Array(map.assets.length).fill(-1)
    this.seenExplosions.clear()
    this.smoke.clear()
    this.embers.clear()
    this.water.clear()

    const size = Math.max(this.W, this.H)
    this.controls.maxDistance = size * 1.7
    this.scene.fog = new THREE.Fog('#0a0f19', size * 1.4, size * 4)
    const s = this.sun.shadow.camera
    s.left = -size * 0.75
    s.right = size * 0.75
    s.top = size * 0.75
    s.bottom = -size * 0.75
    s.near = 1
    s.far = size * 4
    s.updateProjectionMatrix()
    const pose = this.overviewPose()
    this.controls.target.copy(pose.target)
    this.camera.position.copy(pose.position)
    this.controls.update()
    this.setTimeOfDay(map.hour)
    this.labelsDirty = true
  }

  update(sim: SimPayload) {
    const map = this.map
    if (!map || sim.grid.length !== this.H || sim.grid[0]?.length !== this.W) return
    const prevTick = this.lastSim?.tick ?? -1
    this.lastSim = sim
    this.ground?.update(sim.grid, sim.tick)
    this.updateTrees(sim.grid)
    this.updateFlames(sim.grid)
    this.rememberGrid(sim.grid)
    if (sim.wind) this.setWind(sim.wind.direction, sim.wind.speed)

    const city = sim.city
    if (city) {
      this.updateBuildings(city.assets.status)
      this.updateTrucks(sim)
      this.beaconTargets = city.priorities
        .filter((p) => p.level === 'critical' || p.level === 'high')
        .slice(0, this.beacons.length)
        .map((p) => ({ id: p.id, level: p.level }))
      this.placeBeacons()
      for (const e of city.events) {
        if (e.type !== 'explosion' || e.asset_id == null) continue
        const key = `${e.tick}:${e.asset_id}`
        if (this.seenExplosions.has(key)) continue
        this.seenExplosions.add(key)
        if (sim.tick - e.tick <= 2) this.explode(e.asset_id)
      }
      this.setTimeOfDay(city.hour + city.minutes / 60)
      this.updateLabels(sim)
    }
    if (sim.tick < prevTick) {
      // reset: clear transient effects
      this.smoke.clear()
      this.embers.clear()
      this.water.clear()
      this.seenExplosions.clear()
    }
    this.labelsDirty = true
  }

  setWind(directionDeg: number, speedKmh: number) {
    const rad = (directionDeg * Math.PI) / 180
    const k = 0.05 * speedKmh + 0.2
    // direction the wind blows toward: north = -z, east = +x
    this.wind.set(Math.sin(rad) * k, -Math.cos(rad) * k)
  }

  dispose() {
    this.disposed = true
    cancelAnimationFrame(this.raf)
    this.resizeObs.disconnect()
    const el = this.renderer.domElement
    el.removeEventListener('pointermove', this.onPointerMove)
    el.removeEventListener('pointerdown', this.onPointerDown)
    el.removeEventListener('pointerup', this.onPointerUp)
    el.removeEventListener('pointerleave', this.onPointerLeave)
    el.removeEventListener('dblclick', this.onDoubleClick)
    this.clearWorld()
    this.smoke.dispose()
    this.embers.dispose()
    this.water.dispose()
    this.timer.dispose()
    disposeTree(this.scene)
    this.controls.dispose()
    this.renderer.dispose()
    el.remove()
    this.labelsRoot.remove()
  }

  // ---- coordinates -------------------------------------------------------------
  /** Cell coordinates (continuous) -> world x, z. */
  private toWorld(x: number, y: number): [number, number] {
    return [x - this.W / 2, y - this.H / 2]
  }

  /** Terrain height at continuous cell coordinates (bilinear over cell corners). */
  private heightAt(x: number, y: number) {
    const W1 = this.W + 1
    if (!this.corner.length) return 0
    const cx = Math.max(0, Math.min(this.W - 1e-4, x))
    const cy = Math.max(0, Math.min(this.H - 1e-4, y))
    const ix = Math.floor(cx)
    const iy = Math.floor(cy)
    const fx = cx - ix
    const fy = cy - iy
    const h00 = this.corner[iy * W1 + ix]
    const h10 = this.corner[iy * W1 + ix + 1]
    const h01 = this.corner[(iy + 1) * W1 + ix]
    const h11 = this.corner[(iy + 1) * W1 + ix + 1]
    return (h00 * (1 - fx) + h10 * fx) * (1 - fy) + (h01 * (1 - fx) + h11 * fx) * fy
  }

  // ---- build ---------------------------------------------------------------------
  private clearWorld() {
    for (const child of [...this.world.children]) {
      this.world.remove(child)
      disposeTree(child)
    }
    this.ground?.dispose()
    this.ground = null
    this.terrain = null
    this.pieces = []
    this.piecesByAsset.clear()
    this.pieceLookup.clear()
    this.pickables = []
    this.trees = []
    this.cellTrees.clear()
    this.flames = null
    this.flameSpots = []
    this.trucks = []
    this.labels.clear()
    this.labelOrder = []
    this.labelsRoot.replaceChildren()
    this.flashes = []
    this.selBox.visible = this.hoverBox.visible = false
    for (const b of this.beacons) b.group.visible = false
  }

  private buildTerrain(map: MapData) {
    const { W, H } = this
    const W1 = W + 1
    this.corner = new Float32Array(W1 * (H + 1))
    for (let iy = 0; iy <= H; iy++) {
      for (let ix = 0; ix <= W; ix++) {
        let sum = 0
        let n = 0
        for (const [dx, dy] of [[-1, -1], [0, -1], [-1, 0], [0, 0]]) {
          const x = ix + dx
          const y = iy + dy
          if (x >= 0 && y >= 0 && x < W && y < H) {
            sum += map.elevation[y][x]
            n++
          }
        }
        this.corner[iy * W1 + ix] = (sum / Math.max(1, n)) * HEIGHT_SCALE
      }
    }
    const geo = new THREE.PlaneGeometry(W, H, W, H)
    geo.rotateX(-Math.PI / 2)
    const pos = geo.attributes.position as THREE.BufferAttribute
    for (let i = 0; i < pos.count; i++) pos.setY(i, this.corner[i])
    geo.computeVertexNormals()

    this.ground = new GroundPainter(map.landuse, map.fuel)
    const mat = new THREE.MeshStandardMaterial({
      map: this.ground.colorTex,
      emissiveMap: this.ground.glowTex,
      emissive: new THREE.Color('#ffffff'),
      emissiveIntensity: 2.2,
      roughness: 0.95,
      metalness: 0,
    })
    this.terrain = new THREE.Mesh(geo, mat)
    this.terrain.receiveShadow = true
    this.world.add(this.terrain)

    // Diorama edges: soil walls from the terrain edge down to the base.
    const wall: number[] = []
    const push = (x1: number, z1: number, y1: number, x2: number, z2: number, y2: number) => {
      wall.push(x1, y1, z1, x1, BASE_Y, z1, x2, y2, z2, x2, y2, z2, x1, BASE_Y, z1, x2, BASE_Y, z2)
    }
    const h = (ix: number, iy: number) => this.corner[iy * W1 + ix]
    for (let ix = 0; ix < W; ix++) {
      push(ix - W / 2, -H / 2, h(ix, 0), ix + 1 - W / 2, -H / 2, h(ix + 1, 0))
      push(ix + 1 - W / 2, H / 2, h(ix + 1, H), ix - W / 2, H / 2, h(ix, H))
    }
    for (let iy = 0; iy < H; iy++) {
      push(-W / 2, iy + 1 - H / 2, h(0, iy + 1), -W / 2, iy - H / 2, h(0, iy))
      push(W / 2, iy - H / 2, h(W, iy), W / 2, iy + 1 - H / 2, h(W, iy + 1))
    }
    const wg = new THREE.BufferGeometry()
    wg.setAttribute('position', new THREE.Float32BufferAttribute(wall, 3))
    wg.computeVertexNormals()
    const walls = new THREE.Mesh(wg, new THREE.MeshStandardMaterial({ color: '#3a2c22', roughness: 1, side: THREE.DoubleSide }))
    this.world.add(walls)
    const base = new THREE.Mesh(
      new THREE.BoxGeometry(W + 0.02, 0.2, H + 0.02),
      new THREE.MeshStandardMaterial({ color: '#22190f', roughness: 1 }),
    )
    base.position.y = BASE_Y - 0.1
    this.world.add(base)
  }

  private buildAssetGrid(map: MapData) {
    const { W, H } = this
    this.assetGrid = new Int32Array(W * H).fill(-1)
    const fill = (a: Asset, x0: number, y0: number, w: number, h: number) => {
      for (let y = Math.max(0, y0); y < Math.min(H, y0 + h); y++)
        for (let x = Math.max(0, x0); x < Math.min(W, x0 + w); x++) this.assetGrid[y * W + x] = a.id
    }
    for (const a of map.assets) if (a.kind === 'road' || FACILITIES.has(a.kind)) fill(a, a.x, a.y, a.w, a.h)
    for (const a of map.assets) for (const p of a.parts) fill(a, p.x, p.y, p.w, p.h)
  }

  private buildTrees(map: MapData) {
    const { W, H } = this
    const conifer = mergeGeometries([
      colored(new THREE.CylinderGeometry(0.05, 0.07, 0.32, 5).translate(0, 0.16, 0), '#5b3d24'),
      colored(new THREE.ConeGeometry(0.34, 0.95, 7).translate(0, 0.32 + 0.47, 0), '#2f6b35'),
      colored(new THREE.ConeGeometry(0.26, 0.6, 7).translate(0, 0.32 + 0.85, 0), '#3a7d3e'),
    ])!
    const leafy = mergeGeometries([
      colored(new THREE.CylinderGeometry(0.05, 0.07, 0.36, 5).translate(0, 0.18, 0), '#5b3d24'),
      colored(new THREE.IcosahedronGeometry(0.36, 0).translate(0, 0.62, 0), '#4f8f3a'),
    ])!
    const bush = colored(new THREE.IcosahedronGeometry(0.24, 0).scale(1, 0.7, 1).translate(0, 0.14, 0), '#5d7f34')
    const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9, flatShading: true })

    type Spot = { x: number; y: number; z: number; s: number; r: number; tint: number; cell: number }
    const spots: Record<'conifer' | 'leafy' | 'bush', Spot[]> = { conifer: [], leafy: [], bush: [] }
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const f = map.fuel[y][x]
        const l = map.landuse[y][x]
        const cell = y * W + x
        const add = (kind: 'conifer' | 'leafy' | 'bush', k: number, scale: number) => {
          const jx = 0.2 + 0.6 * P.hash2(x * 7 + k, y * 13)
          const jy = 0.2 + 0.6 * P.hash2(x * 11, y * 5 + k)
          const [wx, wz] = this.toWorld(x + jx, y + jy)
          spots[kind].push({
            x: wx, z: wz, y: this.heightAt(x + jx, y + jy),
            s: scale * (0.75 + 0.5 * P.hash2(x + k * 3, y * 3)),
            r: P.hash2(y, x + k) * Math.PI * 2,
            tint: 0.85 + 0.3 * P.hash2(x * 3 + k, y * 17),
            cell,
          })
        }
        if (f === FUEL.FOREST) {
          if (l === LU.FOREST) {
            add('conifer', 1, 1.05)
            if (P.hash2(x, y) > 0.45) add('conifer', 2, 0.85)
          } else add('leafy', 1, 1.0)
        } else if (f === FUEL.SHRUB) {
          if (l !== LU.SHRUB || P.hash2(x + 3, y) > 0.35) add('bush', 1, 1)
        }
      }
    }
    for (const [kind, geo] of [['conifer', conifer], ['leafy', leafy], ['bush', bush]] as const) {
      const list = spots[kind]
      if (!list.length) {
        geo.dispose()
        continue
      }
      const mesh = new THREE.InstancedMesh(geo, mat, list.length)
      mesh.castShadow = kind !== 'bush'
      mesh.receiveShadow = true
      const cells = new Int32Array(list.length)
      const base = new Float32Array(list.length)
      const mats = new Float32Array(list.length * 16)
      const meshIndex = this.trees.length
      list.forEach((s, i) => {
        tmpQ.setFromAxisAngle(UP, s.r)
        tmpM.compose(tmpV.set(s.x, s.y, s.z), tmpQ, tmpS.set(s.s, s.s, s.s))
        mesh.setMatrixAt(i, tmpM)
        tmpM.toArray(mats, i * 16)
        mesh.setColorAt(i, tmpC.setScalar(s.tint))
        cells[i] = s.cell
        base[i] = s.tint
        const list2 = this.cellTrees.get(s.cell)
        if (list2) list2.push([meshIndex, i])
        else this.cellTrees.set(s.cell, [[meshIndex, i]])
      })
      mesh.instanceMatrix.needsUpdate = true
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
      this.trees.push({ mesh, cell: cells, base, mats })
      this.world.add(mesh)
    }
  }

  private buildBuildings(map: MapData) {
    const { W, H } = this
    this.assetTop = new Float32Array(map.assets.length)
    this.cellTop = new Float32Array(W * H)
    const box = new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0)
    const pyramid = new THREE.ConeGeometry(Math.SQRT1_2, 1, 4, 1).rotateY(Math.PI / 4).translate(0, 0.5, 0)
    const bodyMat = new THREE.MeshStandardMaterial({ roughness: 0.8, metalness: 0.02 })
    const roofMat = new THREE.MeshStandardMaterial({ roughness: 0.85, flatShading: true })

    type Spec = { role: Role; asset: number; x: number; z: number; ground: number; sx: number; sy: number; sz: number; lift: number; color: string }
    const specs: Spec[] = []
    for (const a of map.assets) {
      let top = 0
      const groundY = this.heightAt(a.x + a.w / 2, a.y + a.h / 2)
      a.parts.forEach((p, pi) => {
        const [cx, cz] = this.toWorld(p.x + p.w / 2, p.y + p.h / 2)
        const hgt = Math.max(0.5, p.height * FLOOR)
        const inset = a.kind === 'house' ? 0.16 : 0.06
        const sx = Math.max(0.3, p.w - inset)
        const sz = Math.max(0.3, p.h - inset)
        let wall = P.STYLE_COLOR[p.style] ?? '#cccccc'
        if (p.style === 'house') wall = P.pick(P.HOUSE_WALLS, a.id * 3 + pi)
        if (p.style === 'shop') wall = P.pick(P.SHOP_WALLS, a.id * 5 + pi)
        if (p.style === 'kiosk' && a.kind === 'battery_storage') wall = '#9aa5ad'
        for (let y = p.y; y < p.y + p.h; y++)
          for (let x = p.x; x < p.x + p.w; x++) if (x >= 0 && y >= 0 && x < W && y < H) this.cellTop[y * W + x] = hgt
        if (p.style === 'canopy') {
          const ch = 1.3 * FLOOR
          specs.push({ role: 'canopy', asset: a.id, x: cx, z: cz, ground: groundY, sx: sx + 0.1, sy: 0.16, sz: sz + 0.1, lift: ch, color: '#e9ebee' })
          for (const [ox, oz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
            specs.push({ role: 'pillar', asset: a.id, x: cx + ox * (sx / 2 - 0.15), z: cz + oz * (sz / 2 - 0.15), ground: groundY, sx: 0.1, sy: ch, sz: 0.1, lift: 0, color: '#9ca3af' })
          }
          top = Math.max(top, ch + 0.2)
          return
        }
        specs.push({ role: 'body', asset: a.id, x: cx, z: cz, ground: groundY, sx, sy: hgt, sz, lift: 0, color: wall })
        if (p.style === 'house') {
          const rh = 0.45 + 0.12 * Math.min(p.w, p.h)
          specs.push({ role: 'roof', asset: a.id, x: cx, z: cz, ground: groundY, sx: sx * 1.12, sy: rh, sz: sz * 1.12, lift: hgt, color: P.pick(P.HOUSE_ROOFS, a.id * 7 + pi) })
          top = Math.max(top, hgt + rh)
        } else if (p.style !== 'container') {
          const cap = tmpC.set(wall).multiplyScalar(0.72).getStyle()
          specs.push({ role: 'cap', asset: a.id, x: cx, z: cz, ground: groundY, sx: sx + 0.06, sy: 0.14, sz: sz + 0.06, lift: hgt, color: cap })
          if (p.style === 'hospital') {
            const len = Math.min(sx, sz) * 0.5
            specs.push({ role: 'cross', asset: a.id, x: cx, z: cz, ground: groundY, sx: len, sy: 0.06, sz: len * 0.3, lift: hgt + 0.14, color: '#d62828' })
            specs.push({ role: 'cross', asset: a.id, x: cx, z: cz, ground: groundY, sx: len * 0.3, sy: 0.06, sz: len, lift: hgt + 0.14, color: '#d62828' })
          }
          top = Math.max(top, hgt + 0.2)
        } else top = Math.max(top, hgt)
      })
      this.assetTop[a.id] = groundY + (top || 0.4)
    }

    const groups: Record<Role, Spec[]> = { body: [], roof: [], cap: [], canopy: [], pillar: [], cross: [] }
    for (const s of specs) groups[s.role].push(s)
    const geoFor: Record<Role, THREE.BufferGeometry> = { body: box, roof: pyramid, cap: box, canopy: box, pillar: box, cross: box }
    const matFor: Record<Role, THREE.Material> = { body: bodyMat, roof: roofMat, cap: bodyMat, canopy: bodyMat, pillar: bodyMat, cross: bodyMat }
    for (const role of Object.keys(groups) as Role[]) {
      const list = groups[role]
      if (!list.length) continue
      const mesh = new THREE.InstancedMesh(geoFor[role], matFor[role], list.length)
      mesh.castShadow = true
      mesh.receiveShadow = true
      const owned: Piece[] = []
      list.forEach((s, i) => {
        const piece: Piece = { mesh, i, asset: s.asset, role, x: s.x, z: s.z, ground: s.ground, sx: s.sx, sy: s.sy, sz: s.sz, lift: s.lift, color: new THREE.Color(s.color) }
        owned.push(piece)
        this.pieces.push(piece)
        const arr = this.piecesByAsset.get(s.asset)
        if (arr) arr.push(piece)
        else this.piecesByAsset.set(s.asset, [piece])
        this.applyPiece(piece, STATUS.SAFE)
      })
      mesh.instanceMatrix.needsUpdate = true
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
      this.pieceLookup.set(mesh, owned)
      if (role !== 'pillar' && role !== 'cross') this.pickables.push(mesh)
      this.world.add(mesh)
    }
  }

  private applyPiece(p: Piece, status: number) {
    const destroyed = status === STATUS.DESTROYED
    const k = destroyed ? 0.3 : 1
    let sy = p.sy
    let y = p.ground + p.lift
    if (p.role === 'body' || p.role === 'pillar') sy = p.sy * k
    else if (destroyed) {
      y = p.ground + p.lift * 0.3
      sy = p.role === 'roof' ? p.sy * 0.35 : p.sy
      if (p.role === 'cross') sy = 0.0001
    }
    tmpM.compose(tmpV.set(p.x, y, p.z), tmpQ.identity(), tmpS.set(p.sx, Math.max(0.0001, sy), p.sz))
    p.mesh.setMatrixAt(p.i, tmpM)
    tmpC.copy(p.color)
    if (status === STATUS.BURNING) tmpC.lerp(BURN_COLOR, 0.5)
    else if (status === STATUS.DAMAGED) tmpC.lerp(SOOT_COLOR, 0.5)
    else if (destroyed) tmpC.copy(CHAR_COLOR)
    p.mesh.setColorAt(p.i, tmpC)
  }

  private buildFlames() {
    const geo = new THREE.ConeGeometry(0.42, 1, 9, 6, true).translate(0, 0.5, 0)
    const pos = geo.attributes.position
    const colors = new Float32Array(pos.count * 3)
    const stops: [number, THREE.Color][] = [
      [0, new THREE.Color('#fff4b8')],
      [0.25, new THREE.Color('#ffc23a')],
      [0.55, new THREE.Color('#ff6a18')],
      [1, new THREE.Color('#9c1a08')],
    ]
    for (let i = 0; i < pos.count; i++) {
      const t = pos.getY(i)
      let c = stops[stops.length - 1][1]
      for (let s = 1; s < stops.length; s++) {
        if (t <= stops[s][0]) {
          const [t0, c0] = stops[s - 1]
          const [t1, c1] = stops[s]
          c = c0.clone().lerp(c1, (t - t0) / (t1 - t0))
          break
        }
      }
      colors.set([c.r, c.g, c.b], i * 3)
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    const mat = new THREE.MeshBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.92, blending: THREE.AdditiveBlending,
      depthWrite: false, side: THREE.DoubleSide, fog: false,
    })
    this.flames = new THREE.InstancedMesh(geo, mat, this.W * this.H)
    this.flames.count = 0
    this.flames.frustumCulled = false
    this.flames.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
    this.world.add(this.flames)
  }

  private buildTrucks(map: MapData) {
    const station = map.station
    for (let n = 0; n < map.crews.length; n++) {
      const g = new THREE.Group()
      const mk = (w: number, h: number, d: number, color: string, x: number, y: number, z = 0) => {
        const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), new THREE.MeshStandardMaterial({ color, roughness: 0.5 }))
        m.position.set(x, y, z)
        m.castShadow = true
        g.add(m)
        return m
      }
      mk(0.95, 0.4, 0.44, '#d42020', -0.12, 0.32)
      mk(0.34, 0.42, 0.44, '#a51616', 0.52, 0.33)
      mk(0.96, 0.06, 0.45, '#f5f5f5', -0.12, 0.27)
      mk(0.8, 0.05, 0.14, '#b8bec6', -0.15, 0.56)
      mk(0.2, 0.12, 0.46, '#262626', 0.52, 0.42, 0)
      const lightMat = new THREE.MeshBasicMaterial({ color: '#ff2a2a' })
      const bar = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.08, 0.32), lightMat)
      bar.position.set(0.52, 0.58, 0)
      g.add(bar)
      for (const [wx, wz] of [[-0.42, 0.22], [-0.42, -0.22], [0.42, 0.22], [0.42, -0.22]]) {
        const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.11, 0.08, 10).rotateX(Math.PI / 2), new THREE.MeshStandardMaterial({ color: '#111111' }))
        wheel.position.set(wx, 0.11, wz)
        g.add(wheel)
      }
      g.scale.setScalar(1.35)
      const sx = (station?.x ?? 0) + 0.5
      const sy = (station?.y ?? 0) + 0.5
      const [x, z] = this.toWorld(sx, sy)
      const p = new THREE.Vector3(x, this.heightAt(sx, sy), z)
      g.position.copy(p)
      const lineGeo = new THREE.BufferGeometry().setFromPoints([p, p])
      const line = new THREE.Line(lineGeo, new THREE.LineDashedMaterial({ color: '#38bdf8', dashSize: 0.8, gapSize: 0.5, transparent: true, opacity: 0.85 }))
      line.visible = false
      this.world.add(g, line)
      this.trucks.push({ group: g, light: lightMat, pos: p.clone(), goal: p.clone(), heading: 0, status: 'available', target: null, line })
    }
  }

  private makeBeacon(): Beacon {
    const group = new THREE.Group()
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.82, 1, 48).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: '#ff3b30', transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }),
    )
    const beamGeo = new THREE.CylinderGeometry(0.12, 0.3, 1, 14, 1, true).translate(0, 0.5, 0)
    const beam = new THREE.Mesh(
      beamGeo,
      new THREE.MeshBasicMaterial({ color: '#ff3b30', transparent: true, opacity: 0.3, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }),
    )
    group.add(ring, beam)
    group.visible = false
    this.scene.add(group)
    return { group, ring, beam }
  }

  private buildLabels(map: MapData) {
    const order: number[] = []
    for (const a of map.assets) {
      const el = document.createElement('div')
      el.className = `lbl k-${a.kind}`
      el.dataset.id = String(a.id)
      el.style.display = 'none'
      el.addEventListener('click', (ev) => {
        ev.stopPropagation()
        this.cb.onSelect(a.id)
      })
      this.labelsRoot.appendChild(el)
      this.labels.set(a.id, el)
      order.push(a.id)
    }
    this.labelOrder = order
  }

  // ---- per-tick updates ------------------------------------------------------------
  private updateTrees(grid: number[][]) {
    if (!this.trees.length) return
    const W = this.W
    const touched = new Set<number>()
    for (const [cell, list] of this.cellTrees) {
      const s = grid[(cell / W) | 0][cell % W]
      if (s === this.prevGrid[cell]) continue
      for (const [m, i] of list) {
        const t = this.trees[m]
        const base = t.base[i]
        if (s === CELL.BURNING || s === CELL.IGNITING) tmpC.setRGB(1.0, 0.42, 0.18)
        else if (s === CELL.BURNED) tmpC.setRGB(0.14, 0.12, 0.11)
        else if (s === CELL.SUPPRESSED) tmpC.setRGB(0.7 * base, 0.85 * base, 1.0 * base)
        else tmpC.setScalar(base)
        t.mesh.setColorAt(i, tmpC)
        tmpM.fromArray(t.mats, i * 16)
        if (s === CELL.BURNED) {
          tmpM.decompose(tmpV, tmpQ, tmpS)
          tmpM.compose(tmpV, tmpQ, tmpS.set(tmpS.x * 0.6, tmpS.y * 0.8, tmpS.z * 0.6))
        }
        t.mesh.setMatrixAt(i, tmpM)
        touched.add(m)
      }
    }
    for (const m of touched) {
      this.trees[m].mesh.instanceMatrix.needsUpdate = true
      if (this.trees[m].mesh.instanceColor) this.trees[m].mesh.instanceColor!.needsUpdate = true
    }
  }

  private updateFlames(grid: number[][]) {
    const map = this.map!
    const { W, H } = this
    const spots: FlameSpot[] = []
    let sx = 0
    let sz = 0
    for (let y = 0; y < H; y++) {
      const row = grid[y]
      for (let x = 0; x < W; x++) {
        const s = row[x]
        if (s !== CELL.BURNING && s !== CELL.IGNITING) continue
        const f = map.fuel[y][x]
        const top = this.cellTop[y * W + x]
        let h = f === FUEL.GRASS ? 0.55 : f === FUEL.SHRUB ? 0.95 : f === FUEL.FOREST ? 1.7 : top + 1.1
        let w = f === FUEL.GRASS ? 0.7 : f === FUEL.SHRUB ? 0.85 : 1.0
        const hazmat = f === FUEL.HAZMAT
        if (hazmat) {
          h = 2.8
          w = 1.15
        }
        if (s === CELL.IGNITING) {
          h *= 0.5
          w *= 0.7
        }
        const jx = 0.3 + 0.4 * P.hash2(x, y * 3)
        const jy = 0.3 + 0.4 * P.hash2(x * 5, y)
        const [wx, wz] = this.toWorld(x + jx, y + jy)
        spots.push({ x: wx, z: wz, y: this.heightAt(x + jx, y + jy), h, w, phase: P.hash2(x, y) * 6.28, hazmat })
        sx += wx
        sz += wz
      }
    }
    this.flameSpots = spots
    this.fireCount = spots.length
    if (spots.length) this.fireCentroid.set(sx / spots.length, 0, sz / spots.length)
    this.fireCentroid.y = spots.length ? this.heightAt(this.fireCentroid.x + W / 2, this.fireCentroid.z + H / 2) + 5 : 0
  }

  /** Remember this tick's grid so the next tick only touches cells that changed. */
  private rememberGrid(grid: number[][]) {
    const { W, H } = this
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) this.prevGrid[y * W + x] = grid[y][x]
  }

  private updateBuildings(status: number[]) {
    const touched = new Set<THREE.InstancedMesh>()
    for (let id = 0; id < status.length; id++) {
      if (status[id] === this.assetStatus[id]) continue
      this.assetStatus[id] = status[id]
      for (const p of this.piecesByAsset.get(id) ?? []) {
        this.applyPiece(p, status[id])
        touched.add(p.mesh)
      }
    }
    for (const m of touched) {
      m.instanceMatrix.needsUpdate = true
      if (m.instanceColor) m.instanceColor.needsUpdate = true
    }
  }

  private updateTrucks(sim: SimPayload) {
    const city = sim.city!
    const map = this.map!
    city.crews.forEach((c, i) => {
      const t = this.trucks[i]
      if (!t) return
      const [x, z] = this.toWorld(c.x, c.y)
      t.goal.set(x, this.heightAt(c.x, c.y), z)
      t.status = c.status
      t.target = c.target
      const a = c.target != null ? map.assets[c.target] : null
      if (a && c.status === 'en_route') {
        const [ax, az] = this.toWorld(a.x + a.w / 2, a.y + a.h / 2)
        const end = new THREE.Vector3(ax, this.heightAt(a.x + a.w / 2, a.y + a.h / 2) + 0.3, az)
        t.line.geometry.setFromPoints([t.goal.clone().setY(t.goal.y + 0.3), end])
        t.line.computeLineDistances()
        t.line.visible = true
      } else t.line.visible = false
    })
  }

  private placeBeacons() {
    const map = this.map!
    const colors: Record<string, string> = { critical: '#ff3b30', high: '#ff9f0a' }
    this.beacons.forEach((b, i) => {
      const t = this.beaconTargets[i]
      if (!t) {
        b.group.visible = false
        return
      }
      const a = map.assets[t.id]
      const [x, z] = this.toWorld(a.x + a.w / 2, a.y + a.h / 2)
      b.group.position.set(x, this.heightAt(a.x + a.w / 2, a.y + a.h / 2) + 0.05, z)
      const r = Math.max(a.w, a.h) * 0.62 + 0.6
      b.ring.scale.set(r, 1, r)
      b.beam.scale.set(1, 9 + (t.level === 'critical' ? 5 : 0), 1)
      ;(b.ring.material as THREE.MeshBasicMaterial).color.set(colors[t.level] ?? '#ff9f0a')
      ;(b.beam.material as THREE.MeshBasicMaterial).color.set(colors[t.level] ?? '#ff9f0a')
      b.group.userData.level = t.level
      b.group.visible = true
    })
  }

  private explode(assetId: number) {
    const a = this.map?.assets[assetId]
    if (!a) return
    const cx = a.x + a.w / 2
    const cy = a.y + a.h / 2
    const [x, z] = this.toWorld(cx, cy)
    const y = this.heightAt(cx, cy)
    const flash = new THREE.Mesh(
      new THREE.SphereGeometry(1, 24, 16),
      new THREE.MeshBasicMaterial({ color: '#ffb347', transparent: true, opacity: 1, blending: THREE.AdditiveBlending, depthWrite: false }),
    )
    flash.position.set(x, y + 1, z)
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.85, 1, 64).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: '#ffd28a', transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }),
    )
    ring.position.set(x, y + 0.1, z)
    this.world.add(flash, ring)
    this.flashes.push({ mesh: flash, ring, t: 0 })
    for (let i = 0; i < 160; i++) {
      const ang = Math.random() * Math.PI * 2
      const sp = 3 + Math.random() * 6
      this.embers.emit(x, y + 1, z, Math.cos(ang) * sp, 4 + Math.random() * 6, Math.sin(ang) * sp, 1.5 + Math.random() * 2, 0.35, 0, 1, 0.6 + Math.random() * 0.3, 0.2, 1)
    }
  }

  private updateLabels(sim: SimPayload) {
    const city = sim.city
    const map = this.map
    if (!city || !map) return
    const st = city.assets.status
    for (const a of map.assets) {
      const el = this.labels.get(a.id)
      if (!el) continue
      const status = STATUS_NAMES[st[a.id]] ?? 'safe'
      const people = city.assets.occupants[a.id]
      const rescue = city.assets.needs_rescue[a.id]
      const icon = a.kind === 'road' ? CAR_SVG : PERSON_SVG
      let html = ''
      if (FACILITIES.has(a.kind)) {
        html = `<span class="lbl-name">${escapeHtml(a.name)}</span>`
        html += status === 'destroyed' && people === 0
          ? '<span class="lbl-count">Destroyed</span>'
          : `<span class="lbl-count">${icon}${people}</span>`
      } else {
        html = status === 'destroyed' && people === 0 ? '<span class="lbl-count">✕</span>' : `<span class="lbl-count">${icon}${people}</span>`
      }
      if (rescue > 0) html += `<span class="lbl-sos">${rescue} need help</span>`
      if (el.dataset.html !== html) {
        el.innerHTML = html
        el.dataset.html = html
      }
      el.dataset.people = String(people)
      el.dataset.status = status
      const empty = people === 0 && status !== 'destroyed' ? ' lbl-empty' : ''
      const cls = `lbl k-${a.kind} st-${status}${empty}${a.id === this.selected ? ' lbl-sel' : ''}`
      if (el.className !== cls) el.className = cls
    }
  }

  private refreshLabelClasses() {
    for (const [id, el] of this.labels) el.classList.toggle('lbl-sel', id === this.selected)
  }

  // ---- frame loop ---------------------------------------------------------------------
  private loop = () => {
    if (this.disposed || this.paused) return
    this.raf = requestAnimationFrame(this.loop)
    this.timer.update()
    const realDt = Math.min(0.5, this.timer.getDelta())
    const dt = Math.min(0.05, realDt)   // effects step at most 50 ms so a slow frame doesn't jump
    const t = this.timer.getElapsed()
    if (this.fly) {
      // Camera moves use wall-clock time so they take 0.9 s whatever the frame rate.
      this.fly.t = Math.min(1, this.fly.t + realDt / 0.9)
      const e = 1 - Math.pow(1 - this.fly.t, 3)
      this.camera.position.lerpVectors(this.fly.from, this.fly.to, e)
      this.controls.target.lerpVectors(this.fly.tFrom, this.fly.tTo, e)
      if (this.fly.t >= 1) this.fly = null
      this.labelsDirty = true
    }
    this.controls.update()
    this.animateFlames(t)
    this.emitParticles(dt)
    this.animateTrucks(dt, t)
    this.animateBeacons(t)
    this.animateFlashes(dt)
    this.smoke.update(dt, this.wind.x, this.wind.y)
    this.embers.update(dt, this.wind.x * 1.6, this.wind.y * 1.6)
    this.water.update(dt, 0, 0)
    this.fireLight.intensity = this.fireCount ? Math.min(160, 18 + Math.sqrt(this.fireCount) * 9) * (0.85 + 0.15 * Math.sin(t * 17)) : 0
    this.fireLight.position.copy(this.fireCentroid)
    if (this.labelsDirty) this.positionLabels()
    this.renderer.render(this.scene, this.camera)
  }

  private animateFlames(t: number) {
    const f = this.flames
    if (!f) return
    const spots = this.flameSpots
    f.count = spots.length
    for (let i = 0; i < spots.length; i++) {
      const s = spots[i]
      const k = 0.8 + 0.22 * Math.sin(t * 9 + s.phase) + 0.1 * Math.sin(t * 23 + s.phase * 1.7)
      const wk = 0.92 + 0.1 * Math.sin(t * 13 + s.phase)
      tmpQ.setFromAxisAngle(UP, s.phase + t * 0.6)
      tmpM.compose(tmpV.set(s.x, s.y, s.z), tmpQ, tmpS.set(s.w * wk, s.h * k, s.w * wk))
      f.setMatrixAt(i, tmpM)
    }
    f.instanceMatrix.needsUpdate = true
  }

  private emitParticles(dt: number) {
    const spots = this.flameSpots
    if (!spots.length) return
    const smokeRate = Math.min(420, 30 + spots.length * 1.4)
    const n = Math.floor(smokeRate * dt + Math.random())
    for (let i = 0; i < n; i++) {
      const s = spots[(Math.random() * spots.length) | 0]
      // Wood and vegetation smoke is grey-brown (darker at night); fuel and battery fires give black smoke.
      const g = s.hazmat ? 0.07 : 0.18 + 0.24 * this.daylight + Math.random() * 0.14
      this.smoke.emit(
        s.x + (Math.random() - 0.5) * 0.6, s.y + s.h * 0.9, s.z + (Math.random() - 0.5) * 0.6,
        (Math.random() - 0.5) * 0.3, 1.1 + Math.random() * 0.9, (Math.random() - 0.5) * 0.3,
        5 + Math.random() * 4, 1.1 + s.w, 1.9 + Math.random() * 0.9,
        g * 1.06, g, g * 0.92, s.hazmat ? 0.6 : 0.22 + 0.08 * this.daylight,
      )
    }
    const emberN = Math.floor(Math.min(160, spots.length * 0.4) * dt + Math.random())
    for (let i = 0; i < emberN; i++) {
      const s = spots[(Math.random() * spots.length) | 0]
      this.embers.emit(
        s.x, s.y + s.h * 0.7, s.z,
        (Math.random() - 0.5) * 0.8, 1.5 + Math.random() * 1.8, (Math.random() - 0.5) * 0.8,
        1.2 + Math.random() * 1.6, 0.18 + Math.random() * 0.12, 0,
        1, 0.55 + Math.random() * 0.3, 0.15, 1,
      )
    }
  }

  private animateTrucks(dt: number, t: number) {
    const map = this.map
    const k = 1 - Math.exp(-dt * 4)
    for (const tr of this.trucks) {
      const dx = tr.goal.x - tr.pos.x
      const dz = tr.goal.z - tr.pos.z
      if (dx * dx + dz * dz > 0.0004) tr.heading = Math.atan2(-dz, dx)
      tr.pos.lerp(tr.goal, k)
      tr.group.position.copy(tr.pos)
      const turn = tr.heading - tr.group.rotation.y
      tr.group.rotation.y += Math.atan2(Math.sin(turn), Math.cos(turn)) * k   // shortest way round
      const busy = tr.status !== 'available'
      tr.light.color.set(busy ? (Math.floor(t * 4) % 2 ? '#ff2020' : '#2f6bff') : '#552222')
      if (tr.status === 'working' && tr.target != null && map) {
        const a = map.assets[tr.target]
        const [ax, az] = this.toWorld(a.x + a.w / 2, a.y + a.h / 2)
        const n = Math.floor(70 * dt + Math.random())
        for (let i = 0; i < n; i++) {
          const ex = ax + (Math.random() - 0.5) * a.w * 0.8 - tr.pos.x
          const ez = az + (Math.random() - 0.5) * a.h * 0.8 - tr.pos.z
          const dist = Math.hypot(ex, ez) || 1
          const flight = 0.7 + dist * 0.06
          // vy = g * t / 2 so the arc lands on the target after `flight` seconds (g = 9.5).
          this.water.emit(tr.pos.x, tr.pos.y + 0.8, tr.pos.z, ex / flight, 4.75 * flight, ez / flight, flight, 0.22, 0.05, 0.45, 0.75, 1.0, 0.8)
        }
      }
    }
  }

  private animateBeacons(t: number) {
    for (const b of this.beacons) {
      if (!b.group.visible) continue
      const critical = b.group.userData.level === 'critical'
      const pulse = 0.5 + 0.5 * Math.sin(t * (critical ? 6 : 3.5))
      ;(b.ring.material as THREE.MeshBasicMaterial).opacity = 0.45 + 0.5 * pulse
      ;(b.beam.material as THREE.MeshBasicMaterial).opacity = 0.14 + 0.2 * pulse
      const s = 1 + 0.08 * pulse
      b.group.scale.set(s, 1, s)
    }
  }

  private animateFlashes(dt: number) {
    this.flashes = this.flashes.filter((f) => {
      f.t += dt
      const p = f.t / 1.1
      if (p >= 1) {
        this.world.remove(f.mesh, f.ring)
        disposeTree(f.mesh)
        disposeTree(f.ring)
        return false
      }
      f.mesh.scale.setScalar(1 + p * 7)
      ;(f.mesh.material as THREE.MeshBasicMaterial).opacity = 1 - p
      f.ring.scale.setScalar(1 + p * 16)
      ;(f.ring.material as THREE.MeshBasicMaterial).opacity = 0.9 * (1 - p)
      return true
    })
  }

  // ---- labels ------------------------------------------------------------------------------
  private positionLabels() {
    this.labelsDirty = false
    const map = this.map
    if (!map) return
    const rect = this.container.getBoundingClientRect()
    const w = rect.width
    const h = rect.height
    const dist = this.camera.position.distanceTo(this.controls.target)
    const size = Math.max(this.W, this.H)
    const far = size * 0.95
    const mid = size * 0.55
    const tgt = this.controls.target
    let shown = 0
    for (const id of this.labelOrder) {
      const el = this.labels.get(id)!
      const a = map.assets[id]
      const people = Number(el.dataset.people ?? a.occupants0)
      const [cx, cz] = this.toWorld(a.x + a.w / 2, a.y + a.h / 2)
      let visible = false
      if (id === this.selected || id === this.hovered) visible = true
      else if (FACILITIES.has(a.kind)) visible = a.kind !== 'park' || dist < far * 1.25
      else if (el.dataset.status === 'destroyed') visible = false   // the charred ruin says it already
      else if (a.kind === 'commercial') visible = dist < far
      else {
        const near = Math.hypot(cx - tgt.x, cz - tgt.z) < dist * 0.95
        if (a.kind === 'house') visible = dist < mid && near
        else if (a.kind === 'road') visible = dist < mid * 0.8 && near && people > 0
      }
      if (visible && shown < 220) {
        tmpV.set(cx, this.assetTop[id] + 0.25, cz).project(this.camera)
        if (tmpV.z > 1 || tmpV.x < -1.15 || tmpV.x > 1.15 || tmpV.y < -1.15 || tmpV.y > 1.15) visible = false
        else {
          const px = (tmpV.x * 0.5 + 0.5) * w
          const py = (-tmpV.y * 0.5 + 0.5) * h
          el.style.transform = `translate3d(${px.toFixed(1)}px, ${py.toFixed(1)}px, 0) translate(-50%, -100%)`
          shown++
        }
      } else visible = false
      const d = visible ? '' : 'none'
      if (el.style.display !== d) el.style.display = d
    }
  }

  // ---- interaction -----------------------------------------------------------------------------
  private pick(clientX: number, clientY: number): { asset: number | null; cell: [number, number] | null } {
    const rect = this.renderer.domElement.getBoundingClientRect()
    this.pointer.set(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1)
    this.raycaster.setFromCamera(this.pointer, this.camera)
    let cell: [number, number] | null = null
    const hits = this.raycaster.intersectObjects(this.pickables, false)
    for (const hit of hits) {
      const owned = this.pieceLookup.get(hit.object)
      if (owned && hit.instanceId != null) return { asset: owned[hit.instanceId].asset, cell: null }
    }
    if (this.terrain) {
      const th = this.raycaster.intersectObject(this.terrain, false)[0]
      if (th) {
        const x = Math.floor(th.point.x + this.W / 2)
        const y = Math.floor(th.point.z + this.H / 2)
        if (x >= 0 && y >= 0 && x < this.W && y < this.H) {
          cell = [x, y]
          const id = this.assetGrid[y * this.W + x]
          return { asset: id >= 0 ? id : null, cell }
        }
      }
    }
    return { asset: null, cell }
  }

  private onPointerMove = (e: PointerEvent) => {
    if (e.buttons) return
    const { asset } = this.pick(e.clientX, e.clientY)
    if (asset !== this.hovered) {
      this.hovered = asset
      this.placeBox(this.hoverBox, asset !== this.selected ? asset : null)
      this.labelsDirty = true
    }
    this.cb.onHover(asset, e.clientX, e.clientY)
  }

  private onPointerDown = (e: PointerEvent) => {
    this.downAt = { x: e.clientX, y: e.clientY }
  }

  private onPointerUp = (e: PointerEvent) => {
    if (!this.downAt) return
    const moved = Math.hypot(e.clientX - this.downAt.x, e.clientY - this.downAt.y)
    this.downAt = null
    if (moved > 5 || e.button !== 0) return
    const { asset, cell } = this.pick(e.clientX, e.clientY)
    if (this.igniteMode && cell) this.cb.onCellClick(cell[0], cell[1])
    else this.cb.onSelect(asset)
  }

  private onPointerLeave = () => {
    this.hovered = null
    this.hoverBox.visible = false
    this.cb.onHover(null, 0, 0)
  }

  private onDoubleClick = (e: MouseEvent) => {
    const { asset } = this.pick(e.clientX, e.clientY)
    if (asset != null) this.focus(asset)
  }

  private placeBox(box: THREE.LineSegments, id: number | null) {
    const a = id != null ? this.map?.assets[id] : undefined
    if (!a) {
      box.visible = false
      return
    }
    const [x, z] = this.toWorld(a.x + a.w / 2, a.y + a.h / 2)
    const ground = this.heightAt(a.x + a.w / 2, a.y + a.h / 2)
    const top = Math.max(0.4, this.assetTop[a.id] - ground)
    box.position.set(x, ground, z)
    box.scale.set(a.w + 0.3, top + 0.3, a.h + 0.3)
    box.visible = true
  }

  // ---- lighting & sizing ----------------------------------------------------------------------
  private setTimeOfDay(hour: number) {
    const h = ((hour % 24) + 24) % 24
    const day = Math.max(0, Math.sin(((h - 6) / 12) * Math.PI))     // 0 at night, 1 at noon
    this.daylight = day
    const dusk = Math.max(0, 1 - Math.abs(h - 18.5) / 2) + Math.max(0, 1 - Math.abs(h - 6.5) / 1.5)
    const size = Math.max(this.W, this.H) || 100
    const ang = ((h - 6) / 12) * Math.PI
    this.sun.position.set(Math.cos(ang) * size * 0.8, Math.max(0.25, Math.sin(ang)) * size * 0.9 + size * 0.2, size * 0.45)
    this.sun.target.position.set(0, 0, 0)
    const sunColor = new THREE.Color('#fff4e0').lerp(new THREE.Color('#ffb070'), Math.min(1, dusk))
    this.sun.color.copy(day > 0.02 ? sunColor : new THREE.Color('#9fb6ff'))
    this.sun.intensity = day > 0.02 ? 0.6 + 2.0 * day : 0.38
    this.hemi.intensity = 0.28 + 0.65 * day
    this.hemi.color.set(day > 0.02 ? '#cfe0ff' : '#5a6f9e')
    this.renderer.toneMappingExposure = 0.95 + 0.15 * day
  }

  private resize() {
    const w = Math.max(1, this.container.clientWidth)
    const h = Math.max(1, this.container.clientHeight)
    this.renderer.setSize(w, h, false)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    const scale = h / (2 * Math.tan((this.camera.fov * Math.PI) / 360))
    this.smoke.setScale(scale)
    this.embers.setScale(scale)
    this.water.setScale(scale)
    this.labelsDirty = true
  }
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}
