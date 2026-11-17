/**
 * VRM 加载、渲染与状态驱动（纯逻辑，不依赖 Vue）。
 *
 * 职责边界：renderer / camera / 灯的装配、模型加载、状态 → 表情/姿态/视线/节奏的插值、
 * 以及资源释放。数据表在 personaStates.js，这里只做「把数值变成动作」。
 *
 * 参考实现（只学做法，不复制代码）：pixiv/ChatVRM（MIT）的加载顺序与相机取景思路。
 */
import {
  AmbientLight,
  AdditiveBlending,
  BackSide,
  Box3,
  BufferAttribute,
  BufferGeometry,
  CanvasTexture,
  CircleGeometry,
  Color,
  DirectionalLight,
  DoubleSide,
  Group,
  LinearFilter,
  Mesh,
  MeshBasicMaterial,
  Object3D,
  PerspectiveCamera,
  Points,
  PointsMaterial,
  RingGeometry,
  Scene,
  CylinderGeometry,
  Vector3,
  WebGLRenderer
} from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import { subscribe } from '../../visual/motionScheduler.js'
import { PERSONA_POSE_BASE } from './personaStates.js'
import {
  sampleGesture,
  sampleGestureExpressions,
  PERSONA_GESTURES,
  PERSONA_GESTURE_NAMES
} from './personaGestures.js'
import { createFrameBudget, frameDeltaSeconds } from './frameBudget.js'
import { createLipSync, VISEMES } from './useLipSync.js'

const FPS = 30
// 眨眼：早期是固定 3.2s 一次的节拍器，机械感明显。改为「随机间隔 + 偶发连眨」，
// 间隔分布贴近真人（2.2~5.4s），约 12% 的概率紧接一次二次眨眼。
const BLINK_DURATION = 0.24
const BLINK_GAP = 0.16
const BLINK_INTERVAL_MIN = 2.2
const BLINK_INTERVAL_SPAN = 3.2
const BLINK_DOUBLE_CHANCE = 0.12
const BREATH_SPEED = 1.35
const BREATH_AMPLITUDE = 0.012

/** 口型通道的平均开合度，用来判断「是否真的在发声」 */
function visemeEnergy(weights) {
  let sum = 0
  for (const name of VISEMES) sum += weights[name] ?? 0
  return VISEMES.length ? sum / VISEMES.length : 0
}

// 手势层需要更细的上肢：前臂/手/颈。状态姿态只用到其中前四个（POSE_BONES），
// 其余骨骼为手势专用，无手势时保持基准零旋转。
const GESTURE_BONES = ['neck', 'leftLowerArm', 'rightLowerArm', 'leftHand', 'rightHand']
const POSE_BONES = ['head', 'chest', 'leftUpperArm', 'rightUpperArm', 'leftLowerArm', 'rightLowerArm']
const RIG_BONES = [...POSE_BONES, ...GESTURE_BONES]

// 降级门槛见 frameBudget.js：CPU 成本 > 20ms，或真实渲染间隔 ≥ 60ms，连续 2s
const FRAME_SAMPLES = 90

const TAU = Math.PI * 2

function clonePose(source) {
  return Object.fromEntries(
    Object.entries(source).map(([bone, rotation]) => [bone, { ...rotation }])
  )
}

/**
 * @param {object} options
 * @param {HTMLCanvasElement} options.canvas
 * @param {HTMLElement} options.container
 * @param {string} options.modelUrl
 * @param {string} [options.id] 调度器订阅 id，同一页面多实例时须唯一
 * @param {() => void} [options.onContextLost]
 */
export function createVrmStage({ canvas, container, modelUrl, id = 'agent-persona', onContextLost }) {
  const renderer = new WebGLRenderer({
    canvas,
    alpha: true,
    antialias: true,
    powerPreference: 'high-performance'
  })
  renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, 2))
  renderer.setClearAlpha(0)

  const scene = new Scene()
  const camera = new PerspectiveCamera(30, 1, 0.1, 30)

  const ambient = new AmbientLight(0x9fd8ee, 1.15)
  const key = new DirectionalLight(0xffffff, 1.45)
  key.position.set(0.8, 1.7, 1.4)
  const rim = new DirectionalLight(0x2496ed, 0.85)
  rim.position.set(-1.3, 1.1, -1.1)
  // 深海氛围补光：下方微弱青蓝光 + 侧后方弱粉紫（呼应登录水母），让轮廓有层次
  const fillOcean = new DirectionalLight(0x7AD7F5, 0.4)
  fillOcean.position.set(0.2, -0.6, 1.1)
  fillOcean.target.position.set(0, 0.6, 0)
  const backGlow = new DirectionalLight(0xb48cf7, 0.25)
  backGlow.position.set(-0.6, 0.9, -1.8)
  backGlow.target.position.set(0, 0.7, 0)
  scene.add(ambient, key, rim, fillOcean, backGlow)

  // ------------------------------------------------------------------
  // 环境空间层（蒸馏 PetLive「角色住在场景里 + 情绪光影」叙事）。
  // 只往场景里 add 物体，VRM 模型加载/骨骼/口型/视线管线零改动。
  // 组成：脚下地毯 + 情绪光环（随状态色 lerp）+ 深海气泡微光 + 弧形观景窗。
  // ------------------------------------------------------------------
  const GLOW_IDLE = '#3fb9c9'
  const envGroup = new Group()
  const glowRingColor = new Color(GLOW_IDLE)
  const glowTarget = new Color(GLOW_IDLE)
  const backdropTint = new Color('#16324f')
  const backdropTarget = new Color('#16324f')
  const ambientTarget = new Color(0x9fd8ee)
  const rimTarget = new Color(0x2496ed)
  const AMBIENT_BASE = new Color(0x9fd8ee)
  const RIM_BASE = new Color(0x2496ed)
  let bubbles = null
  let bubbleData = null

  /** 气泡 sprite：canvas 径向渐变，中心亮边缘透明，配 additive blending 有微光感 */
  function makeBubbleTexture() {
    const size = 64
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = size
    const ctx = canvas.getContext('2d')
    const gradient = ctx.createRadialGradient(size / 2, size / 2, 2, size / 2, size / 2, size / 2)
    gradient.addColorStop(0, 'rgba(255,255,255,0.95)')
    gradient.addColorStop(0.45, 'rgba(190,235,255,0.5)')
    gradient.addColorStop(1, 'rgba(190,235,255,0)')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)
    const texture = new CanvasTexture(canvas)
    texture.minFilter = LinearFilter
    return texture
  }

  /**
   * 弧形观景窗背景：中性灰渐变纹理 + 窗棂剪影 + 斜光柱，
   * 材质 color 做状态色调 tint（灰度纹理 × 彩色 tint），变色只 lerp material.color。
   */
  function makeBackdropTexture() {
    const width = 1024
    const height = 512
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    // 中性明度渐变（上亮下暗），后续靠 material.color 上色
    const vertical = ctx.createLinearGradient(0, 0, 0, height)
    vertical.addColorStop(0, 'rgb(190,200,210)')
    vertical.addColorStop(0.55, 'rgb(120,135,150)')
    vertical.addColorStop(1, 'rgb(38,52,68)')
    ctx.fillStyle = vertical
    ctx.fillRect(0, 0, width, height)
    // 斜光柱：从上方斜射的两道宽光带
    for (const [x, w] of [[180, 150], [620, 200]]) {
      const beam = ctx.createLinearGradient(x, 0, x + w * 0.8, height)
      beam.addColorStop(0, 'rgba(255,255,255,0.35)')
      beam.addColorStop(1, 'rgba(255,255,255,0)')
      ctx.fillStyle = beam
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x + w, 0)
      ctx.lineTo(x + w * 1.8, height)
      ctx.lineTo(x + w * 0.8, height)
      ctx.closePath()
      ctx.fill()
    }
    // 窗棂：4 根竖框 + 1 根横框，深色半透明
    ctx.fillStyle = 'rgba(20,30,42,0.55)'
    for (const x of [120, 360, 640, 900]) ctx.fillRect(x, 0, 14, height)
    ctx.fillRect(0, height * 0.42, width, 12)
    const texture = new CanvasTexture(canvas)
    texture.minFilter = LinearFilter
    return texture
  }

  function createEnvironment() {
    // 脚下地毯：暗青圆盘，接住角色的「立足感」
    const rug = new Mesh(
      new CircleGeometry(1.55, 48),
      new MeshBasicMaterial({ color: 0x0d2a3f, transparent: true, opacity: 0.5, depthWrite: false })
    )
    rug.rotation.x = -Math.PI / 2
    rug.position.y = 0.001
    // 情绪光环：颜色随状态 lerp，呼吸式明暗
    const ring = new Mesh(
      new RingGeometry(0.52, 1.18, 64),
      new MeshBasicMaterial({
        color: glowRingColor,
        transparent: true,
        opacity: 0.5,
        depthWrite: false,
        side: DoubleSide,
        blending: AdditiveBlending
      })
    )
    ring.rotation.x = -Math.PI / 2
    ring.position.y = 0.004
    envGroup.add(rug, ring)
    // 弧形观景窗：大圆柱 BackSide 内壁，开口朝相机侧；灰度纹理 × 状态 tint
    const backdrop = new Mesh(
      new CylinderGeometry(6, 6, 9, 48, 1, true, Math.PI * 0.35, Math.PI * 1.3),
      new MeshBasicMaterial({
        map: makeBackdropTexture(),
        side: BackSide,
        transparent: true,
        opacity: 0.92,
        color: backdropTint,
        depthWrite: false
      })
    )
    backdrop.position.y = 2.6
    envGroup.add(backdrop)
    // 深海气泡微光：60 个上升光点（降级时隐藏）
    const count = 60
    const positions = new Float32Array(count * 3)
    bubbleData = Array.from({ length: count }, (_, index) => ({
      baseX: (Math.random() - 0.5) * 4.4,
      z: (Math.random() - 0.5) * 2.6 - 0.6,
      phase: Math.random() * TAU,
      speed: 0.12 + Math.random() * 0.22,
      driftFreq: 0.4 + Math.random() * 0.8,
      driftAmp: 0.06 + Math.random() * 0.1
    }))
    bubbleData.forEach((bubble, index) => {
      positions[index * 3] = bubble.baseX
      positions[index * 3 + 1] = Math.random() * 2.6
      positions[index * 3 + 2] = bubble.z
    })
    const geometry = new BufferGeometry()
    geometry.setAttribute('position', new BufferAttribute(positions, 3))
    bubbles = new Points(
      geometry,
      new PointsMaterial({
        map: makeBubbleTexture(),
        size: 0.13,
        transparent: true,
        opacity: 0.75,
        depthWrite: false,
        blending: AdditiveBlending,
        sizeAttenuation: true
      })
    )
    envGroup.add(bubbles)
    scene.add(envGroup)
  }

  /** 状态色下发：光环主色 + 背景暗化 tint + 环境光微调目标，三处同步缓动 */
  function setEnvironmentGlow(hex) {
    glowTarget.set(hex)
    backdropTarget.copy(glowTarget).lerp(new Color('#101d2e'), 0.68)
    ambientTarget.copy(AMBIENT_BASE).lerp(glowTarget, 0.3)
    rimTarget.copy(RIM_BASE).lerp(glowTarget, 0.45)
  }

  function applyEnvironment(dt) {
    // 统一指数缓动（与姿态 fadeTau 同思路），换状态时光色平滑过渡
    const k = 1 - Math.exp(-dt / 0.45)
    glowRingColor.lerp(glowTarget, k)
    backdropTint.lerp(backdropTarget, k)
    ambient.color.lerp(ambientTarget, k)
    rim.color.lerp(rimTarget, k)
    // 光环呼吸
    const ring = envGroup.children[1]
    ring.material.color.copy(glowRingColor)
    ring.material.opacity = 0.4 + Math.sin(elapsed * 1.6) * 0.1
    // 气泡上升 + 左右摆动
    if (bubbles?.visible) {
      const positions = bubbles.geometry.attributes.position
      for (let index = 0; index < bubbleData.length; index += 1) {
        const bubble = bubbleData[index]
        let y = positions.getY(index) + bubble.speed * dt
        if (y > 2.7) y = 0.02
        positions.setY(index, y)
        positions.setX(index, bubble.baseX + Math.sin(elapsed * bubble.driftFreq + bubble.phase) * bubble.driftAmp)
      }
      positions.needsUpdate = true
    }
  }

  function disposeEnvironment() {
    if (!envGroup) return
    scene.remove(envGroup)
    envGroup.traverse((object) => {
      const materials = Array.isArray(object.material) ? object.material : object.material ? [object.material] : []
      for (const material of materials) {
        for (const slot of ['map']) material[slot]?.dispose?.()
        material.dispose()
      }
      object.geometry?.dispose()
    })
  }

  createEnvironment()

  let vrm = null
  let disposed = false
  let elapsed = 0
  let blinkClock = 0
  // 眨眼排程：blinkStart < 0 表示当前没在眨眼；blinkQueue 是剩余的连眨次数
  let blinkStart = -1
  let blinkAt = BLINK_INTERVAL_MIN
  let blinkQueue = 0
  // 微跳视：眼球不会完全静止，每隔一小段时间随机跳一点，避免"死盯"
  const saccade = { yaw: 0, pitch: 0, nextAt: 0 }
  let stopLoop = () => {}
  let onFirstFrame = null
  const firstFrame = new Promise((resolve) => {
    onFirstFrame = resolve
  })

  let poseNodes = {}
  let poseCurrent = clonePose(PERSONA_POSE_BASE)
  let expressionWeights = {}
  let gazeCurrent = { yaw: 0, pitch: 0 }
  // 指针朝向：鼠标悬停在桌宠画面内时，头与上半身朝光标方向轻转（限幅，不会转到背面）
  const pointerLook = { x: 0, y: 0, active: false }
  const lookCurrent = { yaw: 0, pitch: 0 }
  const LOOK_YAW = 0.3 // 头+躯干合计最大偏转 ≈ 17°，侧头但不偏离镜头
  const LOOK_PITCH = 0.1
  let activeProfile = null
  let fadeTau = 0.12
  let lookTarget = null
  let modelHeight = 1.6

  // 手势层（personaGestures）：一次性动作，叠加在状态姿态之上，播完自动回零
  let gestureName = null
  let gestureClock = 0
  let gestureOnEnd = null

  const lipSync = createLipSync()
  const visemeValues = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 }

  const now = () => globalThis.performance?.now?.() ?? Date.now()
  const createdAt = now()
  let firstFrameMs = 0
  let renderedFrames = 0
  let lastStepAt = 0
  const frameSamples = []
  const frameBudget = createFrameBudget()
  let degraded = false
  let modelBytes = 0

  function resize() {
    const width = Math.max(container.clientWidth, 1)
    const height = Math.max(container.clientHeight, 1)
    renderer.setSize(width, height, false)
    camera.aspect = width / height
    camera.updateProjectionMatrix()
  }

  function frameCamera() {
    const box = new Box3().setFromObject(vrm.scene)
    const size = box.getSize(new Vector3())
    modelHeight = Math.max(size.y, 0.1)
    const fov = (camera.fov * Math.PI) / 180
    // 取景：全身入画，留一点头顶空间；相机高度对齐胸口
    const distance = (modelHeight * 0.62) / Math.tan(fov / 2)
    camera.position.set(0, modelHeight * 0.58, distance)
    camera.lookAt(0, modelHeight * 0.52, 0)
    camera.updateProjectionMatrix()
  }

  function initialiseRig(model) {
    poseNodes = {}
    for (const bone of RIG_BONES) {
      poseNodes[bone] = model.humanoid?.getNormalizedBoneNode(bone) ?? null
    }
    poseCurrent = clonePose(PERSONA_POSE_BASE)

    if (model.lookAt) {
      lookTarget = new Object3D()
      scene.add(lookTarget)
      model.lookAt.target = lookTarget
    }
  }

  /**
   * 海洋/生物发光主题色调覆盖：遍历所有材质，对 diffuse 做青蓝色调偏移，
   * 并给衣服/头发类材质加低强度 emissive，让模型融入项目深海体系。
   * 不换资产、不换贴图、只改材质数值，零合规风险。
   */
  const OCEAN_HUE_TARGET = 0.58 // 青蓝 hsl.h = 209° 左右
  const OCEAN_HUE_DRIFT = 0.08  // 每个材质偏移幅度
  const OCEAN_EMISSIVE_INTENSITY = 0.18
  const OCEAN_EMISSIVE_SATURATION = 0.35

  function applyOceanTone(model) {
    model.scene.traverse((object) => {
      const materials = Array.isArray(object.material)
        ? object.material
        : object.material
          ? [object.material]
          : []
      for (const material of materials) {
        if (!material || material.isMeshBasicMaterial) continue
        // 1) diffuse color 青蓝偏移：用 hsl 不破坏明度，只转色相
        if (material.color && material.color.isColor) {
          const hsl = { h: 0, s: 0, l: 0 }
          material.color.getHSL(hsl)
          const drift = (hsl.h - OCEAN_HUE_TARGET + 1 + OCEAN_HUE_DRIFT) % 1
          const targetHue = drift < OCEAN_HUE_DRIFT * 2 ? OCEAN_HUE_TARGET : hsl.h
          const newSaturation = Math.min(0.6, hsl.s * 0.85 + 0.04)
          const newLightness = Math.max(0.12, Math.min(0.88, hsl.l * 1.02))
          material.color.setHSL(targetHue, newSaturation, newLightness)
        }
        // 2) emissive 给衣服/头发材质加低强度青蓝发光
        if (!material.emissive) continue
        const hsl = { h: 0, s: 0, l: 0 }
        material.emissive.getHSL?.(hsl)
        // 只有黑色/极低 emissive 才覆盖——已有自发光材质（如 UI 配件）不动
        if (hsl.l > 0.02) continue
        const tone = new Color().setHSL(OCEAN_HUE_TARGET, OCEAN_EMISSIVE_SATURATION, OCEAN_EMISSIVE_INTENSITY)
        material.emissive.copy(tone)
        material.emissiveIntensity = Math.max(material.emissiveIntensity ?? 0, 0.6)
      }
    })
  }

  function easeFactor(dt) {
    if (fadeTau <= 0) return 1
    return 1 - Math.exp(-dt / fadeTau)
  }

  function applyPose(k, motion) {
    const poseDelta = activeProfile?.pose ?? {}
    for (const bone of POSE_BONES) {
      const node = poseNodes[bone]
      if (!node) continue
      const base = PERSONA_POSE_BASE[bone]
      const delta = poseDelta[bone] ?? {}
      const current = poseCurrent[bone]
      current.x += (base.x + (delta.x ?? 0) - current.x) * k
      current.y += (base.y + (delta.y ?? 0) - current.y) * k
      current.z += (base.z + (delta.z ?? 0) - current.z) * k
    }

    const breath =
      Math.sin(elapsed * (motion.breathSpeed ?? BREATH_SPEED)) * (motion.breathAmp ?? BREATH_AMPLITUDE)
    const nod = motion.nod ? Math.sin(elapsed * TAU * motion.nod.freq) * motion.nod.amp : 0
    const sway = motion.sway ? Math.sin(elapsed * TAU * motion.sway.freq) * motion.sway.amp : 0
    const jitter = motion.jitter
      ? ((Math.sin(elapsed * 27) + Math.sin(elapsed * 31.7)) / 2) * motion.jitter
      : 0

    // 指针朝向用同一套指数缓动：悬停时轻转过去，移出后自然回正
    const lookYawTarget = pointerLook.active ? pointerLook.x * LOOK_YAW : 0
    const lookPitchTarget = pointerLook.active ? pointerLook.y * LOOK_PITCH : 0
    lookCurrent.yaw += (lookYawTarget - lookCurrent.yaw) * k
    lookCurrent.pitch += (lookPitchTarget - lookCurrent.pitch) * k

    if (poseNodes.chest) {
      poseNodes.chest.rotation.set(
        poseCurrent.chest.x + breath,
        poseCurrent.chest.y + lookCurrent.yaw * 0.35,
        poseCurrent.chest.z + jitter
      )
    }
    if (poseNodes.head) {
      poseNodes.head.rotation.set(
        poseCurrent.head.x + nod + lookCurrent.pitch,
        poseCurrent.head.y + sway + lookCurrent.yaw * 0.65,
        poseCurrent.head.z
      )
    }
    for (const bone of ['leftUpperArm', 'rightUpperArm', 'leftLowerArm', 'rightLowerArm']) {
      const node = poseNodes[bone]
      if (!node) continue
      node.rotation.set(poseCurrent[bone].x, poseCurrent[bone].y, poseCurrent[bone].z)
    }
    // 只由手势驱动的骨骼（颈、双手）每帧先清零，再叠加当帧手势增量。
    // 不清零会逐帧累加：思考/大笑等带 neck 的手势会把脖子越转越多，
    // 一秒钟就能转过头、手势结束后还停在背面（点「说」时最明显）。
    for (const bone of ['neck', 'leftHand', 'rightHand']) {
      poseNodes[bone]?.rotation.set(0, 0, 0)
    }
  }

  /**
   * 手势增量直接加在「状态姿态 + 呼吸/节律」的最终旋转上：
   * 关键帧首尾为零、smoothstep 缓动，叠加与退出都无跳变。
   */
  function applyGesture(sample) {
    if (!sample) return
    for (const bone in sample) {
      const node = poseNodes[bone]
      const delta = sample[bone]
      if (!node || !delta) continue
      node.rotation.x += delta.x
      node.rotation.y += delta.y
      node.rotation.z += delta.z
    }
  }

  function applyGaze(k) {
    const target = activeProfile?.gaze ?? { yaw: 0, pitch: 0 }
    gazeCurrent.yaw += (target.yaw - gazeCurrent.yaw) * k
    gazeCurrent.pitch += (target.pitch - gazeCurrent.pitch) * k
    if (elapsed >= saccade.nextAt) {
      saccade.yaw = (Math.random() - 0.5) * 0.05
      saccade.pitch = (Math.random() - 0.5) * 0.04
      saccade.nextAt = elapsed + 0.6 + Math.random() * 1.2
    }
    if (!lookTarget) return
    // 悬停时以视线为主跟随光标（头部只轻转），移出后回到状态视线
    const yaw = pointerLook.active ? lookCurrent.yaw * 4 : gazeCurrent.yaw
    const pitch = pointerLook.active ? lookCurrent.pitch * 3 : gazeCurrent.pitch
    lookTarget.position.set(
      (yaw + saccade.yaw) * 0.8,
      modelHeight * 0.55 + (pitch + saccade.pitch) * 0.8,
      2.2
    )
  }

  /**
   * 表情：状态表情（长期）+ 手势表情（一次性增量），clamp 到 1。
   * blink 不在这里写——它由 applyBlink 统一负责，否则两处互相覆盖会闪。
   */
  function applyExpressions(k, extra = {}) {
    const manager = vrm?.expressionManager
    if (!manager) return
    const targets = activeProfile?.expressions ?? {}
    const names = new Set([
      ...Object.keys(expressionWeights),
      ...Object.keys(targets),
      ...Object.keys(extra)
    ])
    for (const name of names) {
      if (name === 'blink') continue
      if (!manager.getExpression(name)) continue
      const current = expressionWeights[name] ?? 0
      const target = Math.min(1, (targets[name] ?? 0) + (extra[name] ?? 0))
      const next = current + (target - current) * k
      expressionWeights[name] = next
      manager.setValue(name, next)
    }
  }

  /**
   * 眨眼：随机间隔 + 偶发连眨；手势表情轨道给了 blink 权重时取 max，
   * 这样「打瞌睡闭眼」不会被自动眨眼抬开。
   */
  function applyBlink(dt, extra = 0) {
    const manager = vrm?.expressionManager
    if (!manager?.getExpression('blink')) return
    blinkClock += dt
    let weight = 0
    if (blinkStart < 0 && blinkClock >= blinkAt) {
      blinkStart = blinkClock
      blinkQueue = Math.random() < BLINK_DOUBLE_CHANCE ? 1 : 0
    }
    if (blinkStart >= 0) {
      const phase = blinkClock - blinkStart
      if (phase >= 0 && phase < BLINK_DURATION) {
        weight = Math.sin((phase / BLINK_DURATION) * Math.PI)
      } else if (phase >= BLINK_DURATION && blinkQueue > 0) {
        blinkQueue -= 1
        blinkStart = blinkClock + BLINK_GAP
      } else if (phase >= BLINK_DURATION) {
        blinkStart = -1
        blinkAt = blinkClock + BLINK_INTERVAL_MIN + Math.random() * BLINK_INTERVAL_SPAN
      }
    }
    manager.setValue('blink', Math.max(weight, extra))
  }

  /** 口型只写 aa/ih/ou/ee/oh 五个通道，不碰状态表情 */
  function applyVisemes(weights) {
    const manager = vrm?.expressionManager
    if (!manager) return
    for (const name of VISEMES) {
      if (!manager.getExpression(name)) continue
      const value = weights[name] ?? 0
      if (Math.abs(visemeValues[name] - value) < 0.002) continue
      visemeValues[name] = value
      manager.setValue(name, value)
    }
  }

  /**
   * 降级：关阴影、降贴图、停发丝物理，并把渲染分辨率降回 1x。
   * 只做一次，之后的帧时不再触发。
   */
  function degrade() {
    if (degraded) return
    degraded = true
    // 环境层降级：先停气泡粒子（顶点动画每帧写 buffer），保留静态光环/背景
    if (bubbles) bubbles.visible = false
    renderer.shadowMap.enabled = false
    renderer.setPixelRatio(1)
    if (vrm) {
      vrm.scene.traverse((object) => {
        const materials = Array.isArray(object.material)
          ? object.material
          : object.material
            ? [object.material]
            : []
        for (const material of materials) {
          for (const key of ['map', 'normalMap', 'emissiveMap', 'alphaMap']) {
            const texture = material[key]
            if (!texture) continue
            texture.anisotropy = 1
            texture.minFilter = LinearFilter
            texture.needsUpdate = true
          }
        }
      })
      // 发丝/裙摆的 spring bone 解算约占一帧的一小半，降级时直接停掉
      if (vrm.springBoneManager) vrm.springBoneManager.update = () => {}
    }
    resize()
  }

  function step() {
    if (!vrm || disposed) return
    // 用两次渲染的真实间隔做 dt：调度器跳帧时，它给的回调参数只是 rAF 间隔，
    // 拿它推进动画会让动作变慢；看门狗也必须看这个间隔，否则 GPU 瓶颈下永不降级。
    const timestamp = now()
    const interval = lastStepAt ? timestamp - lastStepAt : 16
    lastStepAt = timestamp
    const dt = frameDeltaSeconds(interval)
    elapsed += dt
    const motion = activeProfile?.motion ?? {}
    const k = easeFactor(dt)
    const frameStart = timestamp

    // 手势推进：按时长归一化采样；播完回零并回调，呼吸/眨眼照常
    let gestureSample = null
    let gestureExpressionSample = {}
    if (gestureName) {
      gestureClock += dt
      const gesture = PERSONA_GESTURES[gestureName]
      if (gesture) {
        gestureSample = sampleGesture(gesture, gestureClock)
        gestureExpressionSample = sampleGestureExpressions(gestureName, gestureClock)
        if (gestureClock >= gesture.duration) {
          const ended = gestureOnEnd
          gestureName = null
          gestureClock = 0
          gestureOnEnd = null
          ended?.()
        }
      } else {
        gestureName = null
        gestureClock = 0
        gestureOnEnd = null
      }
    }

    applyPose(k, motion)
    applyGesture(gestureSample)
    applyGaze(k)
    applyExpressions(k, gestureExpressionSample)
    const visemes = lipSync.update(dt)
    applyVisemes(visemes)
    // 说话时头部随音节轻微起伏：没有它，播报时只有嘴在动，脖子像被钉住
    if (poseNodes.head) {
      const energy = visemeEnergy(visemes)
      if (energy > 0.02) poseNodes.head.rotation.x += Math.sin(elapsed * 9.5) * 0.02 * energy
    }
    applyBlink(dt, gestureExpressionSample.blink ?? 0)
    // 环境层推进：光环呼吸/气泡上升/光色缓动（放渲染前，与模型同帧一致）
    applyEnvironment(dt)

    vrm.update(dt)
    renderer.render(scene, camera)

    const cost = now() - frameStart
    renderedFrames += 1
    frameSamples.push(cost)
    if (frameSamples.length > FRAME_SAMPLES) frameSamples.shift()
    // 门槛判定在 frameBudget.js；这里传真实渲染间隔，不能用调度器回调的 rAF 间隔
    if (frameBudget.sample(cost, interval)) degrade()

    if (onFirstFrame) {
      firstFrameMs = now() - createdAt
      onFirstFrame()
      onFirstFrame = null
    }
  }

  function handleLost(event) {
    event.preventDefault()
    stopLoop()
    stopLoop = () => {}
    onContextLost?.()
  }

  canvas.addEventListener('webglcontextlost', handleLost, false)

  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(resize) : null
  observer?.observe(container)
  resize()

  const loader = new GLTFLoader()
  loader.register((parser) => new VRMLoaderPlugin(parser))

  const ready = loader
    .loadAsync(modelUrl)
    .then((gltf) => {
      if (disposed) {
        VRMUtils.deepDispose(gltf.scene)
        return null
      }
      const loaded = gltf.userData.vrm
      if (!loaded) throw new Error('模型缺少 VRM 扩展，无法按 VRM 加载')

      // VRM 0.x 朝向为 -Z，先转成 +Z 再取景，否则会拍到后脑。
      // 判定不能只看 meta.metaVersion：部分 VRM0 资产（如 sendagaya-shino）的 meta
      // 里没有该字段，但 glTF 里仍带旧版 `VRM` 扩展；两者任一命中即按 0.x 处理。
      const isVrm0 = Boolean(gltf.parser?.json?.extensions?.VRM)
        || String(loaded.meta?.metaVersion ?? '') === '0'
      if (isVrm0) VRMUtils.rotateVRM0(loaded)

      loaded.scene.traverse((object) => {
        object.frustumCulled = false
      })
      scene.add(loaded.scene)
      vrm = loaded
      applyOceanTone(loaded)
      initialiseRig(loaded)
      frameCamera()
      resize()
      stopLoop = subscribe(step, { fps: FPS, id })
      return loaded
    })
    .then(async (loaded) => {
      if (!loaded) return null
      // 等第一帧真正画出来再宣布 ready，否则统计拿到的是 0
      await firstFrame
      return loaded
    })

  /**
   * 切换状态。fade 为毫秒：默认 350，error → recovering 传 1200。
   * 传 0 表示立即生效（首次上屏时用）。
   */
  function setState(profile, { fade } = {}) {
    activeProfile = profile ?? null
    const ms = fade ?? 350
    fadeTau = ms > 0 ? ms / 1000 / 3 : 0
    // 环境光色随状态同步切换（光环/背景/环境光三处 lerp 过渡）
    if (profile?.glow) setEnvironmentGlow(profile.glow)
  }

  /**
   * 播一段一次性手势（personaGestures 纯数据关键帧），叠加在当前状态姿态上。
   * @param {string} name PERSONA_GESTURES 的键（wave / nod / shake / bow / greet / laugh / tilt / stretch / sleep / cheer / shy / think / angry / applaud / shrug / salute / point / thumbUp / heart / shiver / facepalm / leanIn / leanBack / lookAround / sway / snap / deepBow / armsCrossed / handOnHip / pointUp / openArms / radioCall / signalStop / signalCover）
   * @param {{ onEnd?: () => void }} [options] 播完回调（被新手势覆盖时不回调）
   * @returns {boolean} false 表示手势名不存在
   */
  function playGesture(name, { onEnd } = {}) {
    if (!PERSONA_GESTURE_NAMES.includes(name)) return false
    gestureName = name
    gestureClock = 0
    gestureOnEnd = typeof onEnd === 'function' ? onEnd : null
    return true
  }

  function stopGesture() {
    gestureName = null
    gestureClock = 0
    gestureOnEnd = null
  }

  /**
   * 指针朝向：鼠标悬停在画面内时，让数字人朝光标方向轻转（头 + 上半身 + 视线）。
   * 传 null 表示指针移出，缓动回正。
   * @param {number|null} x 归一化横坐标：-1 最左，1 最右
   * @param {number} [y] 归一化纵坐标：-1 最下，1 最上
   */
  function setLookPoint(x, y = 0) {
    if (disposed) return
    if (x === null || x === undefined || !Number.isFinite(x)) {
      pointerLook.active = false
      pointerLook.x = 0
      pointerLook.y = 0
      return
    }
    pointerLook.active = true
    pointerLook.x = Math.max(-1, Math.min(1, x))
    pointerLook.y = Math.max(-1, Math.min(1, Number.isFinite(y) ? y : 0))
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
    if (lookTarget) {
      scene.remove(lookTarget)
      lookTarget = null
    }
    if (vrm) {
      scene.remove(vrm.scene)
      VRMUtils.deepDispose(vrm.scene)
      vrm = null
    }
    disposeEnvironment()
    renderer.dispose()
    // 主动释放上下文，并保证不触发上面的降级回调（监听已移除）
    renderer.forceContextLoss()
  }

  /** 从资源计时里取模型的实际传输体积，没有就退回文件大小 */
  function readModelBytes() {
    if (modelBytes) return modelBytes
    try {
      const absolute = new URL(modelUrl, globalThis.location?.href ?? 'http://localhost/').href
      const entry = globalThis.performance?.getEntriesByName?.(absolute)?.pop()
      if (entry?.encodedBodySize) modelBytes = entry.encodedBodySize
      else if (entry?.decodedBodySize) modelBytes = entry.decodedBodySize
    } catch {
      // 拿不到就返回 0，不阻塞
    }
    return modelBytes
  }

  function frameSummary() {
    if (!frameSamples.length) return { avg: 0, max: 0, p50: 0, p90: 0 }
    let sum = 0
    let max = 0
    for (const sample of frameSamples) {
      sum += sample
      if (sample > max) max = sample
    }
    const sorted = [...frameSamples].sort((a, b) => a - b)
    return {
      avg: sum / frameSamples.length,
      max,
      p50: sorted[Math.floor(sorted.length * 0.5)],
      p90: sorted[Math.floor(sorted.length * 0.9)]
    }
  }

  function stats() {
    const frame = frameSummary()
    const heap = globalThis.performance?.memory?.usedJSHeapSize
    return {
      drawCalls: renderer.info.render.calls,
      geometries: renderer.info.memory.geometries,
      textures: renderer.info.memory.textures,
      expressions: vrm?.expressionManager?.expressions?.map((item) => item.expressionName) ?? [],
      firstFrameMs: Math.round(firstFrameMs),
      frameAvgMs: Number(frame.avg.toFixed(2)),
      frameMaxMs: Number(frame.max.toFixed(2)),
      frameP50Ms: Number(frame.p50.toFixed(2)),
      frameP90Ms: Number(frame.p90.toFixed(2)),
      pixelRatio: renderer.getPixelRatio(),
      degraded,
      frames: renderedFrames,
      modelBytes: readModelBytes(),
      heapMB: heap ? Number((heap / 1048576).toFixed(1)) : null
    }
  }

  return {
    ready,
    dispose,
    stats,
    resize,
    setState,
    playGesture,
    stopGesture,
    setLookPoint,
    attachAudio: (element) => lipSync.attachAudio(element),
    resumeAudio: () => lipSync.resume(),
    speakText: (text, options) => lipSync.speak(text, options),
    speakTimeline: (text, timing) => lipSync.speakTimeline(text, timing),
    seekSpeech: (charIndex) => lipSync.seek(charIndex),
    stopSpeaking: () => lipSync.silence()
  }
}
