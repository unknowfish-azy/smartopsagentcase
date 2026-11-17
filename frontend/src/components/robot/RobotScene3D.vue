<template>
  <section class="rs3-wrap" aria-labelledby="rs3-title">
    <header class="rs3-head">
      <div>
        <p class="rs3-eyebrow">SCENE 3D · 真实遥测驱动</p>
        <h2 id="rs3-title">3D 态势</h2>
      </div>
      <div class="rs3-legend" aria-hidden="true">
        <span class="rs3-key"><i class="dot dot-route"></i>路点</span>
        <span class="rs3-key"><i class="dot dot-detour"></i>绕行点</span>
        <span class="rs3-key"><i class="dot dot-robot"></i>机器人</span>
      </div>
    </header>

    <!-- WebGL 3D 场：容器常驻用 v-show；WebGL 不可用 / 轻量模式 / 减少动态时降级静态 SVG -->
    <div v-show="webglReady && !staticMode" ref="host" class="rs3-stage" role="img" :aria-label="ariaLabel"></div>

    <div v-if="!webglReady || staticMode" class="rs3-stage rs3-stage--static" role="img" :aria-label="ariaLabel">
      <svg viewBox="0 0 560 200" class="rs3-static-svg" aria-hidden="true">
        <rect x="20" y="20" width="520" height="160" fill="none" stroke="var(--ds-hairline, #333)" stroke-width="1" />
        <polyline
          v-if="staticPoints.length > 1"
          :points="staticPolyline"
          fill="none" stroke="var(--ds-color-primary, #5b8cff)" stroke-width="1.5" stroke-dasharray="4 3"
        />
        <circle
          v-for="(p, i) in staticPoints" :key="`sp-${i}`"
          :cx="p.cx" :cy="p.cy" r="4"
          :fill="p.detour ? '#e3a008' : 'none'"
          :stroke="p.detour ? '#e3a008' : 'var(--ds-color-primary, #5b8cff)'" stroke-width="1.5"
        />
        <circle :cx="staticRobot.cx" :cy="staticRobot.cy" r="6" :fill="stale ? '#8a8f98' : 'var(--ds-color-text, #e8eaed)'" />
      </svg>
      <p class="rs3-static-note">{{ staticNote }}</p>
    </div>

    <p class="rs3-caption">{{ caption }}</p>
  </section>
</template>

<script setup>
/**
 * 机器人 3D 态势面（M8a 占位模型版）。
 *
 * 数据全部来自真实链路，不伪造：
 * - 位姿：父级 WebSocket 遥测 telemetry.pose（x/y/theta，theta 为角度制）；
 * - 路线：getRobotTasks 取该设备最新任务的 route，label 含「绕行」的点 = M7 重规划绕行点（橙色高亮）；
 * - 已走过路点按 task.progress 变暗；障碍过近时机头箭头变红（真实 obstacleDistance 驱动）。
 *
 * 机器人本体为占位几何体（按 formFactor 区分 CAR / SPIDER / 其他），真机模型 GLB 就位后
 * 在 buildPlaceholder 处替换 GLTFLoader 加载即可，场景逻辑零改动。
 *
 * 降级：WebGL 不可用 / 轻量视觉模式 / 减少动态模式 → 静态 SVG 俯视图（对齐 EngineField3D 惯例）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AmbientLight, AnimationMixer, BufferGeometry, BoxGeometry, CircleGeometry, Color, ConeGeometry,
  CylinderGeometry, DirectionalLight, GridHelper, Group, Line, LineBasicMaterial, Mesh,
  MeshBasicMaterial, PerspectiveCamera, Scene, Vector3, WebGLRenderer
} from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { isDegraded, subscribe } from '../../visual/motionScheduler.js'
import { isLightweightVisualMode, isReducedMotionMode } from '../../visual/visualMode.js'
import { getRobotTasks } from '../../api/robot'

const props = defineProps({
  telemetry: { type: Object, default: null },
  stale: { type: Boolean, default: true },
  deviceKey: { type: String, default: '' },
  formFactor: { type: String, default: 'CAR' },
  mode: { type: String, default: 'OFFLINE' }
})

const host = ref(null)
const webglReady = ref(false)
const reduced = ref(false)
const staticMode = computed(() => isLightweightVisualMode.value || isReducedMotionMode.value || isDegraded() || reduced.value)
const staticReason = computed(() => {
  if (reduced.value) return '减少动态'
  if (isLightweightVisualMode.value) return '轻量视觉模式'
  return 'WebGL 不可用'
})

const DETOUR_COLOR = 0xe3a008
const ROUTE_COLOR = 0x5b8cff

// ------------------------------------------------------------------
// 任务路线（真实 DB 数据）
// ------------------------------------------------------------------

const waypoints = ref([]) // [{x,y,theta,label,done,detour}]

async function loadRoute() {
  if (!props.deviceKey) { waypoints.value = []; return }
  try {
    const r = await getRobotTasks(props.deviceKey)
    const tasks = r?.data
    const latest = Array.isArray(tasks) && tasks.length ? tasks[0] : null
    if (!latest?.route) { waypoints.value = []; return }
    const raw = typeof latest.route === 'string' ? JSON.parse(latest.route) : latest.route
    if (!Array.isArray(raw)) { waypoints.value = []; return }
    const progress = Number(latest.progress) || 0
    waypoints.value = raw.map((p, i) => ({
      x: Number(p.x) || 0,
      y: Number(p.y) || 0,
      theta: Number(p.theta) || 0,
      label: String(p.label || ''),
      done: i < progress,
      detour: String(p.label || '').includes('绕行')
    }))
  } catch {
    /* 任务接口不可用时路线留空，如实显示 */
    waypoints.value = []
  }
}

watch(() => props.deviceKey, loadRoute, { immediate: true })
/* 任务进度变化（执行中 progress 上涨）时刷新已完成路点 */
watch(() => props.telemetry, () => {
  /* 遥测每次到达都轻量核对一次最新任务的 progress（低频任务接口由下方节流保护） */
  scheduleRouteRefresh()
})

let routeRefreshTimer = null
function scheduleRouteRefresh() {
  if (routeRefreshTimer) return
  routeRefreshTimer = window.setTimeout(() => {
    routeRefreshTimer = null
    loadRoute()
  }, 5000)
}

const ariaLabel = computed(() => {
  const pose = props.telemetry?.pose
  const pos = pose ? `机器人位于 x=${Number(pose.x).toFixed(1)} y=${Number(pose.y).toFixed(1)}` : '等待遥测'
  const detour = waypoints.value.filter(p => p.detour).length
  return `3D 态势：${pos}，路线 ${waypoints.value.length} 个路点${detour ? `，含 ${detour} 个重规划绕行点` : ''}`
})

const caption = computed(() => {
  if (!waypoints.value.length) return '暂无巡检路线。提交自主巡检任务后，路点与重规划绕行点会实时绘制在场景中。'
  const detour = waypoints.value.filter(p => p.detour).length
  const done = waypoints.value.filter(p => p.done).length
  return `路线 ${done}/${waypoints.value.length} 已执行${detour ? `，${detour} 个绕行点来自连续异常重规划` : ''}；机器人位姿由真实遥测驱动。`
})

// ------------------------------------------------------------------
// 静态降级视图
// ------------------------------------------------------------------

function worldToSvg(x, y) {
  /* 地图 x∈[-5,10] y∈[-3,9] → SVG 560x200，留 20px 边距 */
  const cx = 20 + ((x + 5) / 15) * 520
  const cy = 180 - ((y + 3) / 12) * 160
  return { cx: Math.round(cx), cy: Math.round(cy) }
}

const staticPoints = computed(() => waypoints.value.map(p => ({ ...worldToSvg(p.x, p.y), detour: p.detour })))
const staticPolyline = computed(() => staticPoints.value.map(p => `${p.cx},${p.cy}`).join(' '))
const staticRobot = computed(() => {
  const pose = props.telemetry?.pose
  if (!pose) return { cx: 280, cy: 100 }
  return worldToSvg(Number(pose.x) || 0, Number(pose.y) || 0)
})
const staticNote = computed(() =>
  `静态俯视图（${staticReason.value}）· 路线 ${waypoints.value.length} 点 · 白点为机器人实时位置`
)

// ------------------------------------------------------------------
// three.js 场景
// ------------------------------------------------------------------

/* 遥测目标位姿（角度制 theta），watch 写入 / 渲染循环读取 */
const poseTarget = { x: 0, y: 0, theta: 0, valid: false }

let disposeScene = () => {}
let replaceRobotRef = null
let syncRouteRef = null

function resolveColor(cssVar, fallback) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim()
  if (!raw || raw.startsWith('var(')) return fallback
  try { return new Color(raw).getHex() } catch { return fallback }
}

/** 占位机器人本体（M8b 时在此替换为 GLTFLoader 加载真实 GLB）。 */
function buildPlaceholder(formFactor, accent) {
  const group = new Group()
  const body = new MeshBasicMaterial({ color: accent, transparent: true, opacity: 0.92 })
  const dark = new MeshBasicMaterial({ color: 0x22262e, transparent: true, opacity: 0.95 })

  if (formFactor === 'CAR') {
    const chassis = new Mesh(new BoxGeometry(0.5, 0.16, 0.3), body)
    chassis.position.y = 0.14
    const roof = new Mesh(new BoxGeometry(0.2, 0.1, 0.2), dark)
    roof.position.set(-0.05, 0.26, 0)
    group.add(chassis, roof)
    /* 4 轮：圆柱默认轴向是 Y，旋转到 Z 轴（横向） */
    const wheelGeo = new CylinderGeometry(0.07, 0.07, 0.05, 12)
    wheelGeo.rotateX(Math.PI / 2)
    for (const [wx, wz] of [[0.16, 0.16], [0.16, -0.16], [-0.16, 0.16], [-0.16, -0.16]]) {
      const wheel = new Mesh(wheelGeo, dark)
      wheel.position.set(wx, 0.07, wz)
      group.add(wheel)
    }
  } else if (formFactor === 'SPIDER') {
    const disc = new Mesh(new CylinderGeometry(0.22, 0.26, 0.12, 16), body)
    disc.position.y = 0.22
    group.add(disc)
    const legGeo = new BoxGeometry(0.03, 0.03, 0.2)
    for (let i = 0; i < 8; i += 1) {
      const angle = (i / 8) * Math.PI * 2
      const leg = new Mesh(legGeo, dark)
      leg.position.set(Math.cos(angle) * 0.3, 0.1, Math.sin(angle) * 0.3)
      leg.rotation.y = -angle + Math.PI / 2
      leg.rotation.x = 0.5
      group.add(leg)
    }
  } else {
    const torso = new Mesh(new CylinderGeometry(0.14, 0.18, 0.4, 12), body)
    torso.position.y = 0.25
    const head = new Mesh(new BoxGeometry(0.16, 0.14, 0.16), dark)
    head.position.y = 0.52
    group.add(torso, head)
  }

  /* 朝向箭头：+X 为机头方向（theta=0 朝 +X），障碍过近时变红 */
  const noseMat = new MeshBasicMaterial({ color: 0x5ad691, transparent: true, opacity: 0.95 })
  const nose = new Mesh(new ConeGeometry(0.07, 0.2, 10), noseMat)
  nose.rotation.z = -Math.PI / 2
  nose.position.set(0.34, 0.2, 0)
  group.add(nose)
  group.userData.noseMat = noseMat
  return group
}

onMounted(() => {
  try { reduced.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { /* SSR */ }
  if (staticMode.value || !host.value) return

  let renderer
  try {
    renderer = new WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' })
  } catch { return }
  const element = host.value
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
  element.appendChild(renderer.domElement)
  webglReady.value = true

  const scene = new Scene()
  const accent = resolveColor('--ds-color-primary', ROUTE_COLOR)
  const camera = new PerspectiveCamera(50, 1, 0.1, 100)
  camera.position.set(2.5, 6.2, 5.2)
  camera.lookAt(2.5, 0, -0.6)

  /* 地面网格：覆盖地图 x∈[-5,10]，中心放 (2.5, 0) */
  const grid = new GridHelper(16, 16, 0x3a3f4a, 0x24272e)
  grid.position.set(2.5, 0, 0)
  scene.add(grid)

  /* 路线折线 + 路点标记（route 变化时重建） */
  const routeGroup = new Group()
  scene.add(routeGroup)

  /* 机器人占位本体（formFactor 变化时替换）；CAR 优先加载真实 GLB，失败回退占位 */
  let robot = buildPlaceholder(props.formFactor, accent)
  scene.add(robot)

  /* GLB PBR 材质需要灯光（占位模型是 MeshBasicMaterial，不受灯光影响） */
  scene.add(new AmbientLight(0xffffff, 1.1))
  const sun = new DirectionalLight(0xffffff, 1.6)
  sun.position.set(5, 8, 4)
  scene.add(sun)

  /* 真模型状态：动画 mixer + 材质清单（stale 半透明 / 障碍红警用） */
  let mixer = null
  let glbMaterials = []
  let lampMats = []
  /* 材质状态机：只在切换帧写材质 */
  let staleApplied = false
  let alarmApplied = false
  const MODEL_URLS = {
    CAR: '/models/robot/patrol-car.glb',
    SPIDER: '/models/robot/spider-bot.glb',
  }
  /* 按 URL 缓存：同一模型只加载一次（不同形态各自缓存） */
  const glbCache = new Map()

  function loadGltf(url) {
    if (!glbCache.has(url)) {
      glbCache.set(url, new Promise((resolve, reject) => {
        new GLTFLoader().load(url, resolve, undefined, reject)
      }))
    }
    return glbCache.get(url)
  }

  function disposeRobotMesh(target) {
    target.traverse((node) => {
      node.geometry?.dispose?.()
      node.material?.dispose?.()
    })
  }

  /** 挂载 GLB 场景并接管渲染状态（调用方保证先移除旧 robot）。 */
  function applyGltf(gltf) {
    scene.remove(robot)
    disposeRobotMesh(robot)
    robot = gltf.scene
    glbMaterials = []
    lampMats = []
    staleApplied = false
    alarmApplied = false
    robot.traverse((node) => {
      if (!node.material) return
      if (!glbMaterials.includes(node.material)) glbMaterials.push(node.material)
      if (/HeadLamp/.test(node.name || '') && !lampMats.includes(node.material)) lampMats.push(node.material)
    })
    if (gltf.animations?.length) {
      mixer = new AnimationMixer(robot)
      const clip = gltf.animations.find((c) => c.name === 'drive') || gltf.animations[0]
      mixer.clipAction(clip).play()
    }
    scene.add(robot)
  }

  function usePlaceholder(formFactor) {
    scene.remove(robot)
    disposeRobotMesh(robot)
    mixer?.stopAllAction()
    mixer = null
    glbMaterials = []
    lampMats = []
    staleApplied = false
    alarmApplied = false
    robot = buildPlaceholder(formFactor, accent)
    scene.add(robot)
  }

  function mountRobotFor(formFactor) {
    const url = MODEL_URLS[formFactor]
    if (!url) { usePlaceholder(formFactor); return }
    loadGltf(url)
      .then((gltf) => {
        /* 异步加载期间的 formFactor 竞态守卫：只挂载当前形态对应的模型 */
        if (MODEL_URLS[props.formFactor] === url) applyGltf(gltf)
      })
      .catch(() => {
        if (MODEL_URLS[props.formFactor] === url) usePlaceholder(formFactor) /* 模型缺失/解析失败 → 占位兜底 */
      })
  }

  mountRobotFor(props.formFactor)

  replaceRobotRef = mountRobotFor

  function disposeGroupChildren(group) {
    for (const child of [...group.children]) {
      group.remove(child)
      child.traverse?.((node) => {
        node.geometry?.dispose?.()
        node.material?.dispose?.()
      })
    }
  }

  function syncRoute() {
    disposeGroupChildren(routeGroup)
    const pts = waypoints.value
    if (!pts.length) return

    const positions = pts.map(p => new Vector3(p.x, 0.02, -p.y))
    const lineGeo = new BufferGeometry().setFromPoints(positions)
    routeGroup.add(new Line(lineGeo, new LineBasicMaterial({ color: accent, transparent: true, opacity: 0.45 })))

    const markGeo = new CircleGeometry(0.09, 16)
    markGeo.rotateX(-Math.PI / 2)
    for (const p of pts) {
      const mat = new MeshBasicMaterial({
        color: p.detour ? DETOUR_COLOR : accent,
        transparent: true,
        opacity: p.done ? 0.28 : 0.85
      })
      const mark = new Mesh(markGeo, mat)
      mark.position.set(p.x, 0.02, -p.y)
      routeGroup.add(mark)
    }
  }

  function resize() {
    const w = Math.max(1, element.clientWidth)
    const h = Math.max(1, element.clientHeight)
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null
  ro?.observe(element)
  resize()
  syncRoute()
  syncRouteRef = syncRoute

  /* 面板滚出视口时暂停渲染（motionScheduler 只在 document.hidden 停，此处补组件级离屏暂停）。
     用几何计算而非 IntersectionObserver：IO 在 headless/无合成器环境恒报不可见，几何判断跨环境一致。
     每 500ms 才算一次 rect，布局读取成本可忽略。 */
  let stageVisible = true
  let lastVisCheck = 0
  function updateStageVisible(now) {
    if (now - lastVisCheck < 500) return
    lastVisCheck = now
    const r = element.getBoundingClientRect()
    stageVisible = r.bottom > 0 && r.top < window.innerHeight && r.right > 0 && r.left < window.innerWidth
  }

  const unsubscribe = subscribe((dt, now) => {
    updateStageVisible(now)
    if (!stageVisible || staticMode.value) return
    /* 位姿插值：遥测几 Hz 推送，逐帧 12% 逼近，运动连续不跳变 */
    if (poseTarget.valid) {
      robot.position.x += (poseTarget.x - robot.position.x) * 0.12
      robot.position.z += (-poseTarget.y - robot.position.z) * 0.12
      const wantY = -poseTarget.theta * Math.PI / 180
      let delta = wantY - robot.rotation.y
      /* 角度走最短弧 */
      while (delta > Math.PI) delta -= Math.PI * 2
      while (delta < -Math.PI) delta += Math.PI * 2
      robot.rotation.y += delta * 0.12
    }
    /* GLB 骨骼/关键帧动画驱动（motionScheduler 的 dt 是毫秒；钳制防 tab 切回后跳帧） */
    if (mixer) mixer.update(Math.min(dt / 1000, 0.1))
    /* 心跳超时 → 本体半透明；障碍过近 → 车灯/机头变红（真实 obstacleDistance 驱动）
       只在状态切换时写材质：GLB PBR 材质 transparent 默认 false，避免每帧写与常驻透明排序开销 */
    const obstacle = Number(props.telemetry?.obstacleDistance)
    const wantAlarm = Number.isFinite(obstacle) && obstacle < 0.5 && !props.stale
    const wantStale = props.stale
    if (glbMaterials.length) {
      if (wantStale !== staleApplied) {
        staleApplied = wantStale
        glbMaterials.forEach((m) => {
          m.transparent = wantStale
          m.opacity = wantStale ? 0.3 : 1
        })
      }
      if (wantAlarm !== alarmApplied && lampMats.length) {
        alarmApplied = wantAlarm
        lampMats.forEach((m) => m.emissive?.setHex(wantAlarm ? 0xe5484d : 0x1c5a37))
      }
    } else {
      const bodyOpacity = props.stale ? 0.3 : 0.92
      robot.children.forEach((child) => {
        if (child.material && child.material !== robot.userData.noseMat) {
          child.material.opacity = bodyOpacity
        }
      })
      robot.userData.noseMat.color.setHex(wantAlarm ? 0xe5484d : 0x5ad691)
      robot.userData.noseMat.opacity = props.stale ? 0.35 : 0.95
      staleApplied = props.stale
      alarmApplied = wantAlarm
    }
    renderer.render(scene, camera)
  })

  disposeScene = () => {
    unsubscribe()
    mixer?.stopAllAction()
    mixer = null
    ro?.disconnect()
    disposeGroupChildren(routeGroup)
    robot.traverse((node) => {
      node.geometry?.dispose?.()
      node.material?.dispose?.()
    })
    grid.geometry.dispose()
    grid.material.dispose()
    renderer.dispose()
    if (renderer.domElement.parentNode === element) element.removeChild(renderer.domElement)
    delete window.__rs3d
  }

  /* DEV 调试钩子：性能诊断用（生产构建为 undefined） */
  if (import.meta.env.DEV) {
    window.__rs3d = {
      renderer, scene, camera, canvas: renderer.domElement,
      getStageVisible: () => stageVisible,
      getMixer: () => ({ present: !!mixer, time: mixer?.time ?? 0, clipCount: mixer?.clipActions?.length ?? 0 }),
    }
  }
})

watch(() => props.telemetry?.pose, (pose) => {
  if (!pose) return
  poseTarget.x = Number(pose.x) || 0
  poseTarget.y = Number(pose.y) || 0
  poseTarget.theta = Number(pose.theta) || 0
  poseTarget.valid = true
}, { deep: true })

watch(() => props.formFactor, (ff) => replaceRobotRef?.(ff))
/* 路线数据变化 → 重建折线与路点标记（WebGL 就绪时） */
watch(waypoints, () => syncRouteRef?.())

onBeforeUnmount(() => {
  if (routeRefreshTimer) { window.clearTimeout(routeRefreshTimer); routeRefreshTimer = null }
  disposeScene()
})
</script>

<style scoped>
.rs3-wrap { border: 1px solid var(--ds-hairline, var(--smart-border)); border-radius: 12px; background: var(--ds-surface-raised, var(--smart-surface)); padding: 14px 16px; }
.rs3-head { display: flex; justify-content: space-between; align-items: end; gap: 16px; flex-wrap: wrap; }
.rs3-eyebrow { margin: 0 0 5px; color: var(--ds-color-primary, var(--smart-primary)); font: 10px Consolas, monospace; letter-spacing: .14em; }
.rs3-head h2 { margin: 0; font-size: 15px; font-weight: 500; }
.rs3-legend { display: flex; gap: 12px; }
.rs3-key { display: inline-flex; align-items: center; gap: 5px; color: var(--ds-color-muted, var(--smart-muted)); font-size: 11px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-route { border: 1.5px solid var(--ds-color-primary, #5b8cff); }
.dot-detour { background: #e3a008; }
.dot-robot { background: var(--ds-color-text, #e8eaed); }
.rs3-stage { position: relative; height: 240px; margin-top: 12px; overflow: hidden; border-radius: 8px; }
.rs3-stage :deep(canvas) { display: block; width: 100%; height: 100%; }
.rs3-stage--static { display: grid; place-items: center; }
.rs3-static-svg { width: 100%; height: 100%; }
.rs3-static-note { position: absolute; bottom: 8px; left: 12px; margin: 0; color: var(--ds-color-muted, var(--smart-muted)); font-size: 10px; }
.rs3-caption { margin: 8px 0 0; color: var(--ds-color-muted, var(--smart-muted)); font-size: 11px; line-height: 1.6; }
@media (max-width: 760px) { .rs3-stage { height: 180px; } .rs3-legend { display: none; } }
</style>
