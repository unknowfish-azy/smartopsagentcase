<template>
  <div class="vos3d-wrap" :class="{ 'vos3d-wrap--narrow': narrow }">
    <div ref="host" class="vos3d-stage" role="img" :aria-label="ariaLabel" tabindex="0"></div>

    <!-- 降级/无 WebGL 的静态拓扑图：用 SVG 表达同样的资产与链路 -->
    <svg v-if="staticMode" class="vos3d-static" viewBox="0 0 760 360" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <g :stroke="linkStroke('up')" stroke-width="1">
        <line v-for="l in staticLinks" :key="l.id" :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2" :stroke="linkStroke(l.status)" :stroke-dasharray="(l.status === 'down' || l.status === 'degraded') ? '5 4' : undefined" />
      </g>
      <g v-for="node in staticNodes" :key="node.id">
        <rect :x="node.x - node.w / 2" :y="node.y - node.h / 2" :width="node.w" :height="node.h" :rx="node.rx" :fill="statusColor(node.status)" :stroke="'var(--ds-color-text)'" stroke-width="0.6" :opacity="node.kind === 'rack' ? 0.92 : 1" />
        <text :x="node.x" :y="node.y + 3" text-anchor="middle" :fill="'var(--ds-color-text)'" font-size="7">{{ node.label }}</text>
      </g>
      <g v-if="staticFirewall">
        <circle :cx="staticFirewall.x" :cy="staticFirewall.y" r="12" fill="none" :stroke="statusColor('down')" stroke-width="1.4" stroke-dasharray="3 2" />
        <text :x="staticFirewall.x" :y="staticFirewall.y - 14" text-anchor="middle" :fill="statusColor('down')" font-size="7" font-weight="bold">ACL DENY</text>
      </g>
      <!-- 静态模式：前向预测徽章（正交投影，无需相机追踪） -->
      <g v-for="b in staticPredictionBadges" :key="'spb-' + b.id">
        <rect :x="b.x - b.w / 2" :y="b.y - 8" :width="b.w" height="15" rx="3" fill="rgba(2,6,23,0.78)" :stroke="b.color" stroke-width="0.9" />
        <text :x="b.x" :y="b.y + 2.5" text-anchor="middle" :fill="b.color" font-size="7" font-weight="600">{{ b.text }}</text>
      </g>
      <text x="380" y="20" text-anchor="middle" :fill="'var(--ds-color-muted)'" font-size="11">虚拟运维拓扑 · 静态单帧（轻量/无障碍模式）</text>
    </svg>

    <!-- WebGL 模式：前向预测悬浮徽章，每帧由 3D→2D 投影重定位；点击定位到首次劣化帧 -->
    <div v-if="!staticMode && predictions.length" ref="badgeLayer" class="vos3d-badges" role="group" aria-label="资产后果预测，可激活定位到首次劣化帧">
      <button
        v-for="(p, i) in predictions"
        :key="'pb-' + p.id"
        :ref="(el) => setBadgeEl(i, el)"
        type="button"
        class="vos3d-badge"
        :class="{ 'is-core': p.criticality === 'core' }"
        :style="{ '--bc': predictionColor(p.worstStatus) }"
        :aria-label="`${predictionText(p)}，激活定位到该帧`"
        @click="emit('focus-prediction', p)"
      >
        <span class="vos3d-badge__dot"></span>{{ predictionText(p) }}
      </button>
    </div>

    <div class="vos3d-legend" aria-hidden="true">
      <span v-for="item in legendItems" :key="item.key"><i class="vos3d-dot" :style="{ '--c': item.color }"></i>{{ item.label }}</span>
    </div>
    <p class="vos3d-hint">{{ staticMode ? '静态拓扑' : '拖拽旋转 · 滚轮缩放 · 点击资产' }}</p>
  </div>
</template>

<script setup>
/**
 * VirtualOpsScene3D — 虚拟运维场景 3D 舞台。
 * 只消费父级传入的 topology / currentSnapshot / targetId / selectedAssetId，
 * 不请求、不轮询、不伪造；颜色与动画强度全部由 domain 快照推导。
 * 遵循项目 P3 性能收口：单一共享 rAF（motionScheduler），reduced-motion / lightweight 降级。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AmbientLight, BoxGeometry, BufferAttribute, BufferGeometry, Color, CylinderGeometry,
  DirectionalLight, Group, LineBasicMaterial, LineSegments, Mesh, MeshStandardMaterial,
  PerspectiveCamera, Raycaster, Scene, SphereGeometry, TorusGeometry, Vector2, Vector3, WebGLRenderer
} from 'three'
import { subscribe } from '../../visual/motionScheduler.js'
import { isLightweightVisualMode, isReducedMotionMode } from '../../visual/visualMode.js'
import { STATUS_COLORS, STATUS_LABELS, STATUS_RANK } from '../../domain/sentinel/virtualOpsScene.js'

const props = defineProps({
  topology: { type: Object, required: true },
  snapshot: { type: Object, default: null },
  // 前向预测：每个资产在整段推演时间窗内的峰值（最坏）状态，用于画布悬浮徽章。
  predictions: { type: Array, default: () => [] },
  targetId: { type: String, default: '' },
  selectedAssetId: { type: String, default: '' },
  narrow: { type: Boolean, default: false }
})
const emit = defineEmits(['select', 'focus-prediction'])

const host = ref(null)
// WebGL 创建失败时同样降级到静态 SVG，避免徽章层留在默认位置、全部叠在左上角。
const webglFailed = ref(false)
const staticMode = computed(() => props.narrow || isLightweightVisualMode.value || isReducedMotionMode.value || webglFailed.value)
// WebGL 模式下的悬浮预测徽章层：HTML 覆盖在画布上，每帧按 3D→2D 投影重定位。
const badgeLayer = ref(null)
const badgeEls = []
const badgeWidths = new Map() // 徽章 id -> 实测宽度（文本固定，测量一次即可复用）
function setBadgeEl(index, el) { badgeEls[index] = el || null }

// 统一引用 domain 色板，保证 3D 网格 / 徽章 / 图例色值一致不漂移。
const STATUS_COLOR = STATUS_COLORS
const statusColor = s => STATUS_COLOR[s] || '#94a3b8'
const legendItems = computed(() => (['ok', 'degraded', 'warn', 'critical', 'down']).map(k => ({
  key: k, label: STATUS_LABELS[k], color: STATUS_COLOR[k]
})))

const ariaLabel = computed(() => {
  if (!props.snapshot) return '虚拟运维场景三维拓扑，未选择操作'
  const s = props.snapshot
  const down = Object.values(s.racks || {}).filter(r => r.status === 'down').length
  const preds = props.predictions
  let peak = ''
  if (preds.length) {
    const worst = preds.reduce((a, p) => ((STATUS_RANK[p.worstStatus] ?? -1) > (STATUS_RANK[a.worstStatus] ?? -1) ? p : a), preds[0])
    peak = `；前向预测 ${preds.length} 个资产将劣化，最严重为「${STATUS_LABELS[worst.worstStatus] || worst.worstStatus}」`
  }
  return `虚拟运维场景三维拓扑，当前预测第 ${s.tick} 步，中断机柜 ${down} 台，广播风暴 ${s.broadcastStorm ? '是' : '否'}${peak}`
})

/* ----------------------------- 静态 SVG 投影 ----------------------------- */
const STATIC_VIEW_W = 760
const STATIC_VIEW_H = 360
function project(x, z) {
  // 拓扑范围 x∈[-6.6,6.6], z∈[-5.8,4.7]；映射到固定 viewBox 画布。
  const cx = STATIC_VIEW_W / 2 + x * 46
  const cy = STATIC_VIEW_H / 2 + z * 26
  return { x: cx, y: cy }
}
const devicePositions = computed(() => {
  const map = new Map()
  for (const r of props.topology.racks) map.set(r.id, { x: r.x, z: r.z, kind: 'rack', label: r.label })
  for (const s of props.topology.switches) map.set(s.id, { x: s.x, z: s.z, kind: 'switch', label: s.id })
  for (const r of props.topology.routers) map.set(r.id, { x: r.x, z: r.z, kind: 'router', label: r.id })
  for (const g of props.topology.gateways) map.set(g.id, { x: g.x, z: g.z, kind: 'gateway', label: g.id })
  for (const c of props.topology.coolers) map.set(c.id, { x: c.x, z: c.z, kind: 'cooler', label: c.id })
  return map
})
function deviceStatus(id) {
  const s = props.snapshot
  if (!s) return 'ok'
  return s.racks?.[id]?.status || s.switches?.[id]?.status
    || s.routers?.[id]?.status || s.gateways?.[id]?.status || s.coolers?.[id]?.status || 'ok'
}

/* --------------------------- 预测徽章文本/颜色 --------------------------- */
function predictionColor(status) { return STATUS_COLOR[status] || '#94a3b8' }
function predictionText(p) {
  // 前向预测文案：资产 + 预测前缀 + 峰值状态 + 首次劣化时点（T+n），
  // 与侧栏级联步骤的 T+ 约定一致；firstBadTick 为整段推演内首次达到该峰值的 tick。
  return `${p.label} 预测将${STATUS_LABELS[p.worstStatus] || p.worstStatus} · T+${p.firstBadTick ?? 0}`
}
/* --------------------------- 徽章防重叠布局 --------------------------- */
const BADGE_H = 26 // WebGL 徽章实测高度（5px 内边距 + 11px 字形 + 2px 边框，核心徽章边框更粗）
const BADGE_GAP_Y = 5
const BADGE_GAP_X = 8
// 无实测宽度时的估算：中文字形约 11px、其余约 6.4px（对应 11px 字号），加左右内边距与圆点。
function estimateBadgeWidth(text) {
  let w = 0
  for (const ch of text) w += /[\u4e00-\u9fa5]/.test(ch) ? 11 : 6.4
  return Math.ceil(w + 34)
}
// 静态 SVG 徽章字号为 7px，宽度估算需按同比例缩放，避免高估/低估导致压字。
function estimateStaticBadgeWidth(text) {
  let w = 0
  for (const ch of text) w += /[\u4e00-\u9fa5]/.test(ch) ? 7 : 4
  return Math.ceil(w + 12)
}
/** 水平钳制：徽章中心不出画布左右边缘，避免贴边裁切。 */
function clampBadgeX(x, w, width, pad = 6) {
  if (!width) return x
  return Math.min(Math.max(x, w / 2 + pad), width - w / 2 - pad)
}
/**
 * 徽章防重叠（二维贪心）：按锚点 y 从低到高逐个落位，与已放置徽章碰撞时上移一个身位；
 * 上方空间耗尽则退回锚点向下找空位，并整体钳制在画布内。
 * 相比「按 x 聚类整簇堆叠」，二维判定不会因相邻徽章链式聚类而把无关徽章抬高，
 * 位移更小、更贴近资产，也不会整簇被顶出画布。
 * @param {Array<{key, x, y, w}>} items 中心坐标与宽度
 * @param {number} h 徽章高度
 * @param {{height?: number, pad?: number}} [bounds] 画布高度与内边距
 * @returns {Map<string|number, number>} key -> 中心 y
 */
function packBadges(items, h, bounds = null) {
  const out = new Map()
  if (!items.length) return out
  const pad = bounds?.pad ?? 4
  const minY = h / 2 + pad
  const maxY = (bounds?.height ?? Infinity) - h / 2 - pad
  const step = h + BADGE_GAP_Y
  const placed = []
  const collides = (x, w, y) => placed.some(o => (
    Math.abs(o.x - x) < (o.w + w) / 2 + BADGE_GAP_X
    && Math.abs(o.y - y) < h + BADGE_GAP_Y
  ))
  // 量化排序键：像素级抖动不改变先后顺序，避免相机微动时徽章来回换位。
  const sorted = [...items].sort((a, b) => (
    Math.round(b.y / 4) - Math.round(a.y / 4)
    || b.y - a.y
    || String(a.key).localeCompare(String(b.key))
  ))
  const limit = sorted.length + 4
  for (const it of sorted) {
    let y = Math.min(it.y, maxY)
    let guard = 0
    while (collides(it.x, it.w, y) && guard < limit) { y -= step; guard += 1 }
    // 上方放不下：从锚点向下找最近空位，优先保证不压字。
    if (y < minY) {
      y = Math.min(it.y, maxY)
      guard = 0
      while ((y < minY || collides(it.x, it.w, y)) && y + step <= maxY && guard < limit) {
        y += step
        guard += 1
      }
    }
    y = Math.min(Math.max(y, minY), maxY)
    out.set(it.key, y)
    placed.push({ x: it.x, w: it.w, y })
  }
  return out
}
// 徽章在 3D 世界中的锚点高度（资产顶部上方一点），保证不被资产本体遮挡。
function badgeAnchorY(kind) {
  if (kind === 'rack') return 2.5
  if (kind === 'gateway') return 1.5
  if (kind === 'link') return 1.5
  if (kind === 'service') return 3.3 // 业务悬浮于宿主机架上方，高于机架徽章
  return 1.2 // switch / router / cooler
}
// 同一机架可能承载多个业务，沿 x 方向错开避免徽章重叠。
const serviceOffsetX = computed(() => {
  const byRack = new Map()
  for (const p of props.predictions) {
    if (p.kind !== 'service' || !p.rackId) continue
    if (!byRack.has(p.rackId)) byRack.set(p.rackId, [])
    byRack.get(p.rackId).push(p.id)
  }
  const map = new Map()
  for (const ids of byRack.values()) {
    ids.sort()
    const n = ids.length
    ids.forEach((id, i) => map.set(id, (i - (n - 1) / 2) * 1.3))
  }
  return map
})
// 预测徽章对应的 3D 世界坐标；链路取中点，业务取宿主机架并错开，其余取资产 x/z。
function badgeWorldPos(p) {
  if (p.kind === 'link') {
    const mid = linkMidpoint(p.id)
    if (!mid) return null
    return new Vector3(mid.x, badgeAnchorY('link'), mid.z)
  }
  if (p.kind === 'service') {
    const host = p.rackId ? devicePositions.value.get(p.rackId) : null
    if (!host) return null
    return new Vector3(host.x + (serviceOffsetX.value.get(p.id) || 0), badgeAnchorY('service'), host.z)
  }
  const d = devicePositions.value.get(p.id)
  if (!d) return null
  return new Vector3(d.x, badgeAnchorY(p.kind), d.z)
}
const staticNodes = computed(() => {
  const out = []
  for (const [id, d] of devicePositions.value) {
    const p = project(d.x, d.z)
    out.push({
      id, label: d.label, x: p.x, y: p.y,
      w: d.kind === 'rack' ? 26 : 40, h: d.kind === 'rack' ? 44 : 14, rx: 2,
      kind: d.kind, status: deviceStatus(id)
    })
  }
  return out
})
const staticLinks = computed(() => props.topology.links.map(link => {
  const a = devicePositions.value.get(link.from)
  const b = devicePositions.value.get(link.to)
  if (!a || !b) return null
  const pa = project(a.x, a.z)
  const pb = project(b.x, b.z)
  return { id: link.id, x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y, status: props.snapshot?.links?.[link.id]?.status || 'up' }
}).filter(Boolean))
function linkStroke(status) {
  return status === 'down' ? STATUS_COLOR.down : status === 'degraded' ? STATUS_COLOR.degraded : 'var(--ds-hairline)'
}
// 静态降级模式：防火墙误配时在网关位置叠加红色「ACL DENY」标记。
const staticFirewall = computed(() => {
  if (!props.snapshot || Object.keys(props.snapshot.firewallBlocked || {}).length === 0) return null
  const gw = props.topology.gateways[0]
  if (!gw) return null
  const d = devicePositions.value.get(gw.id)
  if (!d) return null
  return project(d.x, d.z)
})
// 静态模式下的预测徽章：正交投影，位置在资产/链路中点上方。
const staticPredictionBadges = computed(() => {
  const out = []
  for (const p of props.predictions) {
    let x = 0
    let y = 0
    let found = false
    if (p.kind === 'link') {
      const link = props.topology.links.find(l => l.id === p.id)
      if (link) {
        const a = devicePositions.value.get(link.from)
        const b = devicePositions.value.get(link.to)
        if (a && b) {
          const pa = project(a.x, a.z)
          const pb = project(b.x, b.z)
          x = (pa.x + pb.x) / 2
          y = (pa.y + pb.y) / 2 - 14
          found = true
        }
      }
    } else if (p.kind === 'service') {
      const host = p.rackId ? devicePositions.value.get(p.rackId) : null
      if (host) {
        const pr = project(host.x + (serviceOffsetX.value.get(p.id) || 0), host.z)
        x = pr.x
        y = pr.y - 44 // 高于机架徽章（-30），避免重叠
        found = true
      }
    } else {
      const d = devicePositions.value.get(p.id)
      if (d) {
        const pr = project(d.x, d.z)
        x = pr.x
        y = pr.y - (d.kind === 'rack' ? 30 : 14)
        found = true
      }
    }
    if (!found) continue
    const text = predictionText(p)
    const w = estimateStaticBadgeWidth(text)
    out.push({ id: p.id, x: clampBadgeX(x, w, STATIC_VIEW_W), y, text, color: predictionColor(p.worstStatus), w })
  }
  // 与 WebGL 徽章共用二维防重叠布局；静态图按 viewBox 尺寸约束，避免贴边裁切。
  const ys = packBadges(out.map(b => ({ key: b.id, x: b.x, y: b.y, w: b.w })), 17, { height: STATIC_VIEW_H, pad: 6 })
  return out.map(b => ({ ...b, y: ys.get(b.id) ?? b.y }))
})

/* -------------------------------- WebGL --------------------------------- */
let renderer = null
let scene = null
let camera = null
let rafStop = null
let resizeObs = null
const raycaster = new Raycaster()
const pointer = new Vector2()

const meshes = new Map() // assetId -> { group, body, label? }
const linkMeshes = new Map() // linkId -> LineSegments
let targetRing = null
let stormRing = null
// 网络实验专项可视化对象
let flapRing = null        // OSPF 邻居抖动：抖动路由器上的脉冲环
let flapBeam = null        // OSPF 邻居抖动：抖动路由器上方的不稳定光束
const fiberPulses = new Map() // 光功率衰减：沿抖动链路行进的光信号脉冲（linkId -> Mesh）
let firewallBarrier = null // 防火墙误配：网关处的红色阻断屏障
const firewallDrops = []   // 防火墙误配：出口侧被丢弃的数据包

// 从 domain 统一色板派生 WebGL 用的 hex 数值，保证网格着色与徽章/图例同色。
const palette = Object.fromEntries(Object.entries(STATUS_COLORS).map(([k, v]) => [k, parseInt(v.slice(1), 16)]))
const deviceKindColor = { switch: 0x22d3ee, router: 0x60a5fa, gateway: 0xe879f9, cooler: 0x7dd3fc }

function makeGrid() {
  const pts = []
  for (let i = -8; i <= 8; i += 1) { pts.push(i, 0.001, -6, i, 0.001, 6) }
  for (let j = -6; j <= 6; j += 1) { pts.push(-8, 0.001, j, 8, 0.001, j) }
  const g = new BufferGeometry()
  g.setAttribute('position', new BufferAttribute(new Float32Array(pts), 3))
  return new LineSegments(g, new LineBasicMaterial({ color: 0x1e293b, transparent: true, opacity: 0.5 }))
}

function posOf(id) {
  const d = devicePositions.value.get(id)
  return d ? new Vector3(d.x, 0, d.z) : null
}

function addRack(rack) {
  const group = new Group()
  group.position.set(rack.x, 0, rack.z) // group 定位到资产坐标，子网格用局部坐标，缩放才绕中心不位移
  const body = new Mesh(
    new BoxGeometry(1.05, 2.0, 0.95),
    new MeshStandardMaterial({ color: palette.ok, metalness: 0.35, roughness: 0.45 })
  )
  body.position.set(0, 1.0, 0)
  body.userData = { assetId: rack.id, kind: 'rack' }
  group.add(body)
  // 顶部 LED
  const led = new Mesh(
    new BoxGeometry(0.9, 0.08, 0.1),
    new MeshStandardMaterial({ color: 0x0f172a, emissive: palette.ok, emissiveIntensity: 1.2 })
  )
  led.position.set(0, 2.02, -0.48)
  group.add(led)
  group.userData = { assetId: rack.id, kind: 'rack', body, led }
  scene.add(group)
  meshes.set(rack.id, group)
}

function addFlatDevice(def, kind) {
  const group = new Group()
  group.position.set(def.x, 0, def.z)
  const h = kind === 'gateway' ? 0.9 : 0.55
  const body = new Mesh(
    new BoxGeometry(kind === 'gateway' ? 1.5 : 1.9, h, 0.9),
    new MeshStandardMaterial({ color: deviceKindColor[kind] || 0x94a3b8, metalness: 0.4, roughness: 0.35 })
  )
  body.position.set(0, h / 2, 0)
  body.userData = { assetId: def.id, kind }
  // 顶部色条（状态指示）
  const bar = new Mesh(
    new BoxGeometry(kind === 'gateway' ? 1.5 : 1.9, 0.08, 0.08),
    new MeshStandardMaterial({ color: 0x0f172a, emissive: palette.ok, emissiveIntensity: 1.4 })
  )
  bar.position.set(0, h + 0.06, 0)
  group.add(body, bar)
  group.userData = { assetId: def.id, kind, body, bar }
  scene.add(group)
  meshes.set(def.id, group)
}

function addLink(link) {
  const a = posOf(link.from)
  const b = posOf(link.to)
  if (!a || !b) return
  const ya = linkYOf(link.from)
  const yb = linkYOf(link.to)
  const g = new BufferGeometry().setFromPoints([new Vector3(a.x, ya, a.z), new Vector3(b.x, yb, b.z)])
  const line = new LineSegments(
    g, // 用两点会渲染一条线段；LineSegments 需要成对顶点，setFromPoints 生成的正是一对
    new LineBasicMaterial({ color: 0x475569, transparent: true, opacity: 0.7 })
  )
  line.userData = { linkId: link.id, from: link.from, to: link.to }
  scene.add(line)
  linkMeshes.set(link.id, line)
}
function linkYOf(id) {
  const d = devicePositions.value.get(id)
  if (!d) return 0.3
  if (d.kind === 'rack') return 2.0
  if (d.kind === 'gateway') return 0.9
  return 0.55
}
// 返回链路两端的世界坐标（含正确的 Y 高度），用于光信号行进动画与链路中点高亮。
function linkEndpoints(linkId) {
  const line = linkMeshes.get(linkId)
  if (!line) return null
  const a = posOf(line.userData.from)
  const b = posOf(line.userData.to)
  if (!a || !b) return null
  a.y = linkYOf(line.userData.from)
  b.y = linkYOf(line.userData.to)
  return { a, b }
}
function linkMidpoint(linkId) {
  const ep = linkEndpoints(linkId)
  if (!ep) return null
  return new Vector3((ep.a.x + ep.b.x) / 2, 0.05, (ep.a.z + ep.b.z) / 2)
}

function buildScene() {
  scene = new Scene()
  scene.background = null
  scene.fog = null

  scene.add(makeGrid())
  // 冷/热通道指示带
  const aisle = new Mesh(
    new BoxGeometry(14, 0.002, 0.9),
    new MeshStandardMaterial({ color: 0x0ea5e9, transparent: true, opacity: 0.08 })
  )
  scene.add(aisle)

  for (const rack of props.topology.racks) addRack(rack)
  for (const sw of props.topology.switches) addFlatDevice(sw, 'switch')
  for (const rtr of props.topology.routers) addFlatDevice(rtr, 'router')
  for (const gw of props.topology.gateways) addFlatDevice(gw, 'gateway')
  for (const cooler of props.topology.coolers) addFlatDevice(cooler, 'cooler')
  for (const link of props.topology.links) addLink(link)

  // 目标高亮环
  targetRing = new Mesh(
    new TorusGeometry(1.25, 0.06, 12, 48),
    new MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x38bdf8, emissiveIntensity: 1.4, transparent: true, opacity: 0.9 })
  )
  targetRing.rotation.x = Math.PI / 2
  targetRing.visible = false
  scene.add(targetRing)

  // 广播风暴扩散环
  stormRing = new Mesh(
    new TorusGeometry(1, 0.08, 12, 64),
    new MeshStandardMaterial({ color: 0xf87171, emissive: 0xef4444, emissiveIntensity: 1.6, transparent: true, opacity: 0 })
  )
  stormRing.rotation.x = Math.PI / 2
  scene.add(stormRing)

  // —— 网络实验专项可视化 ——
  // 1) OSPF 邻居抖动：抖动路由器上的脉冲环 + 上方不稳定光束
  flapRing = new Mesh(
    new TorusGeometry(0.95, 0.055, 10, 44),
    new MeshStandardMaterial({ color: 0xef4444, emissive: 0xef4444, emissiveIntensity: 1.2, transparent: true, opacity: 0 })
  )
  flapRing.rotation.x = Math.PI / 2
  flapRing.visible = false
  scene.add(flapRing)

  flapBeam = new Mesh(
    new CylinderGeometry(0.07, 0.07, 1.7, 12),
    new MeshStandardMaterial({ color: 0xef4444, emissive: 0xef4444, emissiveIntensity: 1.2, transparent: true, opacity: 0 })
  )
  flapBeam.visible = false
  scene.add(flapBeam)

  // 2) 光功率衰减：每条链路一个可沿链路行进的光信号脉冲（仅抖动链路可见）
  for (const link of props.topology.links) {
    const dot = new Mesh(
      new SphereGeometry(0.11, 14, 14),
      new MeshStandardMaterial({ color: 0xfde047, emissive: 0xfde047, emissiveIntensity: 1.6, transparent: true, opacity: 0 })
    )
    dot.visible = false
    scene.add(dot)
    fiberPulses.set(link.id, dot)
  }

  // 3) 防火墙误配：网关处的红色阻断屏障 + 出口侧被丢弃的数据包
  firewallBarrier = new Mesh(
    new TorusGeometry(1.0, 0.08, 12, 48),
    new MeshStandardMaterial({ color: 0xf87171, emissive: 0xef4444, emissiveIntensity: 1.4, transparent: true, opacity: 0 })
  )
  firewallBarrier.visible = false
  scene.add(firewallBarrier)
  for (let i = 0; i < 3; i += 1) {
    const drop = new Mesh(
      new SphereGeometry(0.1, 10, 10),
      new MeshStandardMaterial({ color: 0xf87171, emissive: 0xef4444, emissiveIntensity: 1.4, transparent: true, opacity: 0 })
    )
    drop.visible = false
    scene.add(drop)
    firewallDrops.push(drop)
  }

  scene.add(new AmbientLight(0xffffff, 0.55))
  const dir = new DirectionalLight(0xffffff, 0.85)
  dir.position.set(6, 10, 4)
  scene.add(dir)
}

let azimuth = 0.62
let polar = 1.02
let radius = 15
let dragging = false
let lastX = 0
let lastY = 0

function updateCamera() {
  const target = new Vector3(0, 0.8, 0)
  const x = target.x + radius * Math.sin(polar) * Math.cos(azimuth)
  const z = target.z + radius * Math.sin(polar) * Math.sin(azimuth)
  const y = target.y + radius * Math.cos(polar)
  camera.position.set(x, y, z)
  camera.lookAt(target)
}

function onPointerDown(e) {
  dragging = true
  lastX = e.clientX
  lastY = e.clientY
}
function onPointerMove(e) {
  if (!dragging) return
  azimuth -= (e.clientX - lastX) * 0.006
  polar = Math.max(0.35, Math.min(1.5, polar - (e.clientY - lastY) * 0.006))
  lastX = e.clientX
  lastY = e.clientY
  updateCamera()
}
function onPointerUp() { dragging = false }
function onWheel(e) {
  e.preventDefault()
  radius = Math.max(9, Math.min(26, radius + e.deltaY * 0.01))
  updateCamera()
}
function onClick(e) {
  const rect = host.value.getBoundingClientRect()
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, camera)
  const hits = raycaster.intersectObjects(scene.children, true)
  for (const hit of hits) {
    const id = hit.object.userData?.assetId || hit.object.parent?.userData?.assetId
    if (id) { emit('select', id); break }
  }
}

function applySnapshot(s, t) {
  if (!s) {
    for (const group of meshes.values()) {
      const body = group.userData.body
      if (body) body.material.color.setHex(palette.ok)
      const led = group.userData.led || group.userData.bar
      if (led) led.material.emissive.setHex(palette.ok)
    }
    for (const line of linkMeshes.values()) line.material.color.setHex(0x475569)
    targetRing.visible = false
    stormRing.material.opacity = 0
    if (flapRing) flapRing.visible = false
    if (flapBeam) flapBeam.visible = false
    for (const dot of fiberPulses.values()) dot.visible = false
    if (firewallBarrier) firewallBarrier.visible = false
    for (const drop of firewallDrops) drop.visible = false
    return
  }
  const reduce = isReducedMotionMode.value
  const pulse = reduce ? 0 : (0.5 + 0.5 * Math.sin(t * 0.006))
  // 抖动故障：奇数 tick 为「坏」tick（劣化态），偶数 tick 短暂恢复。
  const badTick = (s.tick % 2) === 1
  for (const [id, group] of meshes) {
    const status = s.racks?.[id]?.status || s.switches?.[id]?.status
      || s.routers?.[id]?.status || s.gateways?.[id]?.status || s.coolers?.[id]?.status || 'ok'
    const base = palette[status] || 0x94a3b8
    const body = group.userData.body
    if (body) {
      body.material.color.setHex(base)
      body.material.emissive = body.material.emissive || new Color(0x000000)
      body.material.emissive.setHex(base)
      body.material.emissiveIntensity = status === 'ok' ? 0.08 : (0.35 + pulse * 0.45)
    }
    const led = group.userData.led || group.userData.bar
    if (led) {
      led.material.emissive.setHex(base)
      led.material.emissiveIntensity = status === 'ok' ? 0.7 : (1.1 + pulse * 0.8)
    }
    // 被选中的资产轻微放大提示
    const selected = props.selectedAssetId === id
    group.scale.setScalar(selected ? 1.06 : 1)
  }
  for (const [id, line] of linkMeshes) {
    const ls = s.links?.[id]?.status || 'up'
    const down = ls === 'down'
    const flapping = ls === 'degraded'
    line.material.color.setHex(down ? 0xf87171 : flapping ? 0xfbbf24 : s.broadcastStorm ? 0xfb923c : 0x475569)
    line.material.opacity = down ? (0.5 + pulse * 0.5) : flapping ? (0.55 + pulse * 0.4) : s.broadcastStorm ? (0.5 + pulse * 0.4) : 0.7
  }
  // 目标高亮（支持链路目标：定位到链路中点）
  if (props.targetId) {
    let p = posOf(props.targetId)
    if (!p) p = linkMidpoint(props.targetId)
    if (p) {
      targetRing.visible = true
      targetRing.position.set(p.x, 0.05, p.z)
      const s2 = 1 + (reduce ? 0 : pulse * 0.18)
      targetRing.scale.setScalar(s2)
      targetRing.material.opacity = reduce ? 0.8 : (0.55 + pulse * 0.4)
    } else targetRing.visible = false
  } else targetRing.visible = false
  // 广播风暴扩散
  if (s.broadcastStorm) {
    const phase = (t * 0.0012) % 1
    stormRing.scale.setScalar(1 + phase * 9)
    stormRing.material.opacity = reduce ? 0.4 : (0.7 * (1 - phase))
  } else {
    stormRing.material.opacity = 0
  }

  /* —— 网络实验专项可视化 —— */
  // 1) OSPF 邻居抖动：抖动路由器脉冲环 + 不稳定光束；坏 tick 增强（邻居 Down），好 tick 减弱（短暂恢复）
  const flappingRouterIds = Object.keys(s.flappingRouters || {})
  if (flapRing && flapBeam) {
    if (flappingRouterIds.length > 0) {
      const p = posOf(flappingRouterIds[0])
      if (p) {
        const intensity = badTick ? 1 : 0.3
        flapRing.visible = true
        flapRing.position.set(p.x, 0.06, p.z)
        flapRing.material.opacity = reduce ? 0.7 : (0.4 + intensity * 0.5)
        flapRing.material.emissiveIntensity = 0.6 + intensity * 1.3
        flapRing.scale.setScalar(1 + (reduce ? 0 : pulse * 0.18 * intensity))
        flapBeam.visible = true
        flapBeam.position.set(p.x, 1.0, p.z)
        flapBeam.material.opacity = reduce ? 0.5 : (0.25 + intensity * 0.55)
        flapBeam.material.emissiveIntensity = 0.5 + intensity * 1.5
      } else {
        flapRing.visible = false
        flapBeam.visible = false
      }
    } else {
      flapRing.visible = false
      flapBeam.visible = false
    }
  }

  // 2) 光功率衰减：光信号沿抖动链路行进；坏 tick 衰减、闪烁变红（高误码），好 tick 稳定琥珀色
  for (const [lid, dot] of fiberPulses) {
    const flapping = !!s.flappingLinks?.[lid]
    if (!flapping) { dot.visible = false; continue }
    const ep = linkEndpoints(lid)
    if (!ep) { dot.visible = false; continue }
    dot.visible = true
    const phase = reduce ? 0.5 : ((t * 0.0009) % 1)
    dot.position.set(
      ep.a.x + (ep.b.x - ep.a.x) * phase,
      ep.a.y + (ep.b.y - ep.a.y) * phase,
      ep.a.z + (ep.b.z - ep.a.z) * phase
    )
    if (badTick) {
      const flick = reduce ? 0.6 : (0.45 + 0.55 * Math.abs(Math.sin(t * 0.025)))
      dot.material.color.setHex(0xf87171)
      dot.material.emissive.setHex(0xf87171)
      dot.material.opacity = 0.3 + 0.6 * flick
      dot.material.emissiveIntensity = 0.4 + 1.2 * flick
      dot.scale.setScalar(0.75 + 0.35 * flick)
    } else {
      dot.material.color.setHex(0xfbbf24)
      dot.material.emissive.setHex(0xfde047)
      dot.material.opacity = 0.95
      dot.material.emissiveIntensity = 1.6
      dot.scale.setScalar(1)
    }
  }

  // 3) 防火墙误配：网关处红色阻断屏障旋转脉冲 + 出口侧被丢弃的数据包（z 更小一侧为外部）
  const fwActive = Object.keys(s.firewallBlocked || {}).length > 0
  if (firewallBarrier) {
    if (fwActive) {
      const gw = props.topology.gateways[0]
      const p = gw ? posOf(gw.id) : null
      if (p) {
        firewallBarrier.visible = true
        firewallBarrier.position.set(p.x, 0.75, p.z)
        firewallBarrier.rotation.z = reduce ? 0 : ((t * 0.0008) % (Math.PI * 2))
        firewallBarrier.material.opacity = reduce ? 0.8 : (0.55 + pulse * 0.4)
        firewallBarrier.material.emissiveIntensity = 0.8 + pulse * 1.4
        firewallDrops.forEach((drop, i) => {
          drop.visible = true
          const bob = reduce ? 0 : Math.sin(t * 0.004 + i) * 0.12
          drop.position.set(p.x + (i - 1) * 0.5, 0.6 + bob, p.z - 0.95)
          drop.material.opacity = reduce ? 0.8 : (0.5 + pulse * 0.4)
          drop.material.emissiveIntensity = 0.8 + pulse * 1.2
          drop.scale.setScalar(0.9 + pulse * 0.2)
        })
      } else {
        firewallBarrier.visible = false
        for (const drop of firewallDrops) drop.visible = false
      }
    } else {
      firewallBarrier.visible = false
      for (const drop of firewallDrops) drop.visible = false
    }
  }
}

/**
 * 把前向预测徽章从 3D 世界坐标投影到画布像素坐标，实时跟随相机旋转/缩放。
 * 经验：不要用 NDC z 线性映射透明度（z 接近 1 不代表不可见）；
 * 正确做法是判断「在相机前方 (z<1) 且落在视口内」，否则隐藏，透明度用固定值。
 */
function updatePredictionBadges() {
  if (!camera || !badgeLayer.value || !host.value) return
  const rect = host.value.getBoundingClientRect()
  const preds = props.predictions
  const visible = []
  for (let i = 0; i < preds.length; i += 1) {
    const el = badgeEls[i]
    if (!el) continue
    const p = preds[i]
    const wp = badgeWorldPos(p)
    if (!wp) { el.style.display = 'none'; continue }
    const v = wp.project(camera)
    if (v.z >= 1 || v.x < -1 || v.x > 1 || v.y < -1 || v.y > 1) {
      el.style.display = 'none'
      continue
    }
    el.style.display = ''
    // 徽章以底边为锚点（transform: translateY(-100%)），布局时换算成中心 y。
    const px = (v.x * 0.5 + 0.5) * rect.width
    const py = (-v.y * 0.5 + 0.5) * rect.height
    // 文本固定，宽度测量一次后缓存；首次渲染前用估算值兜底。
    let w = badgeWidths.get(p.id)
    if (!w) {
      w = el.offsetWidth || estimateBadgeWidth(predictionText(p))
      if (w) badgeWidths.set(p.id, w)
    }
    visible.push({ key: p.id, el, x: clampBadgeX(px, w, rect.width), y: py - BADGE_H / 2, w })
  }
  // 防重叠：二维贪心布局，画布四边同时钳制，避免徽章压字或贴边裁切。
  const ys = packBadges(visible.map(it => ({ key: it.key, x: it.x, y: it.y, w: it.w })), BADGE_H, { height: rect.height, pad: 6 })
  for (const it of visible) {
    // 用 transform 定位：每帧只触发合成层更新，不产生 left/top 的布局回流。
    it.el.style.transform = `translate3d(${it.x}px, ${(ys.get(it.key) ?? it.y) + BADGE_H / 2}px, 0) translate(-50%, -100%)`
  }
  // predictions 缩短时，隐藏可能残留的旧元素（Vue 会卸载多余 DOM，此处兜底）。
  for (let i = preds.length; i < badgeEls.length; i += 1) {
    if (badgeEls[i]) badgeEls[i].style.display = 'none'
  }
}

function renderFrame(dt, now) {
  if (!renderer || !scene) return
  applySnapshot(props.snapshot, now)
  renderer.render(scene, camera)
  // 相机矩阵在 render 后已更新，徽章投影以最新相机为准。
  updatePredictionBadges()
}

function resize() {
  if (!renderer || !host.value) return
  const w = host.value.clientWidth
  const h = host.value.clientHeight
  if (w === 0 || h === 0) return
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setSize(w, h, false)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
}

function initWebGL() {
  if (!host.value) return
  try {
    renderer = new WebGLRenderer({ antialias: true, alpha: true })
  } catch {
    renderer = null
    webglFailed.value = true
    return
  }
  renderer.setClearColor(0x000000, 0)
  host.value.appendChild(renderer.domElement)
  renderer.domElement.style.display = 'block'
  renderer.domElement.style.width = '100%'
  renderer.domElement.style.height = '100%'

  camera = new PerspectiveCamera(50, 1, 0.1, 100)
  buildScene()
  updateCamera()
  resize()

  host.value.addEventListener('pointerdown', onPointerDown)
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  host.value.addEventListener('wheel', onWheel, { passive: false })
  host.value.addEventListener('click', onClick)

  resizeObs = new ResizeObserver(resize)
  resizeObs.observe(host.value)

  rafStop = subscribe(renderFrame, { fps: 30, id: 'virtual-ops-scene-3d' })
}

onMounted(() => {
  if (staticMode.value) return
  initWebGL()
})
watch(staticMode, (on) => {
  if (on) disposeWebGL()
  else initWebGL()
})

function disposeWebGL() {
  if (rafStop) { rafStop(); rafStop = null }
  if (resizeObs) { resizeObs.disconnect(); resizeObs = null }
  if (host.value) {
    host.value.removeEventListener('pointerdown', onPointerDown)
    host.value.removeEventListener('wheel', onWheel)
    host.value.removeEventListener('click', onClick)
  }
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  meshes.clear()
  linkMeshes.clear()
  fiberPulses.clear()
  firewallDrops.length = 0
  badgeEls.length = 0
  badgeWidths.clear()
  flapRing = null
  flapBeam = null
  firewallBarrier = null
  if (renderer) {
    renderer.dispose()
    if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement)
    renderer = null
  }
  scene = null
  camera = null
}
onBeforeUnmount(disposeWebGL)
</script>

<style scoped>
.vos3d-wrap { position: relative; width: 100%; height: 100%; min-height: 420px; border-radius: 14px; overflow: hidden; background:
  radial-gradient(120% 90% at 50% 0%, rgba(14,165,233,0.08), transparent 60%),
  linear-gradient(180deg, rgba(15,23,42,0.65), rgba(2,6,23,0.85));
  border: 1px solid var(--ds-hairline, rgba(148,163,184,0.18));
}
.vos3d-stage { position: absolute; inset: 0; outline: none; }
.vos3d-stage:focus-visible { box-shadow: inset 0 0 0 2px var(--ds-color-accent, #38bdf8); }
.vos3d-static { position: absolute; inset: 0; width: 100%; height: 100%; }
.vos3d-legend { position: absolute; left: 12px; bottom: 10px; display: flex; gap: 12px; flex-wrap: wrap;
  font-size: 11px; color: var(--ds-color-muted, #94a3b8); background: rgba(2,6,23,0.55); padding: 6px 10px; border-radius: 999px; backdrop-filter: blur(6px); }
.vos3d-legend .vos3d-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: var(--c); margin-right: 5px; vertical-align: middle; box-shadow: 0 0 6px var(--c); }
.vos3d-hint { position: absolute; right: 12px; bottom: 10px; font-size: 11px; color: var(--ds-color-muted, #94a3b8);
  background: rgba(2,6,23,0.55); padding: 5px 10px; border-radius: 999px; backdrop-filter: blur(6px); }
.vos3d-badges { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
.vos3d-badge { position: absolute; left: 0; top: 0; transform: translate(-50%, -100%); will-change: transform; white-space: nowrap;
  font-family: inherit; font-size: 11px; font-weight: 600; line-height: 1; padding: 5px 10px; margin: 0; border-radius: 999px;
  pointer-events: auto; cursor: pointer;
  background: rgba(2,6,23,0.82); border: 1.5px solid var(--bc); color: var(--bc);
  box-shadow: 0 0 0 1px rgba(0,0,0,0.5), 0 0 12px var(--bc); backdrop-filter: blur(6px);
  transition: background .15s ease, box-shadow .15s ease; }
.vos3d-badge:hover, .vos3d-badge:focus-visible { outline: none; background: rgba(2,6,23,0.95);
  box-shadow: 0 0 0 1px rgba(0,0,0,0.6), 0 0 18px var(--bc), 0 0 0 2px rgba(255,255,255,0.16); }
/* 核心业务：中断后果最需被一眼看到，加粗边框 + 呼吸光晕强调。 */
.vos3d-badge.is-core { font-weight: 700; border-width: 2px; animation: vos3d-badge-core 1.8s ease-in-out infinite; }
@keyframes vos3d-badge-core {
  0%, 100% { box-shadow: 0 0 0 1px rgba(0,0,0,0.5), 0 0 10px var(--bc); }
  50% { box-shadow: 0 0 0 1px rgba(0,0,0,0.5), 0 0 20px var(--bc), 0 0 0 3px rgba(255,255,255,0.12); }
}
@media (prefers-reduced-motion: reduce) { .vos3d-badge.is-core { animation: none; } }
.vos3d-badge__dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--bc);
  margin-right: 6px; vertical-align: middle; box-shadow: 0 0 7px var(--bc); }
@media (max-width: 720px) { .vos3d-legend { font-size: 10px; gap: 8px; } }
</style>
