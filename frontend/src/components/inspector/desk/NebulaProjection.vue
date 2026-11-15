<template>
  <section
    class="nebula-card"
    role="img"
    :aria-label="ariaLabel"
    tabindex="0"
    @keydown="onKeydown"
  >
    <div class="nebula-title">
      <h2>共享时间轴 · <span class="view-name">星云</span></h2>
      <span class="nebula-count">{{ windowKey }} · {{ countLabel }}</span>
    </div>
    <div class="nebula-canvas-wrap" ref="wrapRef">
      <canvas
        ref="canvasRef"
        @pointermove="onPointerMove"
        @pointerleave="onPointerLeave"
        @click="onClick"
      ></canvas>
      <div v-if="emptyState" class="nebula-empty">{{ emptyState }}</div>
      <div v-else-if="errorState" class="nebula-error"><span>{{ errorState }}</span><button @click="$emit('retry')">重试</button></div>
      <div v-else-if="loadingState" class="nebula-empty">加载中…</div>
      <div v-show="tip.visible" class="tip" :style="tip.style" v-html="tip.html"></div>
    </div>
    <div class="nebula-foot">
      <span v-for="s in severities" :key="s.key"><i :style="{ background: s.color }"></i>{{ s.cn }}</span>
      <span><i class="swatch" style="background: conic-gradient(#2496ed,#7ad7f5,#3fb950,#f0883e,#d29922,#58a6ff,#a383a6,#f85149)"></i>hover 按维度重着色</span>
      <span v-if="sampledInfo">已抽样 {{ sampledInfo.shown }} / 总数 {{ sampledInfo.total }}（超出 {{ cap }} 上限，均匀抽样）</span>
      <span v-if="downsampled">掉帧降采样至 {{ cap }} 粒</span>
    </div>
    <!-- 屏幕阅读器列表：星云可见事件 -->
    <ul class="sr-only">
      <li v-for="e in events" :key="e.id">{{ fmtDateTime(e.at) }} · {{ severityMeta(e.severity).cn }} · {{ e.taskId }} · {{ e.traceId ? '已关联' : '未关联' }}</li>
    </ul>
  </section>
</template>

<script setup>
/**
 * NebulaProjection.vue — 洞察台第 4 投影「星云」（T32b/c）
 *
 * Canvas 2D + 手写旋转矩阵透视投影（不引 three.js）：
 *   - 纬度 = 等级四环带（PASS 赤道 → CRITICAL 北极圈）
 *   - 经度 = 当前时间窗比例 × 360°，亮度随新旧衰减
 *   - 自转 ≈ 40s/圈 + 呼吸微光；hover 按维度八色带重着色（色环扫描）
 * 四重降级：reduced-motion 静态单帧 / 掉帧降采样 1000→500→250 /
 *           超 1000 粒抽样脚注 / 窄屏由视图层隐藏 tab。
 * 交互零新契约：点击开既有 DeskDrawer，选中态写回 DeskSelection。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { SEVERITIES, fmtDateTime, runsByTraceMap, severityMeta } from './deskModel.js'
import {
  NEBULA_CAP, NEBULA_DOWNSAMPLE, buildNebula, project, flatPosition,
  easeOutCubic, dimensionColorOf, severityColorOf
} from './nebulaProjection.js'

const props = defineProps({
  events: { type: Array, default: () => [] },
  runs: { type: Array, default: () => [] },
  range: { type: Object, required: true },
  selected: { type: Object, default: null },
  eventsStatus: { type: String, default: 'ready' },
  eventsError: { type: String, default: '' },
  demo: { type: Boolean, default: false },
  windowKey: { type: String, default: '24h' }
})
const emit = defineEmits(['select'])

const canvasRef = ref(null)
const wrapRef = ref(null)
const tip = ref({ visible: false, html: '', style: {} })
const cap = ref(NEBULA_CAP)
const downsampled = ref(false)
const sampledInfo = ref(null)

const severities = SEVERITIES
const reduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const countLabel = computed(() => `${nebula.value.particles.length} 颗事件`)
const emptyState = computed(() => (props.eventsStatus === 'ready' && !props.events.length ? '窗口内没有纠察事件' : ''))
const errorState = computed(() => (props.eventsStatus === 'error' ? props.eventsError : ''))
const loadingState = computed(() => props.eventsStatus === 'loading')

const nebula = computed(() => buildNebula(props.events, props.range, cap.value))
const runsByTrace = computed(() => runsByTraceMap(props.runs))

const severityCount = computed(() => {
  const count = { CRITICAL: 0, HIGH: 0, WARN: 0, PASS: 0 }
  for (const p of nebula.value.particles) count[p.severity] = (count[p.severity] || 0) + 1
  return count
})
const ariaLabel = computed(() => {
  const c = severityCount.value
  const total = nebula.value.particles.length
  return `星云投影，${total} 颗事件：严重 ${c.CRITICAL}、高 ${c.HIGH}、警告 ${c.WARN}、通过 ${c.PASS}。方向键移动选中，回车打开证据抽屉`
})

/* ---------- 渲染循环 ---------- */
let ctx = null
let rafId = null
let lastTime = 0
let rotY = 0.6
const TILT_X = 0.35
const ROT_PERIOD_MS = 40000
let transStart = 0
let fpsEma = 60
let lastProjected = []
let hoverId = null

function draw(now) {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  const rect = wrapRef.value.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const dpr = window.devicePixelRatio || 1
  if (canvas.width !== Math.round(rect.width * dpr) || canvas.height !== Math.round(rect.height * dpr)) {
    canvas.width = Math.round(rect.width * dpr)
    canvas.height = Math.round(rect.height * dpr)
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, rect.width, rect.height)

  const dt = lastTime ? now - lastTime : 16.7
  lastTime = now
  if (!reduced) {
    // 掉帧监测：滚动 EMA，低于 22fps 逐档降采样
    fpsEma = fpsEma * 0.95 + (1000 / Math.max(1, dt)) * 0.05
    if (fpsEma < 22 && !downsampled.value) stepDownCap()
    rotY += (dt / ROT_PERIOD_MS) * Math.PI * 2
  }

  drawBands(rect)

  const particles = nebula.value.particles
  const radius = Math.min(rect.width, rect.height) * 0.36
  const projected = project(particles, rotY, TILT_X, rect.width, rect.height, radius)
  lastProjected = projected

  // 呼吸微光
  const breath = reduced ? 1 : 0.78 + 0.14 * Math.sin(now / 700)
  // 转场：600ms 从平面位置汇聚成球（reduced 静态单帧直接成球；掉帧降采样到底档后关闭）
  const transMs = (reduced || downsampled.value) ? 0 : 600
  const transProgress = transMs ? Math.min(1, (now - transStart) / transMs) : 1
  const eased = easeOutCubic(transProgress)

  const hovering = hoverId != null
  for (const item of projected) {
    const p = item.p
    let x = item.x
    let y = item.y
    if (eased < 1) {
      const flat = flatPosition(p, rect.width, rect.height)
      x = flat.x + (item.x - flat.x) * eased
      y = flat.y + (item.y - flat.y) * eased
    }
    const isSelected = props.selected?.__type === 'event' && props.selected.id === p.id
    const isHover = hoverId === p.id
    const ageAlpha = 0.35 + (1 - p.age) * 0.65
    let alpha = Math.min(1, ageAlpha * breath)
    if (hovering && !isHover) alpha *= 0.15

    let color = severityColorOf(p.severity)
    if (hovering) color = dimensionColorOf(p.dimKey, color) // 色环扫描
    const r = p.size * item.scale * (isHover ? 2.1 : 1) * (isSelected ? 1.4 : 1)

    ctx.globalAlpha = alpha
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.arc(x, y, r, 0, Math.PI * 2)
    ctx.fill()

    if (isSelected || isHover) {
      ctx.globalAlpha = Math.min(1, alpha + 0.35)
      ctx.strokeStyle = color
      ctx.lineWidth = isSelected ? 2 : 1.2
      ctx.beginPath()
      ctx.arc(x, y, r + 5, 0, Math.PI * 2)
      ctx.stroke()
      ctx.lineWidth = 1
    }
  }
  ctx.globalAlpha = 1

  if (props.demo) {
    ctx.font = '700 22px Consolas, monospace'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = 'rgba(210,153,34,.28)'
    ctx.fillText('DEMO', rect.width / 2, rect.height / 2)
    ctx.textAlign = 'left'
  }

  if (!reduced) {
    // 自转 + 呼吸需要持续帧循环；reduced 下由交互按需单帧重绘
    rafId = requestAnimationFrame(draw)
  }
}

/** 背景 hairline 纬度环带 + 等级刻度（无渐变科幻底） */
function drawBands(rect) {
  const cx = rect.width / 2
  const cy = rect.height / 2
  const R = Math.min(rect.width, rect.height) * 0.36
  ctx.font = '10px Consolas, monospace'
  ctx.textBaseline = 'middle'
  ctx.setLineDash([2, 5])
  for (const s of SEVERITIES) {
    const phi = { PASS: 0.1, WARN: 0.48, HIGH: 0.86, CRITICAL: 1.24 }[s.key]
    const rx = R * Math.cos(phi)
    const ry = rx * Math.sin(TILT_X)
    ctx.strokeStyle = 'rgba(255,255,255,.06)'
    ctx.beginPath()
    ctx.ellipse(cx, cy - R * Math.sin(phi) * Math.cos(TILT_X), rx, Math.max(1.5, ry), 0, 0, Math.PI * 2)
    ctx.stroke()
    ctx.fillStyle = '#5d6b78'
    ctx.fillText(s.cn, 8, cy - R * Math.sin(phi) * Math.cos(TILT_X))
  }
  ctx.setLineDash([])
}

function stepDownCap() {
  const index = NEBULA_DOWNSAMPLE.indexOf(cap.value)
  const next = NEBULA_DOWNSAMPLE[Math.min(NEBULA_DOWNSAMPLE.length - 1, index + 1)]
  if (next === cap.value) { downsampled.value = true; return }
  cap.value = next
  downsampled.value = next === NEBULA_DOWNSAMPLE[NEBULA_DOWNSAMPLE.length - 1]
}

/* ---------- 命中检测与交互 ---------- */
function hitTest(px, py) {
  // lastProjected 为远→近排序，从近往回找
  for (let i = lastProjected.length - 1; i >= 0; i -= 1) {
    const item = lastProjected[i]
    if (Math.hypot(px - item.x, py - item.y) < 12) return item
  }
  return null
}

function onPointerMove(e) {
  const rect = canvasRef.value.getBoundingClientRect()
  const hit = hitTest(e.clientX - rect.left, e.clientY - rect.top)
  hoverId = hit ? hit.p.id : null
  if (!hit) { tip.value = { visible: false, html: '', style: {} }; requestFrame(); return }
  const p = hit.p
  const source = props.events.find(ev => ev.id === p.id)
  const linked = source?.traceId ? runsByTrace.value.has(source.traceId) : false
  const html = `<b>${p.id}</b>` +
    `<span><i>时间</i><i>${fmtDateTime(p.at)}</i></span>` +
    `<span><i>等级</i><i>${severityMeta(p.severity).cn}</i></span>` +
    `<span><i>任务</i><i>${p.taskId}</i></span>` +
    `<span><i>维度</i><i>${p.dimKey || '—'}</i></span>` +
    `<span><i>关联</i><i>${linked ? '已关联 trace' : '未关联'}</i></span>`
  tip.value = {
    visible: true,
    html,
    style: { left: `${Math.min(rect.width - 110, Math.max(110, hit.x))}px`, top: `${Math.max(84, hit.y - 10)}px` }
  }
  requestFrame()
}

function onPointerLeave() {
  hoverId = null
  tip.value = { visible: false, html: '', style: {} }
  requestFrame()
}

function onClick(e) {
  const rect = canvasRef.value.getBoundingClientRect()
  const hit = hitTest(e.clientX - rect.left, e.clientY - rect.top)
  if (!hit) return
  const event = props.events.find(ev => ev.id === hit.p.id)
  if (event) emit('select', { __type: 'event', ...event })
}

function onKeydown(e) {
  // 方向键交给视图层全局遍历（moveSelection），这里仅阻止页面滚动
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') e.preventDefault()
}

/* ---------- 生命周期 ---------- */
function requestFrame() {
  if (rafId) return
  rafId = requestAnimationFrame(now => {
    rafId = null
    draw(now)
  })
}

let ro = null
function start() {
  ctx = canvasRef.value.getContext('2d')
  transStart = performance.now()
  updateSampledInfo()
  draw(performance.now()) // 非 reduced 时 draw 末尾自调度持续帧循环
  ro = new ResizeObserver(() => { lastTime = 0; requestFrame() }) // 非 reduced 时主循环下一帧自动拾取新尺寸
  ro.observe(wrapRef.value)
}
function stop() {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = null
  if (ro) ro.disconnect()
}

function updateSampledInfo() {
  const info = nebula.value
  sampledInfo.value = info.sampled ? { shown: info.particles.length, total: info.total } : null
}

watch([() => props.events, () => props.range, () => props.runs], () => {
  updateSampledInfo()
  hoverId = null
  tip.value = { visible: false, html: '', style: {} }
  requestFrame()
})
watch(() => props.selected, requestFrame)
watch(() => props.demo, requestFrame)

onMounted(start)
onBeforeUnmount(stop)
</script>

<style scoped>
.nebula-card { background: var(--ds-surface-raised); border: 1px solid var(--ds-surface-overlay); border-radius: 12px; padding: 16px; min-height: 480px; display: flex; flex-direction: column; }
.nebula-title { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; }
.nebula-title h2 { margin: 0; font-size: 16px; }
.view-name { color: var(--smart-primary); }
.nebula-count { color: var(--smart-muted); font-size: 12px; }
.nebula-canvas-wrap { width: 100%; height: 420px; position: relative; flex: 1; }
.nebula-canvas-wrap canvas { width: 100%; height: 100%; display: block; cursor: crosshair; }
.nebula-empty, .nebula-error { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--smart-muted); font-size: 13px; }
.nebula-error button { background: var(--ds-surface-overlay); border: 0; color: var(--smart-text); padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.tip { position: absolute; z-index: 5; min-width: 186px; padding: 8px 10px; border: 1px solid color-mix(in srgb, var(--smart-surface) 14%, transparent); border-radius: 5px; background: var(--smart-surface-raised); color: var(--smart-text); font: 10.5px/1.65 Consolas, monospace; pointer-events: none; transform: translate(-50%, -110%); }
.tip b { display: block; margin-bottom: 4px; color: var(--smart-primary-strong); }
.tip span { display: flex; justify-content: space-between; gap: 14px; color: var(--smart-muted); }
.tip span i { font-style: normal; color: var(--smart-text); }
.nebula-foot { display: flex; flex-wrap: wrap; gap: 12px 18px; padding-top: 10px; border-top: 1px solid var(--ds-surface-overlay); color: var(--smart-muted); font: 10px Consolas, monospace; letter-spacing: .06em; margin-top: 10px; }
.nebula-foot i { display: inline-block; width: 10px; height: 10px; margin-right: 5px; border-radius: 2px; vertical-align: -1px; }
.swatch { border-radius: 5px !important; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
</style>
