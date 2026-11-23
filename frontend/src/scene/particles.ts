import * as THREE from 'three'

export interface ParticleBehaviour {
  capacity: number
  texture: THREE.Texture
  blending: THREE.Blending
  /** Upward acceleration (smoke rises), world units / s^2. */
  buoyancy: number
  /** Downward acceleration (embers, water), world units / s^2. */
  gravity: number
  /** How quickly horizontal velocity follows the wind (1/s). */
  windFollow: number
  /** Share of life spent fading in. */
  fadeIn: number
  /** 0..1 random brightness flicker (embers). */
  flicker: number
}

const VERTEX = /* glsl */ `
attribute float aSize;
attribute float aAlpha;
attribute vec3 aColor;
varying float vAlpha;
varying vec3 vColor;
uniform float uScale;
void main() {
  vAlpha = aAlpha;
  vColor = aColor;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = max(1.0, aSize * uScale / -mv.z);
  gl_Position = projectionMatrix * mv;
}`

const FRAGMENT = /* glsl */ `
uniform sampler2D uMap;
varying float vAlpha;
varying vec3 vColor;
void main() {
  float a = texture2D(uMap, gl_PointCoord).a * vAlpha;
  if (a < 0.004) discard;
  gl_FragColor = vec4(vColor, a);
}`

/** A pool of GPU point sprites with per-particle size, colour and alpha. */
export class Particles {
  readonly points: THREE.Points
  private b: ParticleBehaviour
  private geom: THREE.BufferGeometry
  private material: THREE.ShaderMaterial
  private pos: Float32Array
  private vel: Float32Array
  private col: Float32Array
  private size: Float32Array
  private alpha: Float32Array
  private age: Float32Array
  private life: Float32Array
  private grow: Float32Array
  private peak: Float32Array
  private next = 0
  private live = 0

  constructor(b: ParticleBehaviour) {
    this.b = b
    const n = b.capacity
    this.pos = new Float32Array(n * 3)
    this.vel = new Float32Array(n * 3)
    this.col = new Float32Array(n * 3)
    this.size = new Float32Array(n)
    this.alpha = new Float32Array(n)
    this.age = new Float32Array(n)
    this.life = new Float32Array(n)
    this.grow = new Float32Array(n)
    this.peak = new Float32Array(n)
    this.geom = new THREE.BufferGeometry()
    this.geom.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage))
    this.geom.setAttribute('aColor', new THREE.BufferAttribute(this.col, 3).setUsage(THREE.DynamicDrawUsage))
    this.geom.setAttribute('aSize', new THREE.BufferAttribute(this.size, 1).setUsage(THREE.DynamicDrawUsage))
    this.geom.setAttribute('aAlpha', new THREE.BufferAttribute(this.alpha, 1).setUsage(THREE.DynamicDrawUsage))
    this.geom.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e5)
    this.material = new THREE.ShaderMaterial({
      uniforms: { uMap: { value: b.texture }, uScale: { value: 400 } },
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      transparent: true,
      depthWrite: false,
      blending: b.blending,
    })
    this.points = new THREE.Points(this.geom, this.material)
    this.points.frustumCulled = false
  }

  get count() {
    return this.live
  }

  /** Point size scale: viewport height in pixels / (2 * tan(fov / 2)). */
  setScale(scale: number) {
    this.material.uniforms.uScale.value = scale
  }

  emit(
    x: number, y: number, z: number,
    vx: number, vy: number, vz: number,
    life: number, size: number, grow: number,
    r: number, g: number, bl: number, alpha: number,
  ) {
    const i = this.next
    this.next = (this.next + 1) % this.b.capacity
    const j = i * 3
    this.pos[j] = x
    this.pos[j + 1] = y
    this.pos[j + 2] = z
    this.vel[j] = vx
    this.vel[j + 1] = vy
    this.vel[j + 2] = vz
    this.col[j] = r
    this.col[j + 1] = g
    this.col[j + 2] = bl
    this.size[i] = size
    this.grow[i] = grow
    this.age[i] = 0
    this.life[i] = life
    this.peak[i] = alpha
    this.alpha[i] = 0
  }

  update(dt: number, windX: number, windZ: number) {
    const { buoyancy, gravity, windFollow, fadeIn, flicker, capacity } = this.b
    const follow = Math.min(1, windFollow * dt)
    let live = 0
    for (let i = 0; i < capacity; i++) {
      const life = this.life[i]
      if (life <= 0) continue
      const age = this.age[i] + dt
      if (age >= life) {
        this.life[i] = 0
        this.alpha[i] = 0
        continue
      }
      live++
      this.age[i] = age
      const j = i * 3
      this.vel[j] += (windX - this.vel[j]) * follow
      this.vel[j + 2] += (windZ - this.vel[j + 2]) * follow
      this.vel[j + 1] += (buoyancy - gravity) * dt
      this.pos[j] += this.vel[j] * dt
      this.pos[j + 1] += this.vel[j + 1] * dt
      this.pos[j + 2] += this.vel[j + 2] * dt
      this.size[i] += this.grow[i] * dt
      const t = age / life
      let a = t < fadeIn ? t / fadeIn : 1 - (t - fadeIn) / (1 - fadeIn)
      if (flicker > 0) a *= 1 - flicker + flicker * Math.random()
      this.alpha[i] = Math.max(0, a) * this.peak[i]
    }
    this.live = live
    const attrs = this.geom.attributes
    attrs.position.needsUpdate = true
    attrs.aColor.needsUpdate = true
    attrs.aSize.needsUpdate = true
    attrs.aAlpha.needsUpdate = true
  }

  clear() {
    this.life.fill(0)
    this.alpha.fill(0)
    this.live = 0
  }

  dispose() {
    this.geom.dispose()
    this.material.dispose()
  }
}

/** Soft round sprite drawn on a canvas (smoke puff or glowing ember). */
export function spriteTexture(kind: 'smoke' | 'ember'): THREE.Texture {
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')!
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  if (kind === 'smoke') {
    g.addColorStop(0, 'rgba(255,255,255,0.9)')
    g.addColorStop(0.45, 'rgba(255,255,255,0.45)')
    g.addColorStop(1, 'rgba(255,255,255,0)')
  } else {
    g.addColorStop(0, 'rgba(255,255,255,1)')
    g.addColorStop(0.25, 'rgba(255,255,255,0.85)')
    g.addColorStop(1, 'rgba(255,255,255,0)')
  }
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  const tex = new THREE.CanvasTexture(canvas)
  tex.needsUpdate = true
  return tex
}
