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
  Box3,
  DirectionalLight,
  Object3D,
  PerspectiveCamera,
  Scene,
  Vector3,
  WebGLRenderer
} from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import { subscribe } from '../../visual/motionScheduler.js'
import { PERSONA_POSE_BASE } from './personaStates.js'
import { createLipSync, VISEMES } from './useLipSync.js'

const FPS = 30
const BLINK_INTERVAL = 3.2
const BLINK_DURATION = 0.24
const BREATH_SPEED = 1.35
const BREATH_AMPLITUDE = 0.012
const POSE_BONES = ['head', 'chest', 'leftUpperArm', 'rightUpperArm']

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
  scene.add(ambient, key, rim)

  let vrm = null
  let disposed = false
  let elapsed = 0
  let blinkClock = 0
  let stopLoop = () => {}
  let onFirstFrame = null
  const firstFrame = new Promise((resolve) => {
    onFirstFrame = resolve
  })

  let poseNodes = {}
  let poseCurrent = clonePose(PERSONA_POSE_BASE)
  let expressionWeights = {}
  let gazeCurrent = { yaw: 0, pitch: 0 }
  let activeProfile = null
  let fadeTau = 0.12
  let lookTarget = null
  let modelHeight = 1.6

  const lipSync = createLipSync()
  const visemeValues = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 }

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
    for (const bone of POSE_BONES) {
      poseNodes[bone] = model.humanoid?.getNormalizedBoneNode(bone) ?? null
    }
    poseCurrent = clonePose(PERSONA_POSE_BASE)

    if (model.lookAt) {
      lookTarget = new Object3D()
      scene.add(lookTarget)
      model.lookAt.target = lookTarget
    }
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

    if (poseNodes.chest) {
      poseNodes.chest.rotation.set(poseCurrent.chest.x + breath, poseCurrent.chest.y, poseCurrent.chest.z + jitter)
    }
    if (poseNodes.head) {
      poseNodes.head.rotation.set(poseCurrent.head.x + nod, poseCurrent.head.y + sway, poseCurrent.head.z)
    }
    for (const bone of ['leftUpperArm', 'rightUpperArm']) {
      const node = poseNodes[bone]
      if (!node) continue
      node.rotation.set(poseCurrent[bone].x, poseCurrent[bone].y, poseCurrent[bone].z)
    }
  }

  function applyGaze(k) {
    const target = activeProfile?.gaze ?? { yaw: 0, pitch: 0 }
    gazeCurrent.yaw += (target.yaw - gazeCurrent.yaw) * k
    gazeCurrent.pitch += (target.pitch - gazeCurrent.pitch) * k
    if (!lookTarget) return
    lookTarget.position.set(gazeCurrent.yaw * 0.8, modelHeight * 0.55 + gazeCurrent.pitch * 0.8, 2.2)
  }

  function applyExpressions(k) {
    const manager = vrm?.expressionManager
    if (!manager) return
    const targets = activeProfile?.expressions ?? {}
    const names = new Set([...Object.keys(expressionWeights), ...Object.keys(targets)])
    for (const name of names) {
      if (!manager.getExpression(name)) continue
      const current = expressionWeights[name] ?? 0
      const target = targets[name] ?? 0
      const next = current + (target - current) * k
      expressionWeights[name] = next
      manager.setValue(name, next)
    }
  }

  function applyBlink(dt) {
    const manager = vrm?.expressionManager
    if (!manager?.getExpression('blink')) return
    blinkClock += dt
    const cycle = blinkClock % BLINK_INTERVAL
    const weight = cycle < BLINK_DURATION ? Math.sin((cycle / BLINK_DURATION) * Math.PI) : 0
    manager.setValue('blink', weight)
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

  function step(frameMs) {
    if (!vrm || disposed) return
    // motionScheduler 回调给的是毫秒，这里统一换成秒（three / 插值都按秒）
    const dt = Math.min(frameMs, 100) / 1000
    elapsed += dt
    const motion = activeProfile?.motion ?? {}
    const k = easeFactor(dt)

    applyPose(k, motion)
    applyGaze(k)
    applyExpressions(k)
    applyVisemes(lipSync.update(dt))
    applyBlink(dt)

    vrm.update(dt)
    renderer.render(scene, camera)
    if (onFirstFrame) {
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

      // VRM 0.x 朝向为 -Z，先转成 +Z 再取景，否则会拍到后脑
      if (loaded.meta?.metaVersion === '0') VRMUtils.rotateVRM0(loaded)

      loaded.scene.traverse((object) => {
        object.frustumCulled = false
      })
      scene.add(loaded.scene)
      vrm = loaded
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
    renderer.dispose()
    // 主动释放上下文，并保证不触发上面的降级回调（监听已移除）
    renderer.forceContextLoss()
  }

  function stats() {
    return {
      drawCalls: renderer.info.render.calls,
      geometries: renderer.info.memory.geometries,
      textures: renderer.info.memory.textures,
      expressions: vrm?.expressionManager?.expressions?.map((item) => item.expressionName) ?? []
    }
  }

  return {
    ready,
    dispose,
    stats,
    resize,
    setState,
    attachAudio: (element) => lipSync.attachAudio(element),
    resumeAudio: () => lipSync.resume(),
    speakText: (text, options) => lipSync.speak(text, options),
    stopSpeaking: () => lipSync.silence()
  }
}
