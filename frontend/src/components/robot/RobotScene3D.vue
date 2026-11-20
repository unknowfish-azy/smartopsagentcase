<template>
  <section class="rs3-wrap" aria-labelledby="rs3-title">
    <header class="rs3-head">
      <div>
        <p class="rs3-eyebrow">SCENE 3D · 宇树官方模型 · 真实遥测驱动</p>
        <h2 id="rs3-title">3D 态势</h2>
      </div>
      <div class="rs3-head-right">
        <div v-if="renderReady && !staticMode" class="rs3-views" role="group" aria-label="3D 镜头视角">
          <button
            v-for="item in VIEWS"
            :key="item.key"
            type="button"
            class="rs3-view-btn"
            :class="{ active: viewMode === item.key }"
            :aria-pressed="viewMode === item.key"
            @click="viewMode = item.key"
          >{{ item.label }}</button>
        </div>
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

    <!-- 3D 场：容器常驻用 v-show；WebGL 优先，缺失时用 SVGRenderer 软件渲染，两者皆不可用才降级静态 SVG -->
    <div v-show="renderReady && !staticMode" ref="host" class="rs3-stage" :class="hudAlarmClass" role="img" :aria-label="ariaLabel">
      <!-- 悬浮 HUD：跟随本体投影，展示真实遥测；aria-hidden 避免与右侧遥测面板重复播报 -->
      <div ref="hudEl" class="rs3-hud" :class="{ 'is-hidden': !hudVisible }" aria-hidden="true">
        <span class="rs3-hud-name">
          <i class="rs3-hud-dot" :class="hudClass"></i>{{ deviceKey || '未选择设备' }}
        </span>
        <span class="rs3-hud-mode">{{ hudModeLabel }}</span>
        <span class="rs3-hud-meta">{{ hudMeta }}</span>
      </div>
      <div class="rs3-vignette" aria-hidden="true"></div>
    </div>

    <div v-if="!renderReady || staticMode" class="rs3-stage rs3-stage--static" role="img" :aria-label="ariaLabel">
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
    <p v-if="renderBackend === 'svg'" class="rs3-caption rs3-caption--fallback">
      当前环境不支持 WebGL，已切换到 SVG 软件渲染：场景、拾取与遥测驱动保持一致，动效帧率降低。
    </p>

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
 * 机器人 3D 态势面（宇树官方模型优先，程序化建模兜底）。
 *
 * 数据全部来自真实链路，不伪造：
 * - 位姿：父级 WebSocket 遥测 telemetry.pose（x/y/theta，theta 为角度制）；
 * - 关节：telemetry.joints（{官方关节名: 弧度}）存在时按真机绝对角直驱（宇树 SDK 电机命名）；
 * - 路线：getRobotTasks 取该设备最新任务的 route，label 含「绕行」的点 = M7 重规划绕行点（橙色高亮）；
 * - 已走过路点按 task.progress 变暗；障碍过近时机头箭头变红（真实 obstacleDistance 驱动）；
 * - 步态：真机关节未接入的关节由「位姿插值后的真实位移速度」推算（心跳超时 → 速度归零站立，不做假动作）。
 *
 * 本体形态（四种形态统一由 rig 驱动，尺寸归一与动效层一致）：
 * - DOG / ROBOT → 优先宇树官方 GLB（go2.glb / g1.glb，unitree_mujoco 经
 *   scripts/import-unitree-model.py 离线转换，BSD-3-Clause），rigs/unitreeGlbRig.js
 *   按官方关节名驱动，步态增量叠加官方 home 站立姿态；GLB/元数据缺失回退程序化 rig
 *   （rigs/quadrupedRig.js / rigs/humanoidRig.js）；
 * - CAR → rigs/patrolCarRig.js：轮速 = 真实线速度 / 轮半径，静止与心跳超时即停转；
 * - SPIDER → rigs/spiderRig.js：8 足 16 关节按 spiderPose 步态驱动，同样随速度起停；
 * - CAR / SPIDER 的 GLB 由 scripts/generate-*-model.mjs 从 models/ 下的构建器产出，
 *   GLB 缺失时直接用同一构建器现场生成，视觉与动效层（状态灯 + LiDAR + 扫描环）一致。
 *
 * 交互：拖拽环视（>6px 位移）、滚轮缩放；位移 <6px 视为点击 → 射线拾取打开设备详情。
 *
 * 降级：WebGL 不可用 → SVGRenderer 软件渲染（同一场景/相机/拾取）；轻量视觉模式 / 减少动态模式
 *        → 静态 SVG 俯视图（对齐 EngineField3D 惯例）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AdditiveBlending, AmbientLight, BufferAttribute, BufferGeometry, BoxGeometry, CircleGeometry, Color, ConeGeometry,
  CylinderGeometry, DirectionalLight, GridHelper, Group, HemisphereLight, Line, LineBasicMaterial, Mesh,
  MeshBasicMaterial, PerspectiveCamera, PMREMGenerator, Raycaster, Scene, Vector2, Vector3, WebGLRenderer
} from 'three'
import { SVGRenderer } from 'three/addons/renderers/SVGRenderer.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { buildQuadrupedRig } from './rigs/quadrupedRig'
import { buildHumanoidRig } from './rigs/humanoidRig'
import { createUnitreeGlbRig } from './rigs/unitreeGlbRig'
import { createPatrolCarRig } from './rigs/patrolCarRig'
import { createSpiderRig } from './rigs/spiderRig'
import { humanoidPose, quadrupedPose, spiderPose } from './rigs/gait'
import { resolveBeaconStatus, resolveEffectConfig } from './rigs/effects'
import { buildCinematicLayer } from './rigs/cinematicLayer'
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
  effects: { type: Object, default: null },
  /* 真实历史轨迹（useRobotFleet.trails[key]）：[{x, y}]，用于绘制渐隐拖尾 */
  trail: { type: Array, default: () => [] }
})

const host = ref(null)
/* 渲染后端：webgl（GPU）→ svg（软件光栅）→ static（两种后端都不可用，走静态俯视图） */
const renderBackend = ref('static')
const renderReady = computed(() => renderBackend.value !== 'static')
const reduced = ref(false)
const detailsOpen = ref(false)
/* 3D 镜头视角：全景（路线总览）/ 跟随（贴近本体）/ 俯瞰（全局态势） */
const viewMode = ref('orbit')
const VIEWS = [
  { key: 'orbit', label: '全景' },
  { key: 'follow', label: '跟随' },
  { key: 'top', label: '俯瞰' }
]
/* 悬浮 HUD：仅 WebGL 后端显示，内容全部来自真实遥测 */
const hudEl = ref(null)
const hudVisible = ref(false)
const staticMode = computed(() => isLightweightVisualMode.value || isReducedMotionMode.value || isDegraded() || reduced.value)
const staticReason = computed(() => {
  if (reduced.value || isReducedMotionMode.value) return '减少动态'
  if (isLightweightVisualMode.value) return '轻量视觉模式'
  if (isDegraded()) return '渲染负载过高'
  return 'WebGL 不可用'
})

const DETOUR_COLOR = 0xe3a008
const ROUTE_COLOR = 0x5b8cff

// ------------------------------------------------------------------
// 任务路线（真实 DB 数据）
// ------------------------------------------------------------------

const waypoints = ref([]) // [{x,y,theta,label,done,detour}]
/* 本体来源与关节数据源（如实标注，不伪造真机关节）：由挂载/渲染循环更新 */
const modelKind = ref('placeholder') // 'unitree-glb' | 'glb' | 'procedural' | 'placeholder'
const jointSource = ref('gait') // 'telemetry'（真机绝对关节角） | 'gait'（步态推算）
/* 当前 rig 实际驱动到的关节数：0 = 无关节形态（巡检车），用于如实标注数据源 */
const jointCount = ref(0)

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
  const route = !waypoints.value.length
    ? '暂无巡检路线，提交自主巡检任务后路点与绕行点实时绘制。'
    : `路线 ${waypoints.value.filter(p => p.done).length}/${waypoints.value.length} 已执行` +
      `${waypoints.value.some(p => p.detour) ? `，${waypoints.value.filter(p => p.detour).length} 个绕行点来自连续异常重规划` : ''}。`
  const model = {
    'unitree-glb': '宇树官方模型',
    glb: 'GLB 模型',
    procedural: '程序化模型（GLB 未加载，已回退）',
    placeholder: '占位几何'
  }[modelKind.value]
  /* 关节来源标注：无关节形态（巡检车）不显示 */
  const joint = jointCount.value > 0
    ? (jointSource.value === 'telemetry' ? '关节由真机遥测直驱' : '关节为步态推算（真机关节遥测未接入）')
    : ''
  return `${route} ${model}，位姿由真实遥测驱动${joint ? `；${joint}` : ''}。`
})

/* ---------- 悬浮 HUD / 告警等级（复用状态灯的业务判定） ---------- */
const MODE_LABELS = {
  HUMAN_CONTROL: '人工态',
  AUTONOMOUS: '自主态',
  IDLE: '待机',
  E_STOP: '急停',
  FAULT: '故障',
  OFFLINE: '离线'
}
const hudStatus = computed(() => resolveBeaconStatus({
  mode: props.mode,
  battery: props.telemetry?.battery,
  stale: props.stale,
  obstacleDistance: props.telemetry?.obstacleDistance
}))
const hudClass = computed(() => `is-${hudStatus.value.key}`)
/* 告警时的场景边缘脉冲（CSS 覆盖层，不参与 WebGL 渲染） */
const hudAlarmClass = computed(() => {
  const key = hudStatus.value.key
  if (key === 'fault') return 'is-alarm-fault'
  if (key === 'warn') return 'is-alarm-warn'
  return ''
})
const hudModeLabel = computed(() => MODE_LABELS[String(props.mode || '').toUpperCase()] || props.mode || '未知')
function batteryPercent(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return null
  return Math.round(n > 1 ? n : n * 100)
}
const hudMeta = computed(() => {
  const battery = batteryPercent(props.telemetry?.battery)
  const obstacle = Number(props.telemetry?.obstacleDistance)
  const theta = Number(props.telemetry?.pose?.theta)
  return [
    battery === null ? '电量 —' : `电量 ${battery}%`,
    Number.isFinite(obstacle) ? `障碍 ${obstacle.toFixed(2)}m` : '障碍 —',
    Number.isFinite(theta) ? `朝向 ${Math.round(theta)}°` : '朝向 —'
  ].join(' · ')
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
let syncTrailRef = null
let applyEffectsRef = null
let applyViewRef = null
let burstRef = null

function resolveColor(cssVar, fallback) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim()
  if (!raw || raw.startsWith('var(')) return fallback
  try { return new Color(raw).getHex() } catch { return fallback }
}

/** 当前主题：深色主题下 rig 需要压低加色光晕与点光，避免 Bloom 叠加过曝。 */
function readTheme() {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

/**
 * 取 3D 面板所在卡片的实际背景色：Bloom 会在透明画布上叠加半透明雾状 alpha，
 * 若继续保持透明，CSS 背景会透出成色块接缝，因此给场景一个与卡片一致的纯色背景。
 */
function surfaceColor(element) {
  let node = element
  while (node && node !== document.body) {
    const color = getComputedStyle(node).backgroundColor
    if (color && color !== 'transparent' && color !== 'rgba(0, 0, 0, 0)') return color
    node = node.parentElement
  }
  return getComputedStyle(document.body).backgroundColor || '#0d1117'
}

/** 占位机器人本体（M8b 时在此替换为 GLTFLoader 加载真实 GLB）。
 *  lowDetail 供 SVGRenderer 软件渲染使用：减少分段数，控制每帧生成的 SVG 面片数量。 */
function buildPlaceholder(formFactor, accent, lowDetail = false) {
  const group = new Group()
  const body = new MeshBasicMaterial({ color: accent, transparent: true, opacity: 0.92 })
  const dark = new MeshBasicMaterial({ color: 0x22262e, transparent: true, opacity: 0.95 })

  if (formFactor === 'CAR') {
    const chassis = new Mesh(new BoxGeometry(0.5, 0.16, 0.3), body)
    chassis.position.y = 0.14
    const roof = new Mesh(new BoxGeometry(0.2, 0.1, 0.2), dark)
    roof.position.set(-0.05, 0.26, 0)
    group.add(chassis, roof)
    if (lowDetail) {
      /* 软件渲染下用方块代替圆柱车轮：外形从俯视机位几乎无差别，面片数从 48 降到 12 */
      for (const [wx, wz] of [[0.16, 0.16], [0.16, -0.16], [-0.16, 0.16], [-0.16, -0.16]]) {
        const wheel = new Mesh(new BoxGeometry(0.08, 0.06, 0.14), dark)
        wheel.position.set(wx, 0.07, wz)
        group.add(wheel)
      }
    } else {
      /* 4 轮：圆柱默认轴向是 Y，旋转到 Z 轴（横向） */
      const wheelGeo = new CylinderGeometry(0.07, 0.07, 0.05, 12)
      wheelGeo.rotateX(Math.PI / 2)
      for (const [wx, wz] of [[0.16, 0.16], [0.16, -0.16], [-0.16, 0.16], [-0.16, -0.16]]) {
        const wheel = new Mesh(wheelGeo, dark)
        wheel.position.set(wx, 0.07, wz)
        group.add(wheel)
      }
    }
  } else if (formFactor === 'DOG') {
    const torso = new Mesh(new BoxGeometry(0.42, 0.14, 0.22), body)
    torso.position.y = 0.2
    const head = new Mesh(new BoxGeometry(0.14, 0.12, 0.14), dark)
    head.position.set(0.24, 0.26, 0)
    group.add(torso, head)
    for (const [lx, lz] of [[0.14, 0.1], [0.14, -0.1], [-0.14, 0.1], [-0.14, -0.1]]) {
      const leg = new Mesh(new BoxGeometry(0.05, 0.16, 0.05), dark)
      leg.position.set(lx, 0.08, lz)
      group.add(leg)
    }
  } else if (formFactor === 'SPIDER') {
    const disc = new Mesh(new CylinderGeometry(0.22, 0.26, 0.12, lowDetail ? 8 : 16), body)
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
    const torso = new Mesh(new CylinderGeometry(0.14, 0.18, 0.4, lowDetail ? 8 : 12), body)
    torso.position.y = 0.25
    const head = new Mesh(new BoxGeometry(0.16, 0.14, 0.16), dark)
    head.position.y = 0.52
    group.add(torso, head)
  }

  /* 朝向箭头：+X 为机头方向（theta=0 朝 +X），障碍过近时变红 */
  const noseMat = new MeshBasicMaterial({ color: 0x5ad691, transparent: true, opacity: 0.95 })
  const nose = new Mesh(new ConeGeometry(0.07, 0.2, lowDetail ? 6 : 10), noseMat)
  nose.rotation.z = -Math.PI / 2
  nose.position.set(0.34, 0.2, 0)
  group.add(nose)
  group.userData.noseMat = noseMat
  return group
}

onMounted(() => {
  try { reduced.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { /* SSR */ }
  if (staticMode.value || !host.value) return

  const element = host.value

  /* 后端选择：WebGL 优先；GPU 被禁用 / 无 GPU 环境时退到 three 的 SVGRenderer 软件渲染 ——
     复用同一 Scene / Camera / Raycaster，交互与遥测驱动不变；两种后端都不可用才落到静态俯视图。
     先用探测 canvas 判断 WebGL 可用性：直接 new WebGLRenderer 失败时 three 会打印 error 噪音。 */
  const hasWebGL = (() => {
    try {
      const probe = document.createElement('canvas')
      return Boolean(probe.getContext('webgl2') || probe.getContext('webgl'))
    } catch { return false }
  })()
  let renderer = null
  let backend = 'svg'
  if (hasWebGL) {
    try {
      renderer = new WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' })
      backend = 'webgl'
    } catch { renderer = null }
  }
  if (!renderer) {
    try {
      renderer = new SVGRenderer()
    } catch { return }
  }
  const isSvg = backend === 'svg'
  if (isSvg) {
    renderer.setQuality('low')
    renderer.setPrecision(1)
  } else {
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
  }
  element.appendChild(renderer.domElement)
  renderBackend.value = backend

  const scene = new Scene()
  /* 纯色背景（与所在卡片一致）+ 主题切换时同步，避免 Bloom 的半透明辉光与 CSS 背景形成色块接缝 */
  const bgColor = new Color(surfaceColor(element))
  scene.background = bgColor
  /* SVG 后端按「本体位姿 + 材质状态」签名跳帧：静止时不做任何重绘 */
  let lastSvgSignature = ''
  /* 电影感氛围层（仅 WebGL 构建，SVG 后端保持轻量） */
  let cinematic = null
  let themeObserver = null
  if (typeof MutationObserver !== 'undefined') {
    themeObserver = new MutationObserver(() => {
      bgColor.set(surfaceColor(element))
      lastSvgSignature = ''
      /* 主题切换 → 光晕/点光衰减同步（深色背景下加色 + Bloom 易过曝） */
      rig?.setTheme?.(readTheme())
      cinematic?.setTheme(readTheme())
    })
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  }
  const accent = resolveColor('--ds-color-primary', ROUTE_COLOR)
  const camera = new PerspectiveCamera(42, 1, 0.1, 100)
  /* 镜头：orbit 全景 / follow 跟随本体 / top 俯瞰；拖拽只改球坐标角度，构图基准由 camTarget 平滑过渡 */
  const BASE_TARGET = new Vector3(2.5, 0.42, -0.6)
  const camTarget = BASE_TARGET.clone()
  const focusTarget = BASE_TARGET.clone()
  const orbit = { radius: 5.6, polar: 0.74, azimuth: 0 }
  /* 跟随模式的轻微手持感：极小幅度的呼吸摆动，避免镜头完全死板 */
  let cameraSway = 0
  let swayClock = 0
  /* 开场推镜：第一帧从更远/更高的机位缓缓推到工作机位（仅 WebGL，SVG 跳帧重绘不做） */
  const INTRO_FROM = { radius: 9.6, polar: 1.04 }
  let introT = isSvg ? 1 : 0
  let lastInteractionAt = 0
  function applyCamera() {
    const sinPolar = Math.sin(orbit.polar)
    const swayX = cameraSway ? Math.sin(swayClock * 0.9) * cameraSway : 0
    const swayY = cameraSway ? Math.cos(swayClock * 1.3) * cameraSway * 0.5 : 0
    camera.position.set(
      camTarget.x + orbit.radius * sinPolar * Math.sin(orbit.azimuth) + swayX,
      camTarget.y + orbit.radius * Math.cos(orbit.polar) + swayY,
      camTarget.z + orbit.radius * sinPolar * Math.cos(orbit.azimuth) + swayX
    )
    camera.lookAt(camTarget)
    lastSvgSignature = '' /* 机位变化必须重绘（SVG 后端） */
  }
  applyCamera()

  /* 视角预设：切入时结束开场推镜，并直接套用对应的机位参数 */
  function applyViewMode(mode) {
    introT = 1
    lastInteractionAt = performance.now()
    if (mode === 'follow') {
      orbit.radius = 4.8
      orbit.polar = 0.92
      cameraSway = 0.02
    } else if (mode === 'top') {
      orbit.radius = 8.2
      orbit.polar = 0.2
      cameraSway = 0
    } else {
      orbit.radius = 5.6
      orbit.polar = 0.74
      cameraSway = 0
    }
    applyCamera()
  }
  applyViewRef = applyViewMode

  /* PBR 环境贴图：金属材质没有环境反射会发黑，用 RoomEnvironment 生成一次即可
     （只影响 PBR 材质，占位几何用的 MeshBasicMaterial 不受影响；SVG 后端无 PBR 材质，跳过） */
  let envRT = null
  if (!isSvg) {
    const pmrem = new PMREMGenerator(renderer)
    envRT = pmrem.fromScene(new RoomEnvironment(), 0.04)
    scene.environment = envRT.texture
    scene.environmentIntensity = 0.65
    pmrem.dispose()
  }

  /* 后处理 Bloom：把状态灯光晕、LiDAR 激光线等自发光溢出成真实辉光。
     强度 / 扩散 / 阈值由 `effects` prop 覆盖（调节面板的辉光三项），默认 1.2 / 0.38 / 0.7；
     isDegraded()（降级/低性能）时跳过 Bloom，直接走原始渲染。SVG 后端不支持后处理，跳过。 */
  const bloomConfig = resolveEffectConfig(props.effects)
  let composer = null
  let bloomPass = null
  if (!isSvg) {
    composer = new EffectComposer(renderer)
    composer.addPass(new RenderPass(scene, camera))
    bloomPass = new UnrealBloomPass(
      new Vector2(1, 1), bloomConfig.bloomStrength, bloomConfig.bloomRadius, bloomConfig.bloomThreshold
    )
    composer.addPass(bloomPass)
    composer.addPass(new OutputPass())
  }

  /* 地面网格：覆盖地图 x∈[-5,10]，中心放 (2.5, 0)；软件渲染减半格数并压低亮度，控制面片量 */
  const grid = new GridHelper(16, isSvg ? 8 : 16, 0x3a3f4a, 0x24272e)
  grid.position.set(2.5, 0, 0)
  if (isSvg) {
    /* GridHelper 用顶点色区分主/次网格线，SVGRenderer 只取材质色，故统一乘透明度弱化 */
    grid.material.vertexColors = false
    grid.material.color.setHex(0x3a3f4a)
    grid.material.transparent = true
    grid.material.opacity = 0.55
  }
  scene.add(grid)

  /* 电影感氛围层：地面光晕盘、雷达扫描、浮尘、路线流光、告警浮标。
     全部为真实数据驱动的装饰：路线来自任务接口，告警等级来自遥测/模式判定。 */
  if (!isSvg) {
    cinematic = buildCinematicLayer({ accentHex: accent, theme: readTheme(), lowDetail: false })
    scene.add(cinematic.group)
    cinematic.setRoute(waypoints.value)
  }

  /* 路线折线 + 路点标记（route 变化时重建） */
  const routeGroup = new Group()
  scene.add(routeGroup)

  /* 真实历史轨迹：渐隐拖尾线（越新的点越亮） */
  const trailGroup = new Group()
  scene.add(trailGroup)
  let trailLine = null

  /* 机器人本体（formFactor 变化时替换）：DOG → 仿宇树四足 rig；ROBOT → 仿宇树人形 rig；
     CAR / SPIDER 优先加载真实 GLB，失败回退占位几何；SVG 后端统一用低面数占位几何 */
  let robot = buildPlaceholder(props.formFactor, accent, isSvg)
  /* 软件渲染下放大本体：与 DOG / ROBOT rig 的图标比例一致，同时保证点击拾取面积 */
  if (isSvg) robot.scale.setScalar(2)
  scene.add(robot)

  /* 交互脉冲：点击本体打开详情时，从设备脚下扩散一圈能量环（仅 WebGL 氛围层） */
  burstRef = () => {
    if (!robot) return
    cinematic?.burstAt(
      robot.position.x,
      robot.position.z,
      props.mode === 'AUTONOMOUS' ? accent : 0x9fc2ff
    )
  }

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

  /* 本体 rig：四种形态统一接口（update / setStale / setBeaconStatus / setEffects），
     动效层、材质状态与尺寸归一都由 rig 自己维护 */
  let rig = null
  let gaitClock = 0
  /* 场景累计时间：路点呼吸、路线流光、雷达旋转共用的动画时钟 */
  let sceneElapsed = 0
  let speedEma = 0
  /* 占位几何的材质状态机：只在切换帧写材质 */
  let staleApplied = false
  let alarmApplied = false
  const MODEL_URLS = {
    CAR: '/models/robot/patrol-car.glb',
    SPIDER: '/models/robot/spider-bot.glb',
    /* 宇树官方模型（unitree_mujoco，BSD-3-Clause）：MJCF 离线转 GLB，关节节点按官方电机命名 */
    DOG: '/models/robot/go2.glb',
    ROBOT: '/models/robot/g1.glb',
  }
  const UNITREE_FORMS = new Set(['DOG', 'ROBOT'])
  /* 按 URL 缓存：同一模型只加载一次（不同形态各自缓存） */
  const glbCache = new Map()
  const rigMetaCache = new Map()

  function loadRigMeta(url) {
    if (!rigMetaCache.has(url)) {
      rigMetaCache.set(url, fetch(url).then((r) => {
        if (!r.ok) throw new Error(`rig meta ${r.status}`)
        return r.json()
      }))
    }
    return rigMetaCache.get(url)
  }

  /* 接触阴影：一块跟随本体的半透明圆片，让立体件与地面有落地感 */
  const shadowMat = new MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.2, depthWrite: false })
  const shadowGeo = new CircleGeometry(0.34, isSvg ? 12 : 24)
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

  /** 卸载当前机器人本体（rig / 占位几何都走这里），并复位渲染状态。 */
  function teardownRobot() {
    if (!robot) return
    scene.remove(robot)
    if (rig) {
      rig.dispose()
      rig = null
    } else {
      disposeRobotMesh(robot)
    }
    staleApplied = false
    alarmApplied = false
    jointCount.value = 0
    robot = null
  }

  function usePlaceholder(formFactor) {
    teardownRobot()
    robot = buildPlaceholder(formFactor, accent, isSvg)
    /* 软件渲染下放大本体：与 DOG / ROBOT rig 的图标比例一致，同时保证点击拾取面积 */
    if (isSvg) robot.scale.setScalar(2)
    modelKind.value = 'placeholder'
    scene.add(robot)
  }

  /** 挂载程序化 rig：DOG → 仿宇树四足，ROBOT → 仿宇树人形（官方 GLB 加载失败时的兜底）。 */
  function useProceduralRig(formFactor) {
    teardownRobot()
    rig = formFactor === 'DOG'
      ? buildQuadrupedRig({ accentHex: accent, effects: props.effects, theme: readTheme() })
      : buildHumanoidRig({ accentHex: accent, effects: props.effects, theme: readTheme() })
    robot = rig.group
    /* 可视化放大：真实机身在 15m 地图上只有几十像素，按「态势图标」比例放大才看得清结构 */
    robot.scale.setScalar(formFactor === 'DOG' ? 2.2 : 1.6)
    modelKind.value = 'procedural'
    jointCount.value = rig.jointCount || 0
    gaitClock = 0
    speedEma = 0
    scene.add(robot)
  }

  /** 挂载宇树官方 GLB rig：关节节点按官方电机命名，支持真机绝对关节角直驱。 */
  function useUnitreeRig(formFactor, gltf, metadata) {
    teardownRobot()
    rig = createUnitreeGlbRig({
      kind: formFactor === 'DOG' ? 'quadruped' : 'humanoid',
      gltf, metadata, accentHex: accent, effects: props.effects, theme: readTheme()
    })
    robot = rig.group
    robot.scale.setScalar(formFactor === 'DOG' ? 2.2 : 1.6)
    modelKind.value = 'unitree-glb'
    jointCount.value = rig.jointCount || 0
    gaitClock = 0
    speedEma = 0
    scene.add(robot)
  }

  /** 挂载巡检车 / 蜘蛛 rig：轮速或 8 足步态由真实位移速度驱动，尺寸与动效层在 rig 内归一。 */
  function useSurfaceRig(formFactor, { gltf, metadata } = {}) {
    teardownRobot()
    const options = { gltf, metadata, accentHex: accent, effects: props.effects, theme: readTheme() }
    rig = formFactor === 'SPIDER' ? createSpiderRig(options) : createPatrolCarRig(options)
    robot = rig.group
    robot.name = `robot-${formFactor.toLowerCase()}`
    modelKind.value = gltf ? 'glb' : 'procedural'
    jointCount.value = rig.jointCount || 0
    jointSource.value = rig.getJointSource?.() || 'gait'
    gaitClock = 0
    speedEma = 0
    scene.add(robot)
  }

  function mountRobotFor(formFactor) {
    /* SVG 软件渲染：rig 与 GLB 的面片量过大（每帧都会重建成 SVG path），统一走低面数占位几何 */
    if (isSvg) { usePlaceholder(formFactor); return }
    const url = MODEL_URLS[formFactor]
    if (!url) { usePlaceholder(formFactor); return }
    /* GLB + rig 元数据优先；缺失/解析失败时用各形态自己的兜底（四足/人形程序化 rig、
       车/蜘蛛同源构建器），保证任何情况下都不是方块占位 */
    Promise.all([loadGltf(url), loadRigMeta(url.replace(/\.glb$/, '.rig.json'))])
      .then(([gltf, metadata]) => {
        /* 异步加载期间的 formFactor 竞态守卫：只挂载当前形态 */
        if (props.formFactor !== formFactor) return
        if (UNITREE_FORMS.has(formFactor)) useUnitreeRig(formFactor, gltf, metadata)
        else useSurfaceRig(formFactor, { gltf, metadata })
      })
      .catch(() => {
        if (props.formFactor !== formFactor) return
        if (UNITREE_FORMS.has(formFactor)) useProceduralRig(formFactor)
        else useSurfaceRig(formFactor)
      })
  }

  mountRobotFor(props.formFactor)

  replaceRobotRef = mountRobotFor
  /* 动效参数热更新：rig 内部持可变配置，Bloom 直接改 pass 属性，均无需重建几何 */
  applyEffectsRef = (effects) => {
    rig?.setEffects(effects)
    if (bloomPass) {
      const cfg = resolveEffectConfig(effects)
      bloomPass.strength = cfg.bloomStrength
      bloomPass.radius = cfg.bloomRadius
      bloomPass.threshold = cfg.bloomThreshold
    }
  }

  function disposeGroupChildren(group) {
    for (const child of [...group.children]) {
      group.remove(child)
      child.traverse?.((node) => {
        node.geometry?.dispose?.()
        node.material?.dispose?.()
      })
    }
  }

  /* 真实历史轨迹拖尾：越新的点颜色越亮（加色混合下旧点自动隐入背景） */
  function syncTrail() {
    if (trailLine) {
      trailGroup.remove(trailLine)
      trailLine.geometry.dispose()
      trailLine.material.dispose()
      trailLine = null
    }
    const points = Array.isArray(props.trail) ? props.trail : []
    if (points.length < 2) return
    const positions = new Float32Array(points.length * 3)
    const colors = new Float32Array(points.length * 3)
    const tint = new Color(accent)
    for (let i = 0; i < points.length; i += 1) {
      const k = (i + 1) / points.length
      positions[i * 3] = Number(points[i].x) || 0
      positions[i * 3 + 1] = 0.035
      positions[i * 3 + 2] = -(Number(points[i].y) || 0)
      colors[i * 3] = tint.r * k
      colors[i * 3 + 1] = tint.g * k
      colors[i * 3 + 2] = tint.b * k
    }
    const geo = new BufferGeometry()
    geo.setAttribute('position', new BufferAttribute(positions, 3))
    geo.setAttribute('color', new BufferAttribute(colors, 3))
    trailLine = new Line(geo, new LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.9, blending: AdditiveBlending, depthWrite: false
    }))
    trailGroup.add(trailLine)
  }

  /* 未完成路点引用：渲染循环里做脉冲呼吸（已完成路点不再闪烁） */
  let routeMarkers = []
  function syncRoute() {
    lastSvgSignature = '' /* 路线变化必须重绘（SVG 后端） */
    disposeGroupChildren(routeGroup)
    routeMarkers = []
    const pts = waypoints.value
    cinematic?.setRoute(pts)
    if (!pts.length) return

    const positions = pts.map(p => new Vector3(p.x, 0.02, -p.y))
    const lineGeo = new BufferGeometry().setFromPoints(positions)
    routeGroup.add(new Line(lineGeo, new LineBasicMaterial({ color: accent, transparent: true, opacity: 0.45 })))

    const markGeo = new CircleGeometry(0.09, isSvg ? 8 : 16)
    markGeo.rotateX(-Math.PI / 2)
    for (const p of pts) {
      const mat = new MeshBasicMaterial({
        color: p.detour ? DETOUR_COLOR : accent,
        transparent: true,
        opacity: p.done ? 0.28 : 0.85
      })
      const mark = new Mesh(markGeo, mat)
      mark.position.set(p.x, 0.02, -p.y)
      mark.userData.done = p.done
      routeMarkers.push(mark)
      routeGroup.add(mark)
    }
  }

  function resize() {
    const w = Math.max(1, element.clientWidth)
    const h = Math.max(1, element.clientHeight)
    renderer.setSize(w, h, false)
    composer?.setSize(w, h)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    lastSvgSignature = '' /* 视口尺寸变化后 SVG 视口需重绘 */
  }
  const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null
  ro?.observe(element)
  resize()
  syncRoute()
  syncRouteRef = syncRoute
  syncTrail()
  syncTrailRef = syncTrail

  /* 悬浮 HUD：把本体上方一点投影到屏幕，节流 15fps 写 transform（避免每帧触发布局） */
  const hudWorld = new Vector3()
  let hudAppliedAt = 0
  function updateHud(now) {
    if (isSvg || !hudEl.value) return
    if (now - hudAppliedAt < 66) return
    hudAppliedAt = now
    if (!robot) { hudVisible.value = false; return }
    hudWorld.set(robot.position.x, 1.72, robot.position.z)
    hudWorld.project(camera)
    const onScreen = hudWorld.z > -1 && hudWorld.z < 1 &&
      Math.abs(hudWorld.x) < 1.04 && Math.abs(hudWorld.y) < 1.04
    hudVisible.value = onScreen
    if (!onScreen) return
    const w = element.clientWidth
    const h = element.clientHeight
    hudEl.value.style.transform =
      `translate(-50%, -100%) translate(${(hudWorld.x * 0.5 + 0.5) * w}px, ${(-hudWorld.y * 0.5 + 0.5) * h}px)`
  }

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
    introT = 1
    lastInteractionAt = performance.now()
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
        lastInteractionAt = performance.now()
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
    introT = 1
    lastInteractionAt = performance.now()
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
    sceneElapsed += dtSec
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
    /* 心跳超时 → 本体半透明；障碍过近 → 状态灯变红（真实 obstacleDistance 驱动）
       只在状态切换时写材质：rig 内部对材质状态做切换帧判定，不做每帧写入 */
    const obstacle = Number(props.telemetry?.obstacleDistance)
    const wantAlarm = Number.isFinite(obstacle) && obstacle < 0.5 && !props.stale
    const wantStale = props.stale

    if (rig && robot) {
      /* 步态 / 轮速来自真实位移速度；心跳超时 → 速度归零并回到站立，不做假动作 */
      const instant = wantStale || !poseTarget.valid ? 0 : moved / Math.max(dtSec, 1e-3)
      speedEma += (Math.min(instant, 1) - speedEma) * 0.18
      if (!wantStale) gaitClock += dtSec
      const visualSpeed = wantStale ? 0 : speedEma
      let pose = null
      if (rig.kind === 'quadruped') pose = quadrupedPose({ speed: visualSpeed, t: gaitClock })
      else if (rig.kind === 'humanoid') pose = humanoidPose({ speed: visualSpeed, t: gaitClock })
      else if (rig.kind === 'arachnid') pose = spiderPose({ speed: visualSpeed, t: gaitClock })
      /* 巡检车（wheeled）不传 pose：只用 speed + 左右轮速遥测驱动轮子与 LiDAR */
      rig.update({
        dt: dtSec,
        speed: visualSpeed,
        pose,
        wheels: wantStale ? null : props.telemetry?.wheels,
        joints: wantStale ? null : props.telemetry?.joints
      })
      rig.setStale(wantStale)
      /* 关节数据源标注（真机绝对角 / 步态推算），仅变化时写 ref */
      const source = rig.getJointSource?.()
      if (source && source !== jointSource.value) jointSource.value = source
      /* 状态灯由真实业务状态驱动：心跳、急停/故障、障碍距离、电量、运行模式 */
      rig.setBeaconStatus({
        mode: props.mode,
        battery: props.telemetry?.battery,
        obstacleDistance: props.telemetry?.obstacleDistance,
        stale: wantStale
      })
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

    /* 电影感镜头：开场推镜 → 空闲缓慢环绕 / 跟随平滑聚焦 / 俯瞰回中 */
    if (!isSvg) {
      swayClock += dtSec
      if (viewMode.value === 'follow' && robot) focusTarget.set(robot.position.x, 0.46, robot.position.z)
      else focusTarget.copy(BASE_TARGET)
      camTarget.lerp(focusTarget, 1 - Math.pow(0.0025, dtSec))
      let cameraDirty = camTarget.distanceToSquared(focusTarget) > 1e-8
      if (introT < 1) {
        introT = Math.min(1, introT + dtSec / 1.7)
        const ease = 1 - Math.pow(1 - introT, 3)
        orbit.radius = INTRO_FROM.radius + (5.6 - INTRO_FROM.radius) * ease
        orbit.polar = INTRO_FROM.polar + (0.74 - INTRO_FROM.polar) * ease
        cameraDirty = true
      } else if (viewMode.value === 'follow') {
        /* 跟随模式每帧重算：既跟住本体，也让轻微手持感持续生效 */
        cameraDirty = true
      } else if (viewMode.value === 'orbit' && !dragging && now - lastInteractionAt > 4200) {
        orbit.azimuth += dtSec * 0.05
        cameraDirty = true
      }
      if (cameraDirty) applyCamera()

      /* 未完成路点脉冲呼吸：已完成路点保持暗态，不制造假进度 */
      for (let i = 0; i < routeMarkers.length; i += 1) {
        const marker = routeMarkers[i]
        if (marker.userData.done) continue
        const wave = 0.5 + 0.5 * Math.sin(sceneElapsed * 2.2 - i * 0.55)
        marker.scale.setScalar(1 + wave * 0.4)
        marker.material.opacity = 0.5 + wave * 0.4
      }

      /* 氛围层：路线流光 / 雷达扫描 / 告警浮标（告警等级复用状态灯的真实判定） */
      const statusKey = hudStatus.value.key
      cinematic?.update({
        dt: dtSec,
        elapsed: sceneElapsed,
        robot,
        alarmLevel: statusKey === 'fault' ? 2 : statusKey === 'warn' ? 1 : 0,
        degraded: isDegraded(),
        speed: Math.min(moved / Math.max(dtSec, 1e-3), 2),
        mode: props.mode,
        stale: wantStale,
        battery: batteryPercent(props.telemetry?.battery),
        obstacleDistance: props.telemetry?.obstacleDistance
      })
      updateHud(now)
    }

    /* SVG 后端：按「位姿 + 材质状态」签名跳帧，本体静止时不产生任何重绘开销 */
    if (isSvg) {
      const signature = robot
        ? `${robot.position.x.toFixed(3)}|${robot.position.z.toFixed(3)}|${robot.rotation.y.toFixed(3)}|${staleApplied ? 1 : 0}|${alarmApplied ? 1 : 0}`
        : 'empty'
      if (signature === lastSvgSignature) return
      lastSvgSignature = signature
      renderer.render(scene, camera)
      return
    }
    if (isDegraded()) renderer.render(scene, camera)
    else composer.render()
  }, { id: 'robot-scene-3d', fps: isSvg ? 24 : 30 })

  disposeScene = () => {
    unsubscribe()
    ro?.disconnect()
    bloomPass?.dispose()
    composer?.dispose()
    themeObserver?.disconnect()
    element.removeEventListener('click', onStageClick)
    element.removeEventListener('pointerdown', onStagePointerDown)
    element.removeEventListener('pointerup', onStagePointerUp)
    element.removeEventListener('pointercancel', onStagePointerUp)
    element.removeEventListener('pointerleave', onStagePointerUp)
    element.removeEventListener('pointermove', onStageMove)
    element.removeEventListener('wheel', onStageWheel)
    element.style.cursor = ''
    disposeGroupChildren(routeGroup)
    routeMarkers = []
    disposeGroupChildren(trailGroup)
    trailLine = null
    burstRef = null
    cinematic?.dispose()
    cinematic = null
    if (rig) { rig.dispose(); rig = null } else if (robot) { disposeRobotMesh(robot) }
    shadowGeo.dispose()
    shadowMat.dispose()
    envRT?.dispose()
    grid.geometry.dispose()
    grid.material.dispose()
    renderer.dispose?.() /* SVGRenderer 无 dispose，按可选调用处理 */
    if (renderer.domElement.parentNode === element) element.removeChild(renderer.domElement)
    delete window.__rs3d
  }

  /* DEV 调试钩子：性能诊断用（生产构建为 undefined） */
  if (import.meta.env.DEV) {
    window.__rs3d = {
      renderer, scene, camera, backend, canvas: renderer.domElement,
      getStageVisible: () => stageVisible,
      getBloom: () => (bloomPass
        ? { strength: bloomPass.strength, radius: bloomPass.radius, threshold: bloomPass.threshold }
        : null),
      /* rig 状态：用于确认形态已接管、关节数与数据源（车为 0、蜘蛛 16、四足 12、人形 23） */
      getRig: () => (rig
        ? {
            kind: rig.kind,
            jointCount: rig.jointCount || 0,
            wheelCount: rig.wheelCount || 0,
            jointSource: rig.getJointSource?.() ?? null
          }
        : null),
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
/* 镜头视角切换：全景 / 跟随 / 俯瞰 */
watch(viewMode, (mode) => applyViewRef?.(mode))
/* 历史轨迹增长时重建拖尾：轨迹到上限后会「去头追加」，长度不变但末点坐标会变 */
watch(
  () => {
    const list = props.trail
    if (!Array.isArray(list) || !list.length) return '0'
    const last = list[list.length - 1]
    return `${list.length}|${last?.x}|${last?.y}`
  },
  () => syncTrailRef?.()
)
/* 切换设备：轨迹数组会换成另一台设备的历史，即使长度相同也要重建 */
watch(() => props.deviceKey, () => syncTrailRef?.())
/* 打开设备详情时从本体脚下扩散一圈能量脉冲 */
watch(detailsOpen, (open) => { if (open) burstRef?.() })
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
.rs3-views {
  display: flex;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--ds-color-border, #3a3f4a);
  border-radius: 999px;
  background: rgba(120, 140, 170, 0.08);
}
.rs3-view-btn {
  padding: 2px 10px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--ds-color-muted, #8a8f98);
  font-size: 10px;
  cursor: pointer;
  transition: background 150ms ease-out, color 150ms ease-out;
}
.rs3-view-btn.active { background: var(--ds-color-primary, #5b8cff); color: #fff; }
.rs3-view-btn:focus-visible { outline: 2px solid var(--ds-focus-ring-color, var(--smart-primary)); outline-offset: 1px; }
.rs3-stage { position: relative; height: 320px; margin-top: 12px; overflow: hidden; border-radius: 8px; cursor: grab; }
.rs3-stage :deep(canvas) { position: absolute; inset: 0; z-index: 0; display: block; width: 100%; height: 100%; }
.rs3-stage :deep(svg) { position: absolute; inset: 0; z-index: 0; display: block; width: 100%; height: 100%; }
.rs3-vignette {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  border-radius: 8px;
  background:
    radial-gradient(ellipse at 50% 46%, transparent 52%, rgba(4, 8, 16, 0.36) 100%),
    repeating-linear-gradient(to bottom, rgba(255, 255, 255, 0.016) 0 1px, transparent 1px 3px);
}
.rs3-stage::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
  border-radius: 8px;
  pointer-events: none;
  opacity: 0;
  transition: opacity 220ms ease-out;
}
.rs3-stage.is-alarm-warn::before {
  opacity: 1;
  box-shadow: inset 0 0 38px rgba(227, 160, 8, 0.42);
  animation: rs3-alert-pulse 1.8s ease-in-out infinite;
}
.rs3-stage.is-alarm-fault::before {
  opacity: 1;
  box-shadow: inset 0 0 46px rgba(229, 72, 77, 0.55);
  animation: rs3-alert-pulse 1s ease-in-out infinite;
}
@keyframes rs3-alert-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .rs3-stage.is-alarm-warn::before,
  .rs3-stage.is-alarm-fault::before { animation: none; opacity: 0.8; }
}
.rs3-hud {
  position: absolute;
  left: 0;
  top: 0;
  z-index: 3;
  display: grid;
  grid-template-columns: auto auto;
  gap: 1px 10px;
  padding: 5px 9px;
  border: 1px solid rgba(140, 170, 220, 0.38);
  border-radius: 7px;
  background: rgba(10, 16, 28, 0.64);
  color: #e8eefc;
  font-size: 10px;
  line-height: 1.45;
  white-space: nowrap;
  pointer-events: none;
  backdrop-filter: blur(6px);
  transform: translate(-50%, -100%);
  transition: opacity 180ms ease-out;
  will-change: transform;
}
.rs3-hud.is-hidden { opacity: 0; }
/* HUD 指向本体：底部短引导线，强化「标签吸附在设备上」的空间感 */
.rs3-hud::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: -10px;
  width: 1px;
  height: 10px;
  background: linear-gradient(to bottom, rgba(140, 170, 220, 0.7), rgba(140, 170, 220, 0));
}
.rs3-hud-name { display: inline-flex; align-items: center; gap: 5px; font-weight: 600; letter-spacing: 0.04em; }
.rs3-hud-mode { justify-self: end; color: #9fc2ff; }
.rs3-hud-meta { grid-column: 1 / -1; color: #b9c4d6; font-variant-numeric: tabular-nums; }
.rs3-hud-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; background: #5ad691; }
.rs3-hud-dot.is-running { background: #5b8cff; box-shadow: 0 0 6px #5b8cff; }
.rs3-hud-dot.is-manual { background: #57c8d8; box-shadow: 0 0 6px #57c8d8; }
.rs3-hud-dot.is-warn { background: #e3a008; box-shadow: 0 0 6px #e3a008; }
.rs3-hud-dot.is-fault { background: #e5484d; box-shadow: 0 0 6px #e5484d; }
.rs3-hud-dot.is-offline { background: #8a8f98; }
.rs3-stage--static { display: grid; place-items: center; cursor: default; }
.rs3-static-svg { width: 100%; height: 100%; }
.rs3-static-robot { cursor: pointer; }
.rs3-static-note { position: absolute; bottom: 8px; left: 12px; margin: 0; color: var(--ds-color-muted, var(--smart-muted)); font-size: 10px; }
.rs3-caption { margin: 8px 0 0; color: var(--ds-color-muted, var(--smart-muted)); font-size: 11px; line-height: 1.6; }
.rs3-caption--fallback { margin-top: 2px; color: #e3a008; }
@media (max-width: 760px) { .rs3-stage { height: 220px; } .rs3-legend { display: none; } }
</style>
