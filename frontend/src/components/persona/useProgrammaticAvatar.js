/**
 * 程序化深海生物发光数字人（零外部资产、零许可风险）。
 *
 * 接口与 useVrmModel.js 完全对齐，可在 AgentPersona.vue 里直接互换 mode。
 * 设计依据：docs/design/agent-avatar-3d-v1/PROGRAMMATIC.md
 */
import {
  AdditiveBlending,
  AmbientLight,
  BackSide,
  CapsuleGeometry,
  Color,
  DoubleSide,
  DirectionalLight,
  Group,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  PerspectiveCamera,
  RingGeometry,
  Scene,
  SphereGeometry,
  TorusGeometry,
  WebGLRenderer
} from 'three'
import { subscribe } from '../../visual/motionScheduler.js'
import { PERSONA_STATE_PROFILES as PROFILES } from './personaStates.js'
import { createFrameBudget, frameDeltaSeconds } from './frameBudget.js'
import { createLipSync } from './useLipSync.js'

const FPS = 30
const TAU = Math.PI * 2

/** 青蓝/粉紫调色板，与 design-system 的深海体系一致 */
const PALETTE = {
  cyan: new Color(0x2496ed),
  cyanSoft: new Color(0x7ad7f5),
  cyanGlow: new Color(0xb4ebff),
  purple: new Color(0xb48cf7),
  amber: new Color(0xffb454),
  red: new Color(0xff6b6b),
  green: new Color(0x5fd3a5),
  white: new Color(0xffffff)
}

/** 状态 accent → 发光色，让七状态在无表情/无姿态的几何体上也能一眼区分 */
const ACCENT_COLOR = {
  neutral: 'cyan',
  primary: 'cyanSoft',
  warning: 'amber',
  danger: 'red',
  success: 'green'
}

/**
 * @param {object} options
 * @param {HTMLCanvasElement} options.canvas
 * @param {HTMLElement} options.container
 * @param {string} [options.id] 调度器订阅 id
 * @param {() => void} [options.onContextLost]
 */
export function createProgrammaticAvatar({ canvas, container, id = 'agent-persona-programmatic', onContextLost }) {
  const renderer = new WebGLRenderer({
    canvas,
    alpha: true,
    antialias: true,
    powerPreference: 'high-performance'
  })
  renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, 2))
  renderer.setClearAlpha(0)

  const scene = new Scene()
  const camera = new PerspectiveCamera(35, 1, 0.1, 30)
  camera.position.set(0, 0.3, 4.2)
  camera.lookAt(0, 0.4, 0)

  const ambient = new AmbientLight(0x9fd8ee, 0.8)
  const rim = new DirectionalLight(0x2496ed, 0.6)
  rim.position.set(-1.5, 1, -1)
  scene.add(ambient, rim)

  // —— 形体构建 —— //
  const root = new Group()
  scene.add(root)

  // 头部：半透明青蓝球体
  const head = new Mesh(
    new SphereGeometry(0.34, 32, 32),
    new MeshStandardMaterial({
      color: PALETTE.cyanSoft,
      emissive: PALETTE.cyan,
      emissiveIntensity: 0.5,
      transparent: true,
      opacity: 0.82,
      roughness: 0.35,
      metalness: 0.1
    })
  )
  head.position.y = 0.55

  // 头部外层发光壳
  const headGlow = new Mesh(
    new SphereGeometry(0.42, 24, 24),
    new MeshBasicMaterial({
      color: PALETTE.cyan,
      transparent: true,
      opacity: 0.12,
      blending: AdditiveBlending,
      side: BackSide
    })
  )
  headGlow.position.y = 0.55

  // 核心光点（头部内脉冲）
  const core = new Mesh(
    new SphereGeometry(0.08, 16, 16),
    new MeshBasicMaterial({ color: PALETTE.cyanGlow })
  )
  core.position.y = 0.55

  // 双眼
  const eyeMat = new MeshBasicMaterial({ color: PALETTE.white })
  const eyeL = new Mesh(new SphereGeometry(0.04, 12, 12), eyeMat)
  const eyeR = new Mesh(new SphereGeometry(0.04, 12, 12), eyeMat)
  eyeL.position.set(-0.12, 0.62, 0.3)
  eyeR.position.set(0.12, 0.62, 0.3)

  // 身体
  const body = new Mesh(
    new CapsuleGeometry(0.22, 0.5, 8, 16),
    new MeshStandardMaterial({
      color: PALETTE.cyanSoft,
      emissive: PALETTE.cyan,
      emissiveIntensity: 0.35,
      transparent: true,
      opacity: 0.7,
      roughness: 0.4
    })
  )
  body.position.y = 0

  // 光环
  const halo = new Mesh(
    new TorusGeometry(0.5, 0.018, 8, 48),
    new MeshBasicMaterial({
      color: PALETTE.cyanSoft,
      transparent: true,
      opacity: 0.6,
      blending: AdditiveBlending
    })
  )
  halo.position.y = 0.95
  halo.rotation.x = Math.PI / 2.6

  // 口型（环形，按 aa 权重开合）
  const mouth = new Mesh(
    new RingGeometry(0.03, 0.08, 16),
    new MeshBasicMaterial({
      color: PALETTE.cyanGlow,
      transparent: true,
      opacity: 0.9,
      side: DoubleSide,
      blending: AdditiveBlending
    })
  )
  mouth.position.set(0, 0.46, 0.3)
  mouth.scale.y = 0.1 // 闭嘴

  // 触须（3 条，从身体向下延伸）
  const tentacles = []
  const tentacleMat = new MeshBasicMaterial({
    color: PALETTE.purple,
    transparent: true,
    opacity: 0.7,
    blending: AdditiveBlending
  })
  for (let i = 0; i < 3; i++) {
    const t = new Mesh(new CapsuleGeometry(0.02, 0.5, 4, 8), tentacleMat)
    const angle = (i - 1) * 0.32
    t.position.set(Math.sin(angle) * 0.15, -0.35 - i * 0.04, Math.cos(angle) * 0.05)
    t.rotation.z = -angle
    tentacles.push({ mesh: t, phase: i * 1.2, baseAngle: angle })
  }

  root.add(head, headGlow, core, eyeL, eyeR, body, halo, mouth, ...tentacles.map((t) => t.mesh))

  // —— 状态与动画 —— //
  let disposed = false
  let elapsed = 0
  let activeProfile = PROFILES.idle
  let fadeTau = 0.12
  const lipSync = createLipSync()
  let stopLoop = () => {}
  let onFirstFrame = null
  const firstFrame = new Promise((resolve) => {
    onFirstFrame = resolve
  })
  const now = () => globalThis.performance?.now?.() ?? Date.now()
  let firstFrameMs = 0
  let renderedFrames = 0
  let lastStepAt = 0
  const frameSamples = []
  let degraded = false

  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(resize) : null
  observer?.observe(container)

  function resize() {
    const width = container.clientWidth || 200
    const height = container.clientHeight || 260
    renderer.setSize(width, height, false)
    camera.aspect = width / height
    camera.updateProjectionMatrix()
  }
  resize()

  function easeFactor(dt) {
    if (fadeTau <= 0) return 1
    return 1 - Math.exp(-dt / fadeTau)
  }

  function applyStateColor(profile) {
    const accent = profile.accent
    const target = ACCENT_COLOR[accent] ?? profile.color ?? 'cyan'
    const c = PALETTE[target] ?? PALETTE.cyan
    head.material.emissive.lerp(c, 0.15)
    body.material.emissive.lerp(c, 0.12)
    halo.material.color.lerp(c, 0.1)
  }

  function applyPose(k, dt) {
    const motion = activeProfile.motion ?? {}
    const breath = Math.sin(elapsed * (motion.breathSpeed ?? 1.35)) * (motion.breathAmp ?? 0.018)
    const nod = motion.nod ? Math.sin(elapsed * TAU * motion.nod.freq) * motion.nod.amp : 0
    const sway = motion.sway ? Math.sin(elapsed * TAU * motion.sway.freq) * motion.sway.amp : 0

    head.rotation.x += ((nod ?? 0) - head.rotation.x) * k
    head.rotation.y += ((sway ?? 0) - head.rotation.y) * k
    core.position.y = 0.55 + breath * 0.5
    head.scale.setScalar(1 + breath * 0.04)
    headGlow.scale.setScalar(1 + breath * 0.06)

    // 光环转速
    const haloSpeed = motion.haloSpeed ?? 0.3
    halo.rotation.z += haloSpeed * dt

    // 触须摆动
    const tentacleAmp = motion.tentacleAmp ?? 0.15
    for (const t of tentacles) {
      const wave = Math.sin(elapsed * 2.4 + t.phase) * tentacleAmp
      t.mesh.rotation.z = t.baseAngle + wave
    }
  }

  function applyVisemes() {
    const weights = lipSync.update(1 / FPS)
    const aa = weights.aa ?? 0
    mouth.scale.y = 0.1 + aa * 2.2
    mouth.material.opacity = 0.5 + aa * 0.5
  }

  function step() {
    if (disposed) return
    const timestamp = now()
    const interval = lastStepAt ? timestamp - lastStepAt : 16
    lastStepAt = timestamp
    const dt = frameDeltaSeconds(interval)
    elapsed += dt
    const k = easeFactor(dt)
    const frameStart = timestamp

    applyStateColor(activeProfile)
    applyPose(k, dt)
    applyVisemes()

    renderer.render(scene, camera)

    const cost = now() - frameStart
    renderedFrames += 1
    frameSamples.push(cost)
    if (frameSamples.length > 90) frameSamples.shift()
    if (renderedFrames === 1) {
      firstFrameMs = cost
      onFirstFrame?.()
      onFirstFrame = null
    }
  }

  stopLoop = subscribe(step, { fps: FPS, id })

  // frameBudget 沿用：持续慢帧降级
  createFrameBudget({
    onDegrade: () => {
      degraded = true
      renderer.setPixelRatio(1)
    }
  })

  function handleLost(event) {
    event.preventDefault()
    stopLoop()
    stopLoop = () => {}
    onContextLost?.()
  }
  canvas.addEventListener('webglcontextlost', handleLost, false)

  function setState(profile, { fade } = {}) {
    activeProfile = profile ?? PROFILES.idle
    const ms = fade ?? 350
    fadeTau = ms > 0 ? ms / 1000 / 3 : 0
  }

  function stats() {
    const frame = frameSamples.length
      ? {
          avg: frameSamples.reduce((a, b) => a + b, 0) / frameSamples.length,
          max: Math.max(...frameSamples),
          p50: frameSamples.sort((a, b) => a - b)[Math.floor(frameSamples.length * 0.5)] ?? 0,
          p90: frameSamples.sort((a, b) => a - b)[Math.floor(frameSamples.length * 0.9)] ?? 0
        }
      : { avg: 0, max: 0, p50: 0, p90: 0 }
    return {
      drawCalls: renderer.info.render.calls,
      geometries: renderer.info.memory.geometries,
      textures: renderer.info.memory.textures,
      expressions: [],
      firstFrameMs: Math.round(firstFrameMs),
      frameAvgMs: Number(frame.avg.toFixed(2)),
      frameMaxMs: Number(frame.max.toFixed(2)),
      frameP50Ms: Number(frame.p50.toFixed(2)),
      frameP90Ms: Number(frame.p90.toFixed(2)),
      pixelRatio: renderer.getPixelRatio(),
      degraded,
      frames: renderedFrames,
      modelBytes: 0,
      heapMB: globalThis.performance?.memory?.usedJSHeapSize
        ? Number((globalThis.performance.memory.usedJSHeapSize / 1048576).toFixed(1))
        : null
    }
  }

  function dispose() {
    if (disposed) return
    disposed = true
    stopLoop()
    stopLoop = () => {}
    lipSync.dispose()
    onFirstFrame?.()
    onFirstFrame = null
    observer?.disconnect()
    canvas.removeEventListener('webglcontextlost', handleLost, false)
    root.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose()
      if (obj.material) {
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material]
        mats.forEach((m) => m.dispose())
      }
    })
    renderer.dispose()
    renderer.forceContextLoss()
  }

  // 首帧后 ready
  firstFrame.then(() => {}).catch(() => {})

  return {
    ready: firstFrame,
    dispose,
    stats,
    resize,
    setState,
    attachAudio: (element) => lipSync.attachAudio(element),
    resumeAudio: () => lipSync.resume(),
    speakText: (text, options) => lipSync.speak(text, options),
    seekSpeech: (charIndex) => lipSync.seek(charIndex),
    stopSpeaking: () => lipSync.silence()
  }
}
