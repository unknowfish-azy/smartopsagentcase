<template>
  <div class="repo-page">
    <header class="repo-head">
      <div>
        <p class="eyebrow">SMART REPOSITORY · 智能仓库</p>
        <h1>智能仓库</h1>
        <p class="lede">等距 3D 仓库大屏：知识库机架楼、洞察信号塔、云原生集装箱堆垛与 Harbor 罐区箱场坐落在中央货台四角，AGV 沿虚线环线执行孪生巡检，实时回传各区块纠察异常。悬停查看区块，点击进入对应模块（存在异常时直达纠察中心）。</p>
      </div>
    </header>

    <section
      ref="stageEl"
      class="repo-stage"
      :class="{ 'repo-stage--hover': hoveredKey }"
      aria-label="智能仓库 等距 3D 仓库"
      @mousemove="onMouseMove"
      @mouseleave="onMouseLeave"
      @click="onClick"
    >
      <canvas v-show="!isNarrow" ref="canvasEl" class="repo-stage__canvas" />
      <span v-if="!isNarrow" class="repo-stage__mark" aria-hidden="true">{{ patrolReady ? 'DIGITAL TWIN · 构成示意 · 巡检状态为实时数据' : 'DIGITAL TWIN · 构成示意 · 非运行时数据' }}</span>
      <div v-if="!isNarrow" class="repo-stage__hint">ISOMETRIC WAREHOUSE · 悬停查看 / 点击进入</div>
    </section>

    <section class="repo-grid" aria-label="仓库模块列表">
      <button v-for="station in STATIONS" :key="station.key" type="button" class="repo-card" @click="go(station)">
        <i class="repo-card__dot" :style="{ background: station.color, boxShadow: `0 0 10px ${station.color}` }" aria-hidden="true"></i>
        <span class="repo-card__en">{{ station.en }}</span>
        <strong class="repo-card__cn">{{ station.cn }}</strong>
        <small class="repo-card__desc">{{ station.desc }}</small>
        <span v-if="stationBadges[station.key]" class="repo-card__badge" :class="`repo-card__badge--${stationBadges[station.key].level}`">异常 {{ stationBadges[station.key].count }}</span>
        <span class="repo-card__go">进入 →</span>
      </button>
    </section>
  </div>
</template>

<script setup>
/**
 * SmartRepositoryView — 智能仓库 等距 3D 大屏（参考数字孪生仓储构图）
 *
 * 设计（DESIGN: repo-iso-warehouse-v1）：
 *  - canvas 2D 手写等距投影（零依赖，与 agent 工坊视图同路线）；
 *  - 中央货台 + 四个能力区建筑：知识库=机架楼（蓝）、自然语言洞察=信号塔（紫）、
 *    云原生工程=集装箱堆垛（绿）、Harbor 工作台=罐区箱场（金）；
 *  - 孪生巡检（蒸馏自「智巡孪卫」三维数字孪生巡检视图）：AGV 环线即巡检路线
 *    （虚线），建筑顶部状态气泡 / 模块卡徽标来自纠察中心真实数据（60s 轮询），
 *    异常区块点击直达 /inspector；
 *  - 氛围层：地面网格、雷达环、AGV 环线巡航、信标脉冲 —— 均为构成示意装饰；
 *  - 悬停区块高亮 + 标签，点击进入对应路由（页面职能仍是聚合导航）；
 *  - 降级红线：prefers-reduced-motion / visualMode 非 balanced → 静态一帧
 *    （保留 hover / click，不轮询、气泡无脉动），窄屏（<768px）隐藏 canvas 只出模块卡列表；
 *  - 证据规则：巡检计数全部来自真实接口，接口失败静默降级为全 ok 并标注
 *    「构成示意 · 非运行时数据」，绝不显示伪造运维数字。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { visualMode } from '../../visual/visualMode'
import { getInspectorEvents, getInspectorSummary } from '../../api/inspector'
import { mapSummaryToZones } from '../../utils/repoPatrol'

const router = useRouter()

const STATIONS = [
  { key: 'knowledge', cn: '知识库', en: 'KNOWLEDGE', to: '/knowledge/space', desc: '知识空间 · 蒸馏图谱 · 溯源问答 · 研究资料', color: '#58c4ff', x: -2.35, y: -2.35, kind: 'rack' },
  { key: 'insights', cn: '自然语言洞察', en: 'NL INSIGHTS', to: '/insights', desc: '一句话问出数据答案，智能生成洞察图表', color: '#a78bfa', x: 2.35, y: -2.35, kind: 'tower' },
  { key: 'cloud-native', cn: '云原生工程', en: 'CLOUD NATIVE', to: '/cloud-native', desc: '容器 · 编排 · 集群只读工程工作台', color: '#3fb950', x: -2.35, y: 2.35, kind: 'stack' },
  { key: 'harbor', cn: 'Harbor 工作台', en: 'HARBOR', to: '/harbor', desc: '镜像仓库 · 项目 · 扫描报告速览', color: '#d29922', x: 2.35, y: 2.35, kind: 'yard' }
]

const stageEl = ref(null)
const canvasEl = ref(null)
const hoveredKey = ref('')
const isNarrow = ref(false)

const width = ref(0)
const height = ref(0)
let frameId = null
let resizeObserver = null
let motionMedia = null
let reduceHit = false
let phase = 0
let lastTs = null
let mouseNX = 0 // -1 ~ 1 视差目标
let camX = 0 // 摄像机横向摇摆（缓动）
// 悬停检测缓存：key → 屏幕坐标
const screenCenters = new Map()
// 固定星空（确定性伪随机，只生成一次）
const STARS = (() => {
  let seed = 20260116
  const rand = () => {
    seed = (seed * 16807) % 2147483647
    return seed / 2147483647
  }
  return Array.from({ length: 90 }, () => ({ x: rand(), y: rand(), size: rand() < 0.82 ? 1 : 1.6, base: 0.14 + rand() * 0.4, twinkle: rand() * Math.PI * 2 }))
})()

const isStatic = () => reduceHit || visualMode.value !== 'balanced'

/* ---------------------------- 孪生巡检数据 ---------------------------- */

// 纠察中心真实数据（repoPatrol.mapSummaryToZones）：zone key → { warningCount, criticalCount, level }
const patrolZones = ref({})
// 是否拿到真实接口数据：决定角标文案与徽标显隐；接口失败静默降级为全 ok
const patrolReady = ref(false)
let patrolTimer = null
const PATROL_POLL_MS = 60000 // 每 60s 轮询一次；静态档位（reduced-motion / lightweight）不轮询，仅加载一次

async function loadPatrol() {
  let summary = null
  let events = []
  let hasData = false
  try {
    const res = await getInspectorSummary()
    summary = res?.data || null
    if (summary) hasData = true
  } catch { /* summary 失败不阻塞 events */ }
  try {
    const res = await getInspectorEvents(50)
    if (res) hasData = true
    events = Array.isArray(res?.data) ? res.data : []
  } catch { /* events 失败不阻塞 summary */ }
  if (!hasData) {
    // 两个接口都失败：静默降级为全部 ok，绝不显示假数据
    patrolZones.value = {}
    patrolReady.value = false
    refreshStaticFrame()
    return
  }
  const mapped = mapSummaryToZones(summary, events)
  patrolZones.value = mapped.zones
  patrolReady.value = true
  refreshStaticFrame()
}

/** 巡检数据更新后的补绘：动态档位由 rAF 循环自然刷新，静态档位需手动重绘一帧 */
function refreshStaticFrame() {
  if (!isNarrow.value && canvasEl.value && width.value && isStatic()) draw()
}

function hexToRgb(hex) {
  const value = parseInt(hex.slice(1), 16)
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}

/* ---------------------------- 等距投影 ---------------------------- */

// 视图状态：draw() 每帧更新；等距单位 tile = 1 格
const view = { cx: 0, cy: 0, k: 0 }

/** 世界坐标 (x, y, z) → 相对画布中心的屏幕偏移（等距 2:1） */
function isoP(x, y, z) {
  return {
    x: (x - y) * view.k + camX * view.k * 0.5,
    y: (x + y) * view.k * 0.5 - z * view.k
  }
}

function pt(p) {
  return { x: view.cx + p.x, y: view.cy + p.y }
}

function shade(rgb, f, a) {
  return `rgba(${Math.round(rgb[0] * f)}, ${Math.round(rgb[1] * f)}, ${Math.round(rgb[2] * f)}, ${a})`
}

function poly(context, points, fill) {
  context.beginPath()
  points.forEach((p, i) => (i === 0 ? context.moveTo(p.x, p.y) : context.lineTo(p.x, p.y)))
  context.closePath()
  context.fillStyle = fill
  context.fill()
  context.strokeStyle = 'rgba(232, 242, 247, 0.16)'
  context.lineWidth = 1
  context.stroke()
}

/** 等距立方体：右面（暗）→ 左面（中）→ 顶面（亮） */
function drawBox(context, x, y, w, d, h, rgb, topBoost = 1.3) {
  const t = [pt(isoP(x, y, h)), pt(isoP(x + w, y, h)), pt(isoP(x + w, y + d, h)), pt(isoP(x, y + d, h))]
  const g = [pt(isoP(x + w, y, 0)), pt(isoP(x + w, y + d, 0)), pt(isoP(x, y + d, 0))]
  poly(context, [t[1], t[2], g[1], g[0]], shade(rgb, 0.52, 0.96))
  poly(context, [t[2], t[3], g[2], g[1]], shade(rgb, 0.8, 0.96))
  poly(context, t, shade(rgb, topBoost, 0.98))
}

/** 地面椭圆（世界平面圆的等距投影） */
function groundEllipse(context, x, y, r, stroke, width = 1) {
  const c = pt(isoP(x, y, 0))
  context.strokeStyle = stroke
  context.lineWidth = width
  context.beginPath()
  context.ellipse(c.x, c.y, r * view.k * 1.41, r * view.k * 0.71, 0, 0, Math.PI * 2)
  context.stroke()
}

/* ---------------------------- 场景元素 ---------------------------- */

function drawGround(context) {
  // 货台菱形
  const corners = [pt(isoP(-4.4, -4.4, 0)), pt(isoP(4.4, -4.4, 0)), pt(isoP(4.4, 4.4, 0)), pt(isoP(-4.4, 4.4, 0))]
  context.beginPath()
  corners.forEach((p, i) => (i === 0 ? context.moveTo(p.x, p.y) : context.lineTo(p.x, p.y)))
  context.closePath()
  const fill = context.createLinearGradient(0, view.cy - 4 * view.k, 0, view.cy + 4 * view.k)
  fill.addColorStop(0, 'rgba(21, 34, 52, 0.9)')
  fill.addColorStop(1, 'rgba(10, 19, 32, 0.95)')
  context.fillStyle = fill
  context.fill()
  context.strokeStyle = 'rgba(122, 215, 245, 0.22)'
  context.lineWidth = 1
  context.stroke()

  // 台面网格
  context.strokeStyle = 'rgba(122, 215, 245, 0.07)'
  for (let i = -4; i <= 4; i += 1) {
    let a = pt(isoP(i, -4.4, 0))
    let b = pt(isoP(i, 4.4, 0))
    context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke()
    a = pt(isoP(-4.4, i, 0))
    b = pt(isoP(4.4, i, 0))
    context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke()
  }

  // 中央雷达：扩散环 + 旋转扫掠
  const pulse = (phase * 0.0006) % 1
  groundEllipse(context, 0, 0, 0.4 + pulse * 1.1, `rgba(122, 215, 245, ${(0.3 * (1 - pulse)).toFixed(3)})`)
  groundEllipse(context, 0, 0, 1.5, 'rgba(122, 215, 245, 0.14)')
  const sweep = pt(isoP(Math.cos(phase * 0.001) * 1.45, Math.sin(phase * 0.001) * 1.45, 0))
  const origin = pt(isoP(0, 0, 0))
  context.strokeStyle = 'rgba(122, 215, 245, 0.28)'
  context.beginPath(); context.moveTo(origin.x, origin.y); context.lineTo(sweep.x, sweep.y); context.stroke()
  context.fillStyle = 'rgba(122, 215, 245, 0.9)'
  context.beginPath(); context.arc(origin.x, origin.y, 2.6, 0, Math.PI * 2); context.fill()
}

function drawPatrolRoute(context) {
  // AGV 环线巡检路线：虚线圆环（等距椭圆投影），静态档位同样绘制但无动画
  const segments = 64
  context.save()
  context.setLineDash([5, 7])
  context.strokeStyle = 'rgba(122, 215, 245, 0.26)'
  context.lineWidth = 1.2
  context.beginPath()
  for (let i = 0; i <= segments; i += 1) {
    const angle = (i / segments) * Math.PI * 2
    const p = pt(isoP(Math.cos(angle) * 1.45, Math.sin(angle) * 1.45, 0.02))
    if (i === 0) context.moveTo(p.x, p.y)
    else context.lineTo(p.x, p.y)
  }
  context.closePath()
  context.stroke()
  context.restore()
}

function drawRack(context, z, rgb) {
  // 知识库：机架楼 —— 高层机柜 + 楼层灯带 + 屋顶信标
  const { x, y } = z
  drawBox(context, x - 0.85, y - 0.85, 1.7, 1.7, 2.6, rgb)
  // 楼层灯带（左 + 右面横线）
  for (let i = 1; i <= 5; i += 1) {
    const zz = 0.35 * i
    const a = pt(isoP(x + 0.85, y - 0.85, zz))
    const b = pt(isoP(x + 0.85, y + 0.85, zz))
    context.strokeStyle = shade(rgb, 1.5, 0.4)
    context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke()
    const c = pt(isoP(x - 0.85, y + 0.85, zz))
    context.beginPath(); context.moveTo(b.x, b.y); context.lineTo(c.x, c.y); context.stroke()
  }
  // 屋顶信标脉冲
  const tip = pt(isoP(x, y, 2.85))
  const glow = 3 + Math.sin(phase * 0.004) * 1.6
  const halo = context.createRadialGradient(tip.x, tip.y, 0, tip.x, tip.y, glow * 3)
  halo.addColorStop(0, shade(rgb, 1.6, 0.55))
  halo.addColorStop(1, shade(rgb, 1.6, 0))
  context.fillStyle = halo
  context.beginPath(); context.arc(tip.x, tip.y, glow * 3, 0, Math.PI * 2); context.fill()
  context.fillStyle = shade(rgb, 1.7, 0.95)
  context.beginPath(); context.arc(tip.x, tip.y, glow, 0, Math.PI * 2); context.fill()
}

function drawTower(context, z, rgb) {
  // 自然语言洞察：信号塔 —— 塔身 + 天线 + 电波脉冲
  const { x, y } = z
  drawBox(context, x - 0.65, y - 0.65, 1.3, 1.3, 1.3, rgb)
  drawBox(context, x - 0.4, y - 0.4, 0.8, 0.8, 1.9, rgb, 1.5)
  const base = pt(isoP(x, y, 1.9))
  const tip = pt(isoP(x, y, 2.9))
  context.strokeStyle = shade(rgb, 1.4, 0.9)
  context.lineWidth = 1.4
  context.beginPath(); context.moveTo(base.x, base.y); context.lineTo(tip.x, tip.y); context.stroke()
  // 电波：两圈扩散环（屏幕空间圆）
  const pulse = (phase * 0.0009) % 1
  context.strokeStyle = shade(rgb, 1.5, (0.5 * (1 - pulse)).toFixed(3))
  context.beginPath(); context.arc(tip.x, tip.y, 5 + pulse * 16, 0, Math.PI * 2); context.stroke()
  context.fillStyle = shade(rgb, 1.7, 0.95)
  context.beginPath(); context.arc(tip.x, tip.y, 3, 0, Math.PI * 2); context.fill()
}

function drawStack(context, z, rgb) {
  // 云原生工程：集装箱堆垛 —— 三层错位堆放
  const { x, y } = z
  const layers = [
    { dx: -0.75, dy: -0.6, z: 0 },
    { dx: -0.62, dy: -0.72, z: 0.5 },
    { dx: -0.7, dy: -0.66, z: 1.0 }
  ]
  layers.forEach((layer, i) => {
    drawBox(context, x + layer.dx, y + layer.dy, 1.5, 1.2, 0.5, rgb, i === 2 ? 1.45 : 1.25)
  })
  // 堆垛顶指示灯
  const tip = pt(isoP(x, y, 1.6))
  context.fillStyle = shade(rgb, 1.8, 0.9)
  context.beginPath(); context.arc(tip.x, tip.y, 2.6, 0, Math.PI * 2); context.fill()
}

function drawYard(context, z, rgb) {
  // Harbor：罐区箱场 —— 3×3 小罐箱，其中一箱周期性高亮（危险品巡检示意）
  const { x, y } = z
  const glowIdx = Math.floor(phase * 0.0011) % 9
  for (let i = 0; i < 3; i += 1) {
    for (let j = 0; j < 3; j += 1) {
      const idx = i * 3 + j
      const gx = x + 0.15 + i * 0.58
      const gy = y + 0.15 + j * 0.58
      drawBox(context, gx, gy, 0.44, 0.44, 0.36, rgb, idx === glowIdx ? 1.7 : 1.2)
      if (idx === glowIdx) {
        const c = pt(isoP(gx + 0.22, gy + 0.22, 0.36))
        const halo = context.createRadialGradient(c.x, c.y, 0, c.x, c.y, 16)
        halo.addColorStop(0, 'rgba(255, 196, 120, 0.5)')
        halo.addColorStop(1, 'rgba(255, 196, 120, 0)')
        context.fillStyle = halo
        context.beginPath(); context.arc(c.x, c.y, 16, 0, Math.PI * 2); context.fill()
      }
    }
  }
}

function drawAgv(context, index) {
  // AGV 巡航：环线 r=1.45，三台错相位，白色车灯 + 拖尾
  const angle = phase * 0.0007 + index * ((Math.PI * 2) / 3)
  const x = Math.cos(angle) * 1.45
  const y = Math.sin(angle) * 1.45
  const tail = 0.16
  const t2 = pt(isoP(Math.cos(angle - tail) * 1.45, Math.sin(angle - tail) * 1.45, 0.06))
  const c = pt(isoP(x, y, 0.06))
  context.strokeStyle = 'rgba(191, 230, 255, 0.3)'
  context.lineWidth = 2.4
  context.beginPath(); context.moveTo(t2.x, t2.y); context.lineTo(c.x, c.y); context.stroke()
  context.fillStyle = 'rgba(232, 250, 255, 0.95)'
  context.beginPath(); context.arc(c.x, c.y, 3, 0, Math.PI * 2); context.fill()
  const halo = context.createRadialGradient(c.x, c.y, 0, c.x, c.y, 10)
  halo.addColorStop(0, 'rgba(191, 230, 255, 0.4)')
  halo.addColorStop(1, 'rgba(191, 230, 255, 0)')
  context.fillStyle = halo
  context.beginPath(); context.arc(c.x, c.y, 10, 0, Math.PI * 2); context.fill()
}

// 状态气泡语义色：警告琥珀系 / 危险红系（沿用项目既有色值）
const LEVEL_COLORS = { warn: '#d29922', alert: '#f85149' }
// 各建筑造型的气泡世界高度（机架楼 / 信号塔顶、堆垛顶、罐区顶）
const BUBBLE_Z = { rack: 3.15, tower: 3.15, stack: 1.95, yard: 0.95 }

/** 孪生巡检状态气泡：level!=='ok' 的区块在建筑顶部显示真实异常计数 */
function drawStatusBubble(context, station, info) {
  const rgb = hexToRgb(LEVEL_COLORS[info.level] || LEVEL_COLORS.warn)
  const count = info.warningCount + info.criticalCount
  const tip = pt(isoP(station.x, station.y, BUBBLE_Z[station.kind] ?? 2.4))
  // 静态档位无脉动：光环半径与透明度固定
  const pulse = isStatic() ? 0.5 : 0.5 + Math.sin(phase * 0.005) * 0.5
  const halo = context.createRadialGradient(tip.x, tip.y, 0, tip.x, tip.y, 18)
  halo.addColorStop(0, shade(rgb, 1.3, (0.38 * pulse).toFixed(3)))
  halo.addColorStop(1, shade(rgb, 1.3, 0))
  context.fillStyle = halo
  context.beginPath(); context.arc(tip.x, tip.y, 18, 0, Math.PI * 2); context.fill()
  context.fillStyle = shade(rgb, 1.05, 0.95)
  context.beginPath(); context.arc(tip.x, tip.y, 9, 0, Math.PI * 2); context.fill()
  context.strokeStyle = 'rgba(232, 242, 247, 0.45)'
  context.lineWidth = 1
  context.stroke()
  context.fillStyle = 'rgba(255, 248, 240, 0.96)'
  context.font = '700 10px ui-monospace, monospace'
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  context.fillText(String(count), tip.x, tip.y + 0.5)
  context.textBaseline = 'alphabetic'
  context.textAlign = 'left'
}

function drawZone(context, station) {
  const rgb = hexToRgb(station.color)
  const hovered = hoveredKey.value === station.key
  const patrol = patrolZones.value?.[station.key]

  // 悬停：地块光环
  if (hovered) {
    groundEllipse(context, station.x, station.y, 1.6, shade(rgb, 1.4, 0.65), 1.6)
    groundEllipse(context, station.x, station.y, 1.85, shade(rgb, 1.4, 0.3))
  }

  if (station.kind === 'rack') drawRack(context, station, rgb)
  else if (station.kind === 'tower') drawTower(context, station, rgb)
  else if (station.kind === 'stack') drawStack(context, station, rgb)
  else drawYard(context, station, rgb)

  // 孪生巡检：存在异常（warn/alert）的区块绘制建筑顶部状态气泡
  if (patrol && patrol.level !== 'ok') drawStatusBubble(context, station, patrol)

  // 标签锚点（供悬停拾取）
  const anchor = pt(isoP(station.x, station.y, 0))
  screenCenters.set(station.key, anchor)
  const labelAlpha = hovered ? 1 : 0.72
  context.font = '600 13px ui-monospace, monospace'
  context.textAlign = 'center'
  context.fillStyle = `rgba(232, 242, 247, ${labelAlpha})`
  context.fillText(station.cn, anchor.x, anchor.y + 30)
  context.font = '9px ui-monospace, monospace'
  context.fillStyle = shade(rgb, 1.3, labelAlpha)
  context.fillText(station.en, anchor.x, anchor.y + 44)
  // hover 状态气泡的区块：标签行追加真实计数「告警 N · 严重 M」
  if (hovered && patrol && patrol.level !== 'ok') {
    context.font = '10px ui-monospace, monospace'
    context.fillStyle = shade(hexToRgb(LEVEL_COLORS[patrol.level]), 1.45, 0.92)
    context.fillText(`告警 ${patrol.warningCount} · 严重 ${patrol.criticalCount}`, anchor.x, anchor.y + 58)
  }
  context.textAlign = 'left'
}

function draw() {
  const canvas = canvasEl.value
  if (!canvas) return
  const context = canvas.getContext('2d')
  if (!context) return

  const dpr = Math.min(2, globalThis.devicePixelRatio || 1)
  const w = width.value
  const h = height.value
  const pixelW = Math.round(w * dpr)
  const pixelH = Math.round(h * dpr)
  if (canvas.width !== pixelW || canvas.height !== pixelH) {
    canvas.width = pixelW
    canvas.height = pixelH
    canvas.style.width = `${w}px`
    canvas.style.height = `${h}px`
  }
  context.setTransform(dpr, 0, 0, dpr, 0, 0)
  context.clearRect(0, 0, w, h)

  // 等距单位：货台对角宽 17.6 单位，按画布宽换算；同时保证纵向（约 11.6 单位）不溢出
  view.k = Math.min(w / 19, h / 12)
  view.cx = w / 2
  view.cy = h / 2 + view.k * 0.8 // 留出建筑高度空间，构图重心下移

  // 星空（低存在感背景）
  STARS.forEach((star) => {
    const twinkle = isStatic() ? 0.5 : 0.5 + Math.sin(phase * 0.002 + star.twinkle) * 0.5
    context.fillStyle = `rgba(210, 235, 250, ${(star.base * (0.4 + twinkle * 0.6)).toFixed(3)})`
    context.fillRect(star.x * w, star.y * h * 0.85, star.size, star.size)
  })

  drawGround(context)
  drawPatrolRoute(context)

  // 画家算法：AGV 与建筑按世界深度 (x+y) 统一排序绘制
  const renderables = [
    ...STATIONS.map(station => ({ depth: station.x + station.y, draw: () => drawZone(context, station) })),
    ...[0, 1, 2].map(index => ({ depth: Math.cos(phase * 0.0007 + index * 2.094) * 1.45 + Math.sin(phase * 0.0007 + index * 2.094) * 1.45, draw: () => drawAgv(context, index) }))
  ]
  renderables.sort((a, b) => a.depth - b.depth).forEach(item => item.draw())
}

function tick(timestamp) {
  if (lastTs == null) lastTs = timestamp
  phase += Math.min(64, timestamp - lastTs)
  lastTs = timestamp
  // 视差摇摆缓动
  camX += (mouseNX * 0.9 - camX) * 0.05
  draw()
  frameId = requestAnimationFrame(tick)
}

function restart() {
  if (frameId != null) {
    cancelAnimationFrame(frameId)
    frameId = null
  }
  lastTs = null
  if (isNarrow.value || !canvasEl.value || !width.value) return
  if (isStatic()) draw()
  else frameId = requestAnimationFrame(tick)
}

function measure() {
  const rect = stageEl.value?.getBoundingClientRect()
  width.value = Math.max(320, Math.round(rect?.width || 720))
  height.value = Math.max(260, Math.round(rect?.height || 380))
  isNarrow.value = globalThis.innerWidth < 768
  restart()
}

function pickStation(clientX, clientY) {
  const rect = canvasEl.value?.getBoundingClientRect()
  if (!rect) return null
  const x = clientX - rect.left
  const y = clientY - rect.top
  let best = null
  let bestDist = 72
  screenCenters.forEach((pos, key) => {
    const dist = Math.hypot(pos.x - x, pos.y - y)
    if (dist < bestDist) {
      bestDist = dist
      best = key
    }
  })
  return best
}

function onMouseMove(event) {
  const rect = stageEl.value?.getBoundingClientRect()
  if (rect) mouseNX = ((event.clientX - rect.left) / rect.width - 0.5) * 2
  const key = pickStation(event.clientX, event.clientY)
  hoveredKey.value = key || ''
  if (stageEl.value) stageEl.value.style.cursor = key ? 'pointer' : 'default'
}
function onMouseLeave() {
  mouseNX = 0
  camX = 0
  hoveredKey.value = ''
}
function onClick(event) {
  const key = pickStation(event.clientX, event.clientY)
  const station = STATIONS.find(item => item.key === key)
  if (station) go(station)
}
function go(station) {
  // 孪生巡检联动：存在异常（warn/alert）的区块点击直达纠察中心
  const patrol = patrolZones.value?.[station?.key]
  const target = patrol && patrol.level !== 'ok' ? '/inspector' : station?.to
  if (target) router.push(target)
}

// 模块卡徽标：每个模块的真实异常计数（数据失败 / 全 ok 时不显示）
const stationBadges = computed(() => {
  const map = {}
  if (!patrolReady.value) return map
  for (const station of STATIONS) {
    const patrol = patrolZones.value?.[station.key]
    if (patrol && patrol.level !== 'ok') {
      map[station.key] = { count: patrol.warningCount + patrol.criticalCount, level: patrol.level }
    }
  }
  return map
})

onMounted(() => {
  try {
    motionMedia = globalThis.matchMedia('(prefers-reduced-motion: reduce)')
    reduceHit = motionMedia.matches
    motionMedia.addEventListener?.('change', onMotionChange)
  } catch {
    /* 能力探测不可用时按完整档位运行 */
  }
  measure()
  resizeObserver = new ResizeObserver(measure)
  if (stageEl.value) resizeObserver.observe(stageEl.value)
  // 孪生巡检：首屏加载一次；动态档位下每 60s 轮询，静态档位不轮询
  loadPatrol()
  if (!isStatic()) patrolTimer = setInterval(loadPatrol, PATROL_POLL_MS)
})

function onMotionChange(event) {
  reduceHit = event.matches
  restart()
}

onBeforeUnmount(() => {
  if (frameId != null) cancelAnimationFrame(frameId)
  if (patrolTimer != null) clearInterval(patrolTimer)
  resizeObserver?.disconnect()
  motionMedia?.removeEventListener?.('change', onMotionChange)
})
</script>

<style scoped>
.repo-page {
  display: grid;
  gap: 18px;
  padding: 22px;
  color: var(--smart-text, #e8f2f7);
  background: var(--smart-bg, #071018);
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 12px;
}
.repo-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 16px; }
.eyebrow { margin: 0 0 6px; color: var(--smart-primary-strong, #7ad7f5); font: 11px var(--font-mono, ui-monospace, monospace); letter-spacing: .1em; }
.repo-head h1 { margin: 0; font-size: 28px; font-weight: 500; }
.lede { margin: 6px 0 0; color: var(--smart-muted, #92a6b5); font-size: 13px; line-height: 1.6; }
/* 等距仓库舞台 */
.repo-stage {
  position: relative;
  height: clamp(420px, 58vh, 640px);
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 12px;
  overflow: hidden;
  background:
    radial-gradient(85% 65% at 50% 45%, rgba(36, 150, 237, .13), transparent 62%),
    linear-gradient(180deg, rgba(4, 10, 18, .55), rgba(4, 10, 18, .95));
}
.repo-stage--hover { border-color: var(--smart-primary-strong, #7ad7f5); }
.repo-stage__canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
.repo-stage__mark {
  position: absolute;
  left: 14px;
  top: 12px;
  color: rgba(122, 215, 245, .42);
  font: 9px var(--font-mono, ui-monospace, monospace);
  letter-spacing: .14em;
  pointer-events: none;
}
.repo-stage__hint {
  position: absolute;
  right: 14px;
  bottom: 10px;
  color: rgba(122, 215, 245, .5);
  font: 10px var(--font-mono, ui-monospace, monospace);
  letter-spacing: .12em;
  pointer-events: none;
}
/* 模块卡列表（窄屏 / 无障碍兜底） */
.repo-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.repo-card {
  position: relative;
  display: grid;
  gap: 6px;
  justify-items: start;
  padding: 16px;
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 10px;
  background: var(--smart-surface, #151a21);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 160ms ease, transform 160ms ease;
}
.repo-card:hover { border-color: var(--smart-primary-strong, #7ad7f5); transform: translateY(-2px); }
.repo-card__dot { width: 8px; height: 8px; border-radius: 50%; }
.repo-card__en { color: var(--smart-muted, #92a6b5); font: 10px var(--font-mono, ui-monospace, monospace); letter-spacing: .1em; }
.repo-card__cn { font-size: 16px; font-weight: 500; }
.repo-card__desc { color: var(--smart-muted, #92a6b5); font-size: 12px; line-height: 1.5; }
.repo-card__go { color: var(--smart-primary-strong, #7ad7f5); font-size: 12px; }
/* 孪生巡检异常徽标：真实纠察计数（琥珀=warn，红=alert） */
.repo-card__badge {
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 2px 9px;
  border-radius: 999px;
  font: 10px var(--font-mono, ui-monospace, monospace);
  letter-spacing: .04em;
  transition: border-color 160ms ease, background-color 160ms ease;
}
.repo-card__badge--warn { color: #f0b72f; border: 1px solid rgba(210, 153, 34, .5); background: rgba(210, 153, 34, .14); }
.repo-card__badge--alert { color: #ff8f7a; border: 1px solid rgba(248, 81, 73, .5); background: rgba(248, 81, 73, .12); }
@media (max-width: 1100px) { .repo-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 767px) {
  .repo-page { padding: 16px; }
  .repo-grid { grid-template-columns: 1fr; }
  .repo-stage { min-height: 260px; }
}
@media (prefers-reduced-motion: reduce) {
  .repo-card, .repo-card__badge { transition: none; }
}
</style>
