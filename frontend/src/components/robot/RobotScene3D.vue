<template>
  <section class="rs3-wrap" aria-labelledby="rs3-title">
    <header class="rs3-head">
      <div>
        <p class="rs3-eyebrow">SCENE 3D · 宇树形态建模 · 真实遥测驱动</p>
        <h2 id="rs3-title">3D 态势</h2>
      </div>
      <div class="rs3-head-right">
        <div class="rs3-legend" aria-hidden="true">
          <span class="rs3-key"><i class="dot dot-route"></i>路点</span>
          <span class="rs3-key"><i class="dot dot-detour"></i>绕行点</span>
          <span class="rs3-key"><i class="dot dot-robot"></i>机器人</span>
        </div>
        <button type="button" class="rs3-details-btn" :aria-label="`查看 ${deviceKey || '设备'} 详情`" @click="detailsOpen = true">
          设备详情
        </button>
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
        <!-- 机器人俯视剪影：按形态区分（四足 / 人形 / 车载 / 六足），可点击打开详情（与 WebGL 拾取行为一致） -->
        <g
          class="rs3-static-robot"
          :transform="`translate(${staticRobot.cx} ${staticRobot.cy})`"
          :style="{ color: stale ? '#8a8f98' : 'var(--ds-color-text, #e8eaed)' }"
          @click="detailsOpen = true"
        >
          <template v-if="formFactor === 'DOG'">
            <ellipse cx="0" cy="0" rx="7" ry="4.2" fill="currentColor" />
            <rect v-for="(s, i) in [[-4.4, -5.2], [4.4, -5.2], [-4.4, 3.1], [4.4, 3.1]]" :key="`dg-${i}`"
              :x="s[0]" :y="s[1]" width="3" height="2.1" rx="0.9" fill="currentColor" opacity="0.75" />
          </template>
          <template v-else-if="formFactor === 'ROBOT'">
            <circle cx="0" cy="0" r="3.4" fill="currentColor" />
            <rect x="-6.2" y="-1.1" width="3.4" height="2.2" rx="1.1" fill="currentColor" opacity="0.75" />
            <rect x="2.8" y="-1.1" width="3.4" height="2.2" rx="1.1" fill="currentColor" opacity="0.75" />
            <rect x="-2.6" y="-6" width="2.2" height="3" rx="1" fill="currentColor" opacity="0.75" />
            <rect x="0.4" y="-6" width="2.2" height="3" rx="1" fill="currentColor" opacity="0.75" />
          </template>
          <template v-else-if="formFactor === 'SPIDER'">
            <circle cx="0" cy="0" r="3.2" fill="currentColor" />
            <line v-for="(a, i) in [-2.3, -1.15, 0.15, 1.35, 2.5, 3.6]" :key="`sg-${i}`"
              x1="0" y1="0" :x2="Math.cos(a) * 6.2" :y2="Math.sin(a) * 6.2"
              stroke="currentColor" stroke-width="1.2" opacity="0.75" />
          </template>
          <template v-else>
            <rect x="-6.4" y="-3.6" width="12.8" height="7.2" rx="2.4" fill="currentColor" />
          </template>
        </g>
      </svg>
      <p class="rs3-static-note">{{ staticNote }}</p>
    </div>

    <p class="rs3-caption">{{ caption }}</p>

    <!-- 设备详情弹窗：台账信息自接口加载，遥测/路线直接复用本面板已持有的真实数据 -->
    <RobotDeviceDetails
      :open="detailsOpen"
      :device-key="deviceKey"
      :form-factor="formFactor"
      :mode="mode"
      :telemetry="telemetry"
      :stale="stale"
      :waypoints="waypoints"
      @close="detailsOpen = false"
    />
  </section>
</template>

<script setup>
/**
 * 机器人 3D 态势面（仿宇树形态程序化建模）。
 *
 * 数据全部来自真实链路，不伪造：
 * - 位姿：父级 WebSocket 遥测 telemetry.pose（x/y/theta，theta 为角度制）；
 * - 路线：getRobotTasks 取该设备最新任务的 route，label 含「绕行」的点 = M7 重规划绕行点（橙色高亮）；
 * - 已走过路点按 task.progress 变暗；障碍过近时机头箭头变红（真实 obstacleDistance 驱动）；
 * - 步态：四足/人形关节角由「位姿插值后的真实位移速度」驱动（心跳超时 → 速度归零站立，不做假动作）。
 *
 * 本体形态：
 * - DOG   → rigs/quadrupedRig.js（仿 Go2 四足：机身 + LiDAR 旋转 + 4 腿 3 段）
 * - ROBOT → rigs/humanoidRig.js（仿 G1 人形：躯干 + 双臂 + 双腿）
 * - CAR / SPIDER → 优先 GLB（patrol-car / spider-bot），失败或缺失回退占位几何
 *
 * 交互：拖拽环视（>6px 位移）、滚轮缩放；位移 <6px 视为点击 → 射线拾取打开设备详情。
 *
 * 降级：WebGL 不可用 / 轻量视觉模式 / 减少动态模式 → 静态 SVG 俯视图（对齐 EngineField3D 惯例）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AmbientLight, AnimationMixer, BufferGeometry, BoxGeometry, CircleGeometry, Color, ConeGeometry,
  CylinderGeometry, DirectionalLight, GridHelper, Group, HemisphereLight, Line, LineBasicMaterial, Mesh,
  MeshBasicMaterial, PerspectiveCamera, PMREMGenerator, Raycaster, Scene, Vector2, Vector3, WebGLRenderer
} from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { buildQuadrupedRig } from './rigs/quadrupedRig'
import { buildHumanoidRig } from './rigs/humanoidRig'
import { humanoidPose, quadrupedPose } from './rigs/gait'
import { isDegraded, subscribe } from '../../visual/motionScheduler.js'
import { isLightweightVisualMode, isReducedMotionMode } from '../../visual/visualMode.js'
import { getRobotTasks } from '../../api/robot'
import RobotDeviceDetails from './RobotDeviceDetails.vue'

const props = defineProps({
  telemetry: { type: Object, default: null },
  stale: { type: Boolean, default: true },
  deviceKey: { type: String, default: '' },
  formFactor: { type: String, default: 'CAR' },
  mode: { type: String, default: 'OFFLINE' },
  /* 状态灯 / LiDAR 扫描动画的可选覆盖项，缺省走 rigs/effects.js 的 DEFAULT_EFFECT_CONFIG */
  effects: { type: Object, default: null }
})

const host = ref(null)
const webglReady = ref(false)
const reduced = ref(false)
const detailsOpen = ref(false)
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
  `静态俯视图（${staticReason.value}）· 路线 ${waypoints.value.length} 点 · 白点为机器人实时位置，点击可查看详情`
)

// ------------------------------------------------------------------
// three.js 场景
// ------------------------------------------------------------------

/* 遥测目标位姿（角度制 theta），watch 写入 / 渲染循环读取 */
const poseTarget = { x: 0, y: 0, theta: 0, valid: false }

let disposeScene = () => {}
let replaceRobotRef = null
let syncRouteRef = null
let applyEffectsRef = null

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
  const camera = new PerspectiveCamera(42, 1, 0.1, 100)
  /* 环视：目标点固定在地图中部，拖拽只改球坐标角度，构图基准不漂移 */
  const camTarget = new Vector3(2.5, 0.42, -0.6)
  const orbit = { radius: 5.6, polar: 0.74, azimuth: 0 }
  function applyCamera() {
    const sinPolar = Math.sin(orbit.polar)
    camera.position.set(
      camTarget.x + orbit.radius * sinPolar * Math.sin(orbit.azimuth),
      camTarget.y + orbit.radius * Math.cos(orbit.polar),
      camTarget.z + orbit.radius * sinPolar * Math.cos(orbit.azimuth)
    )
    camera.lookAt(camTarget)
  }
  applyCamera()

  /* PBR 环境贴图：金属材质没有环境反射会发黑，用 RoomEnvironment 生成一次即可
     （只影响 PBR 材质，占位几何用的 MeshBasicMaterial 不受影响） */
  const pmrem = new PMREMGenerator(renderer)
  const envRT = pmrem.fromScene(new RoomEnvironment(), 0.04)
  scene.environment = envRT.texture
  scene.environmentIntensity = 0.65
  pmrem.dispose()

  /* 地面网格：覆盖地图 x∈[-5,10]，中心放 (2.5, 0) */
  const grid = new GridHelper(16, 16, 0x3a3f4a, 0x24272e)
  grid.position.set(2.5, 0, 0)
  scene.add(grid)

  /* 路线折线 + 路点标记（route 变化时重建） */
  const routeGroup = new Group()
  scene.add(routeGroup)

  /* 机器人本体（formFactor 变化时替换）：DOG → 仿宇树四足 rig；ROBOT → 仿宇树人形 rig；
     CAR / SPIDER 优先加载真实 GLB，失败回退占位几何 */
  let robot = buildPlaceholder(props.formFactor, accent)
  scene.add(robot)

  /* PBR 材质需要灯光：半球光铺天光/地面反射，主平行光造高光与体积感，补光压暗部
     （占位模型是 MeshBasicMaterial，不受灯光影响，行为不变） */
  scene.add(new AmbientLight(0xffffff, 0.5))
  scene.add(new HemisphereLight(0xdbe4ff, 0x171a20, 0.95))
  const keyLight = new DirectionalLight(0xffffff, 2.1)
  keyLight.position.set(5, 8, 4)
  scene.add(keyLight)
  const rimLight = new DirectionalLight(accent, 0.85)
  rimLight.position.set(-6, 3.2, -5)
  scene.add(rimLight)

  /* 真模型状态：动画 mixer + 材质清单（stale 半透明 / 障碍红警用） */
  let mixer = null
  let glbMaterials = []
  let lampMats = []
  /* 程序化 rig（DOG / ROBOT 形态）：独立材质 + 关节阻尼由 rig 自己维护 */
  let rig = null
  let gaitClock = 0
  let speedEma = 0
  /* 材质状态机：只在切换帧写材质 */
  let staleApplied = false
  let alarmApplied = false
  const MODEL_URLS = {
    CAR: '/models/robot/patrol-car.glb',
    SPIDER: '/models/robot/spider-bot.glb',
  }
  /* 按 URL 缓存：同一模型只加载一次（不同形态各自缓存） */
  const glbCache = new Map()

  /* 接触阴影：一块跟随本体的半透明圆片，让立体件与地面有落地感 */
  const shadowMat = new MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.2, depthWrite: false })
  const shadowGeo = new CircleGeometry(0.34, 24)
  shadowGeo.rotateX(-Math.PI / 2)
  const contactShadow = new Mesh(shadowGeo, shadowMat)
  contactShadow.position.y = 0.004
  scene.add(contactShadow)

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

  /** 卸载当前机器人本体（GLB / rig / 占位几何都走这里），并复位渲染状态。 */
  function teardownRobot() {
    if (!robot) return
    scene.remove(robot)
    if (rig) {
      rig.dispose()
      rig = null
    } else {
      disposeRobotMesh(robot)
    }
    mixer?.stopAllAction()
    mixer = null
    glbMaterials = []
    lampMats = []
    staleApplied = false
    alarmApplied = false
    robot = null
  }

  /** 挂载 GLB 场景并接管渲染状态（调用方保证先移除旧 robot）。 */
  function applyGltf(gltf) {
    teardownRobot()
    robot = gltf.scene
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
    teardownRobot()
    robot = buildPlaceholder(formFactor, accent)
    scene.add(robot)
  }

  /** 挂载程序化 rig：DOG → 仿宇树四足，ROBOT → 仿宇树人形。 */
  function useProceduralRig(formFactor) {
    teardownRobot()
    rig = formFactor === 'DOG'
      ? buildQuadrupedRig({ accentHex: accent, effects: props.effects })
      : buildHumanoidRig({ accentHex: accent, effects: props.effects })
    robot = rig.group
    /* 可视化放大：真实机身在 15m 地图上只有几十像素，按「态势图标」比例放大才看得清结构 */
    robot.scale.setScalar(formFactor === 'DOG' ? 2.2 : 1.6)
    gaitClock = 0
    speedEma = 0
    scene.add(robot)
  }

  function mountRobotFor(formFactor) {
    if (formFactor === 'DOG' || formFactor === 'ROBOT') { useProceduralRig(formFactor); return }
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
  /* 动效参数热更新：rig 内部持可变配置，拖动调节滑杆无需重建几何 */
  applyEffectsRef = (effects) => rig?.setEffects(effects)

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

  /* 模型点击拾取 + 拖拽环视：
     - 拖拽位移 < 6px 视为点击 → 射线命中本体打开设备详情（保持既有交互）
     - 超过阈值 → 旋转球坐标相机，同时抑制拖拽结束后浏览器补发的 click */
  const raycaster = new Raycaster()
  const pointer = new Vector2()
  function hitRobot(event) {
    if (!robot) return false
    const rect = element.getBoundingClientRect()
    if (!rect.width || !rect.height) return false
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(pointer, camera)
    /* robot 为 let 闭包变量，GLB / rig 换装后自动指向当前模型 */
    return raycaster.intersectObject(robot, true).length > 0
  }

  const DRAG_THRESHOLD = 6
  let dragging = false
  let dragDistance = 0
  let dragSuppressClick = false
  let lastPointerX = 0
  let lastPointerY = 0

  function onStagePointerDown(event) {
    if (event.button !== 0) return
    dragging = true
    dragDistance = 0
    dragSuppressClick = false
    lastPointerX = event.clientX
    lastPointerY = event.clientY
  }

  function onStageClick(event) {
    if (dragSuppressClick) { dragSuppressClick = false; return }
    if (hitRobot(event)) detailsOpen.value = true
  }

  /* 悬停指针反馈：120ms 节流的射线检测，命中模型显示 pointer 光标 */
  let lastHoverCheck = 0
  function onStageMove(event) {
    if (dragging) {
      const dx = event.clientX - lastPointerX
      const dy = event.clientY - lastPointerY
      lastPointerX = event.clientX
      lastPointerY = event.clientY
      dragDistance += Math.abs(dx) + Math.abs(dy)
      if (dragDistance >= DRAG_THRESHOLD) {
        dragSuppressClick = true
        orbit.azimuth = Math.min(1.05, Math.max(-1.05, orbit.azimuth - dx * 0.006))
        orbit.polar = Math.min(1.2, Math.max(0.3, orbit.polar - dy * 0.005))
        applyCamera()
        element.style.cursor = 'grabbing'
      }
      return
    }
    const now = performance.now()
    if (now - lastHoverCheck < 120) return
    lastHoverCheck = now
    element.style.cursor = hitRobot(event) ? 'pointer' : ''
  }
  function onStagePointerUp() {
    if (!dragging) return
    dragging = false
    element.style.cursor = ''
    /* 拖拽结束浏览器会补发 click，交给 onStageClick 的首帧抑制 */
  }
  function onStageWheel(event) {
    event.preventDefault()
    orbit.radius = Math.min(12, Math.max(4, orbit.radius + Math.sign(event.deltaY) * 0.45))
    applyCamera()
  }

  element.addEventListener('click', onStageClick)
  element.addEventListener('pointerdown', onStagePointerDown)
  element.addEventListener('pointerup', onStagePointerUp)
  element.addEventListener('pointercancel', onStagePointerUp)
  element.addEventListener('pointerleave', onStagePointerUp)
  element.addEventListener('pointermove', onStageMove)
  element.addEventListener('wheel', onStageWheel, { passive: false })

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
    const dtSec = Math.min(dt / 1000, 0.1)
    /* 位姿插值：遥测几 Hz 推送，逐帧 12% 逼近，运动连续不跳变 */
    let moved = 0
    if (poseTarget.valid && robot) {
      const beforeX = robot.position.x
      const beforeZ = robot.position.z
      robot.position.x += (poseTarget.x - beforeX) * 0.12
      robot.position.z += (-poseTarget.y - beforeZ) * 0.12
      moved = Math.hypot(robot.position.x - beforeX, robot.position.z - beforeZ)
      const wantY = -poseTarget.theta * Math.PI / 180
      let delta = wantY - robot.rotation.y
      /* 角度走最短弧 */
      while (delta > Math.PI) delta -= Math.PI * 2
      while (delta < -Math.PI) delta += Math.PI * 2
      robot.rotation.y += delta * 0.12
    }
    /* GLB 骨骼/关键帧动画驱动（motionScheduler 的 dt 是毫秒；钳制防 tab 切回后跳帧） */
    if (mixer) mixer.update(dtSec)

    /* 心跳超时 → 本体半透明；障碍过近 → 状态灯变红（真实 obstacleDistance 驱动）
       只在状态切换时写材质：GLB PBR 材质 transparent 默认 false，避免每帧写与常驻透明排序开销 */
    const obstacle = Number(props.telemetry?.obstacleDistance)
    const wantAlarm = Number.isFinite(obstacle) && obstacle < 0.5 && !props.stale
    const wantStale = props.stale

    if (rig && robot) {
      /* 步态振幅来自真实位移速度；心跳超时 → 速度归零并回到站立，不做假动作 */
      const instant = wantStale || !poseTarget.valid ? 0 : moved / Math.max(dtSec, 1e-3)
      speedEma += (Math.min(instant, 1) - speedEma) * 0.18
      if (!wantStale) gaitClock += dtSec
      const pose = rig.kind === 'quadruped'
        ? quadrupedPose({ speed: speedEma, t: gaitClock })
        : humanoidPose({ speed: speedEma, t: gaitClock })
      rig.update({ dt: dtSec, pose })
      rig.setStale(wantStale)
      rig.setAlarm(wantAlarm)
    } else if (glbMaterials.length) {
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
    } else if (robot) {
      const bodyOpacity = wantStale ? 0.3 : 0.92
      robot.children.forEach((child) => {
        if (child.material && child.material !== robot.userData.noseMat) {
          child.material.opacity = bodyOpacity
        }
      })
      robot.userData.noseMat?.color.setHex(wantAlarm ? 0xe5484d : 0x5ad691)
      if (robot.userData.noseMat) robot.userData.noseMat.opacity = wantStale ? 0.35 : 0.95
      staleApplied = wantStale
      alarmApplied = wantAlarm
    }

    /* 接触阴影跟随本体：四足/人形用小圆片，车载形态铺大一圈 */
    if (robot) {
      contactShadow.position.x = robot.position.x
      contactShadow.position.z = robot.position.z
      const shadowScale = props.formFactor === 'ROBOT' ? 1.15 : props.formFactor === 'DOG' ? 2.2 : 1.5
      contactShadow.scale.setScalar(shadowScale)
      shadowMat.opacity = wantStale ? 0.07 : 0.2
    }

    renderer.render(scene, camera)
  })

  disposeScene = () => {
    unsubscribe()
    mixer?.stopAllAction()
    mixer = null
    ro?.disconnect()
    element.removeEventListener('click', onStageClick)
    element.removeEventListener('pointerdown', onStagePointerDown)
    element.removeEventListener('pointerup', onStagePointerUp)
    element.removeEventListener('pointercancel', onStagePointerUp)
    element.removeEventListener('pointerleave', onStagePointerUp)
    element.removeEventListener('pointermove', onStageMove)
    element.removeEventListener('wheel', onStageWheel)
    element.style.cursor = ''
    disposeGroupChildren(routeGroup)
    if (rig) { rig.dispose(); rig = null } else if (robot) { disposeRobotMesh(robot) }
    shadowGeo.dispose()
    shadowMat.dispose()
    envRT.dispose()
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
/* 动效参数变化 → rig 热更新（仅四足 / 人形有 rig，其余形态忽略） */
watch(() => props.effects, (effects) => applyEffectsRef?.(effects), { deep: true })
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
.rs3-head-right { display: flex; align-items: center; gap: 14px; }
.rs3-details-btn {
  padding: 4px 12px;
  border: 1px solid var(--ds-color-border, var(--smart-border-strong, #3a3f4a));
  border-radius: 999px;
  background: transparent;
  color: var(--ds-color-muted, var(--smart-muted));
  font-size: 11px;
  cursor: pointer;
  transition: color 150ms ease-out, border-color 150ms ease-out;
}
.rs3-details-btn:hover,
.rs3-details-btn:focus-visible {
  color: var(--ds-color-primary, var(--smart-primary));
  border-color: var(--ds-color-primary, var(--smart-primary));
}
.rs3-details-btn:focus-visible {
  outline: 2px solid var(--ds-focus-ring-color, var(--smart-primary));
  outline-offset: 2px;
}
.rs3-key { display: inline-flex; align-items: center; gap: 5px; color: var(--ds-color-muted, var(--smart-muted)); font-size: 11px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-route { border: 1.5px solid var(--ds-color-primary, #5b8cff); }
.dot-detour { background: #e3a008; }
.dot-robot { background: var(--ds-color-text, #e8eaed); }
.rs3-stage { position: relative; height: 320px; margin-top: 12px; overflow: hidden; border-radius: 8px; cursor: grab; }
.rs3-stage :deep(canvas) { display: block; width: 100%; height: 100%; }
.rs3-stage--static { display: grid; place-items: center; cursor: default; }
.rs3-static-svg { width: 100%; height: 100%; }
.rs3-static-robot { cursor: pointer; }
.rs3-static-note { position: absolute; bottom: 8px; left: 12px; margin: 0; color: var(--ds-color-muted, var(--smart-muted)); font-size: 10px; }
.rs3-caption { margin: 8px 0 0; color: var(--ds-color-muted, var(--smart-muted)); font-size: 11px; line-height: 1.6; }
@media (max-width: 760px) { .rs3-stage { height: 220px; } .rs3-legend { display: none; } }
</style>
