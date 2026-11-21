<template>
  <div ref="wrapRef" class="forecast-chart-host">
    <canvas ref="canvasRef" class="forecast-chart-canvas" :aria-label="ariaLabel" role="img"></canvas>
    <!-- 浮层 DOM（tooltip） -->
    <div
      v-if="tooltipVisible"
      class="forecast-chart-tooltip"
      :style="tooltipStyle"
    >
      <b>{{ tooltip.value }} {{ sensor.unit }}</b>
      <span><i>时间</i><i>{{ tooltip.deltaLabel }}</i></span>
      <span><i>{{ tooltip.delta > 0 ? 'p10–p90' : '来源' }}</i><i>{{ tooltip.band }}</i></span>
    </div>
  </div>
</template>

<script setup>
/**
 * 预测面主图。
 *
 * 两种数据形态，由 `live` 区分：
 *   - demo（合成）：曲线由 syntheticSeries 的 valueAt/forecastAt 生成，逐点连续；
 *   - live （真实）：曲线由后端返回的 series / forecast 离散点连线，采样间隔 30~60s。
 *
 * 两者的坐标语义保持一致：t 为相对「现在」的秒偏移（历史为负、预测为正），
 * 因此工具栏的视野切换、阈值线、越界标记对两态通用。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { forecastAt, valueAt, bandAt } from '../../domain/forecast/syntheticSeries.js'

const props = defineProps({
  sensor: { type: Object, required: true },
  horizon: { type: Number, default: 30 },
  shadowEnabled: { type: Boolean, default: false },
  now: { type: Number, default: 0 },       // 绝对回放时间（仅 demo 用）
  generatedAt: { type: Number, default: 0 }, // 基准时刻（秒）
  history: { type: Array, default: () => [] },
  forecast: { type: Array, default: () => [] },
  crossings: { type: Array, default: () => [] },
  // live 态：后端已给出按 horizon 换算好的秒偏移序列。
  live: { type: Boolean, default: false }
})

defineEmits(['cursor-change', 'crossing-click'])

const wrapRef = ref(null)
const canvasRef = ref(null)
let ro = null
let lastDpr = 1
let hover = null   // { x, y }（画布坐标）
let pinned = null  // { x, y }
const HISTORY = 120
const MARGIN = { l: 52, r: 18, t: 16, b: 28 }

// ---------- tooltip ----------
const tooltipVisible = ref(false)
const tooltip = ref({ value: '', delta: 0, deltaLabel: '', band: '' })
const tooltipStyle = computed(() => {
  if (!hover && !pinned) return {}
  const host = wrapRef.value
  if (!host) return {}
  const rect = host.getBoundingClientRect()
  const cursorX = (pinned || hover)?.x ?? 0
  const cursorY = (pinned || hover)?.y ?? 0
  const left = Math.min(rect.width - 90, Math.max(90, cursorX))
  const top = Math.max(60, cursorY - 12)
  return { left: `${left}px`, top: `${top}px` }
})

const ariaLabel = computed(() => {
  const s = props.sensor
  const name = props.live && s.metric ? s.metric : `${s.cn} ${s.en}`
  return `历史与预测区间示意图 · ${name}`
})

// ---------- 工具 ----------
function niceStep(raw) {
  const power = Math.pow(10, Math.floor(Math.log10(Math.max(1e-6, raw))))
  const norm = raw / power
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10
  return step * power
}

function format(v, digits) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

/** demo 态：连续曲线取值。 */
function demoValueAt(sensor, offsetSec) {
  return valueAt(sensor, props.generatedAt + props.now + offsetSec)
}
function demoForecastAt(sensor, offsetSec) {
  return forecastAt(sensor, props.generatedAt + props.now, Math.max(0, offsetSec))
}
function demoBandAt(sensor, offsetSec) {
  return bandAt(sensor, props.generatedAt + props.now, Math.max(0, offsetSec))
}

/**
 * live 态：把相对「现在」的秒偏移映射到真实采样值。
 * 采样点稀疏（30~60s），这里做线性插值——不伪造更密的数据，只让折线可读。
 */
function liveSample(points, offsetSec) {
  if (!points?.length) return null
  let prev = points[0]
  for (let i = 1; i < points.length; i += 1) {
    const next = points[i]
    if (offsetSec <= next.t) {
      const span = next.t - prev.t
      if (span <= 0) return next.v
      const ratio = (offsetSec - prev.t) / span
      return prev.v + (next.v - prev.v) * ratio
    }
    prev = next
  }
  return prev.v
}

function sampleValue(offsetSec) {
  if (props.live) return liveSample(props.history, offsetSec)
  return demoValueAt(props.sensor, offsetSec)
}
function medianValue(offsetSec) {
  if (props.live) return liveSample(props.forecast, offsetSec)
  return demoForecastAt(props.sensor, offsetSec)
}
function bandValue(offsetSec) {
  if (props.live) return liveBand(offsetSec)
  return demoBandAt(props.sensor, offsetSec)
}
/** live 态 p10/p90 用后端字段直接取；缺失时退化为中位数的 ±4% 视觉带宽。 */
function liveBand(offsetSec) {
  const points = props.forecast || []
  if (!points.length) return 0
  let nearest = points[0]
  for (const point of points) {
    if (Math.abs(point.t - offsetSec) < Math.abs(nearest.t - offsetSec)) nearest = point
  }
  const half = nearest.p90 != null && nearest.median != null
    ? Math.abs(nearest.p90 - nearest.median)
    : Math.abs(nearest.median || 0) * 0.04
  return Math.max(half, 0)
}

/** 视野内的横轴范围（秒）。live 态历史只有 120s 窗口，与 demo 一致。 */
const windowSec = computed(() => ({
  from: -HISTORY,
  to: props.horizon
}))

function computeBounds() {
  const values = []
  for (let t = windowSec.value.from; t <= 0; t += 2) {
    const v = sampleValue(t)
    if (v != null && Number.isFinite(v)) values.push(v)
  }
  for (const point of props.forecast || []) {
    if (point.median != null) values.push(point.median)
    if (point.p90 != null) values.push(point.p90)
    if (point.p10 != null) values.push(point.p10)
  }
  if (!values.length) {
    const base = props.sensor.base || 1
    values.push(base, base + 1)
  }
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const step = niceStep((rawMax - rawMin) / 4 || 1)
  return {
    min: Math.floor(rawMin / step) * step,
    max: Math.ceil(rawMax / step) * step,
    step
  }
}

function scaleX(width) {
  const total = HISTORY + props.horizon
  return v => MARGIN.l + ((v - windowSec.value.from) / total) * (width - MARGIN.l - MARGIN.r)
}

function scaleY(height, range) {
  return v => MARGIN.t + (1 - (v - range.min) / (range.max - range.min)) * (height - MARGIN.t - MARGIN.b)
}

// ---------- 主绘制 ----------
function draw() {
  const canvas = canvasRef.value
  const host = wrapRef.value
  if (!canvas || !host) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const rect = host.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return

  // DPR 变化时重建
  const needResize = canvas.width !== Math.round(rect.width * dpr) ||
                     canvas.height !== Math.round(rect.height * dpr)
  if (needResize || dpr !== lastDpr) {
    canvas.width = Math.round(rect.width * dpr)
    canvas.height = Math.round(rect.height * dpr)
    canvas.style.width = `${rect.width}px`
    canvas.style.height = `${rect.height}px`
    lastDpr = dpr
  }

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, rect.width, rect.height)

  const sensor = props.sensor
  const range = computeBounds()
  const sx = scaleX(rect.width)
  const sy = scaleY(rect.height, range)

  // 颜色（从 CSS 变量读，避免硬编码）
  const styles = getComputedStyle(host)
  const c_accent = styles.getPropertyValue('--fc-accent').trim() || '#2496ED'
  const c_cyan = styles.getPropertyValue('--fc-cyan').trim() || '#7AD7F5'
  const c_text = styles.getPropertyValue('--fc-text').trim() || '#E8F2F7'
  const c_muted = styles.getPropertyValue('--fc-muted').trim() || '#92A6B5'
  const c_dim = styles.getPropertyValue('--fc-dim').trim() || '#5D6B78'
  const c_warn = '#D29922'
  const c_bad = '#F85149'
  const c_grid = 'rgba(255,255,255,.06)'
  const c_grid2 = 'rgba(255,255,255,.04)'
  const c_crosshair = 'rgba(232,242,247,.25)'

  /* === 网格与轴 === */
  ctx.font = '10px Consolas, "Cascadia Mono", monospace'
  ctx.textBaseline = 'middle'
  const rows = Math.max(2, Math.round((range.max - range.min) / range.step))
  for (let i = 0; i <= rows; i += 1) {
    const y = MARGIN.t + ((rect.height - MARGIN.t - MARGIN.b) / rows) * i
    const value = range.max - range.step * i
    ctx.strokeStyle = c_grid
    ctx.beginPath()
    ctx.moveTo(MARGIN.l, y)
    ctx.lineTo(rect.width - MARGIN.r, y)
    ctx.stroke()
    ctx.fillStyle = c_dim
    ctx.textAlign = 'left'
    ctx.fillText(format(value, sensor.digits), 6, y)
  }

  /* 时间刻度（30s 一格） */
  for (let offset = -HISTORY; offset <= props.horizon; offset += 30) {
    const x = sx(offset)
    if (x < MARGIN.l - 1) continue
    ctx.strokeStyle = c_grid2
    ctx.beginPath()
    ctx.moveTo(x, MARGIN.t)
    ctx.lineTo(x, rect.height - MARGIN.b)
    ctx.stroke()
    ctx.fillStyle = c_dim
    ctx.textAlign = 'center'
    ctx.fillText(offset === 0 ? '现在' : `${offset}s`, x, rect.height - 12)
    ctx.textAlign = 'left'
  }

  /* === 阈值线 === */
  const drawThreshold = (value, color, label) => {
    if (!Number.isFinite(value) || value === 0) return
    if (value < range.min) {
      ctx.fillStyle = color
      ctx.textAlign = 'right'
      ctx.fillText(`${label} ↓`, rect.width - MARGIN.r - 2, rect.height - MARGIN.b - 10)
      ctx.textAlign = 'left'
      return
    }
    if (value > range.max) {
      ctx.fillStyle = color
      ctx.textAlign = 'right'
      ctx.fillText(`${label} ↑`, rect.width - MARGIN.r - 2, MARGIN.t + 10)
      ctx.textAlign = 'left'
      return
    }
    const y = sy(value)
    ctx.strokeStyle = color
    ctx.setLineDash([4, 4])
    ctx.beginPath()
    ctx.moveTo(MARGIN.l, y)
    ctx.lineTo(rect.width - MARGIN.r, y)
    ctx.stroke()
    ctx.setLineDash([])
    ctx.fillStyle = color
    ctx.textAlign = 'right'
    ctx.fillText(label, rect.width - MARGIN.r - 2, y - 8)
    ctx.textAlign = 'left'
  }
  drawThreshold(sensor.warn, c_warn, `预警 ${format(sensor.warn, sensor.digits)}`)
  drawThreshold(sensor.crit, c_bad, `越界 ${format(sensor.crit, sensor.digits)}`)

  /* === 不确定带 === */
  ctx.beginPath()
  let bandStarted = false
  for (let h = 0; h <= props.horizon; h += 1) {
    const v = medianValue(h) + bandValue(h)
    if (v == null || !Number.isFinite(v)) continue
    const x = sx(h), y = sy(v)
    if (!bandStarted) { ctx.moveTo(x, y); bandStarted = true } else ctx.lineTo(x, y)
  }
  for (let h = props.horizon; h >= 0; h -= 1) {
    const v = medianValue(h) - bandValue(h)
    if (v == null || !Number.isFinite(v)) continue
    ctx.lineTo(sx(h), sy(v))
  }
  if (bandStarted) {
    ctx.closePath()
    ctx.fillStyle = 'rgba(122,215,245,.12)'
    ctx.fill()
    ctx.strokeStyle = 'rgba(122,215,245,.28)'
    ctx.lineWidth = 1
    ctx.stroke()
  }

  /* === 历史序列 === */
  ctx.beginPath()
  let historyStarted = false
  for (let t = windowSec.value.from; t <= 0; t += 2) {
    const v = sampleValue(t)
    if (v == null || !Number.isFinite(v)) continue
    const x = sx(t), y = sy(v)
    if (!historyStarted) { ctx.moveTo(x, y); historyStarted = true } else ctx.lineTo(x, y)
  }
  if (historyStarted) {
    ctx.strokeStyle = c_accent
    ctx.lineWidth = 1.6
    ctx.stroke()
    // 下方淡填充
    ctx.lineTo(sx(0), rect.height - MARGIN.b)
    ctx.lineTo(sx(windowSec.value.from), rect.height - MARGIN.b)
    ctx.closePath()
    ctx.fillStyle = 'rgba(36,150,237,.08)'
    ctx.fill()
  }

  /* === 预测中位数 === */
  ctx.beginPath()
  let medianStarted = false
  for (let h = 0; h <= props.horizon; h += 1) {
    const v = medianValue(h)
    if (v == null || !Number.isFinite(v)) continue
    const x = sx(h), y = sy(v)
    if (!medianStarted) { ctx.moveTo(x, y); medianStarted = true } else ctx.lineTo(x, y)
  }
  if (medianStarted) {
    ctx.setLineDash([6, 4])
    ctx.strokeStyle = c_cyan
    ctx.lineWidth = 1.7
    ctx.stroke()
    ctx.setLineDash([])
  }

  /* === 影子模型（仅 demo 有意义：真实实现只有一个在跑的模型） === */
  if (props.shadowEnabled && !props.live) {
    ctx.beginPath()
    for (let h = 0; h <= props.horizon; h += 1) {
      const x = sx(h)
      const y = sy(demoForecastAt(sensor, h, sensor.amp * 0.05) - demoBandAt(sensor, h) * 0.18)
      h === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    }
    ctx.setLineDash([2, 3])
    ctx.strokeStyle = c_muted
    ctx.lineWidth = 1.3
    ctx.stroke()
    ctx.setLineDash([])
  }

  /* === 现在线 === */
  const nowX = sx(0)
  ctx.strokeStyle = 'rgba(232,242,247,.45)'
  ctx.setLineDash([3, 5])
  ctx.beginPath()
  ctx.moveTo(nowX, MARGIN.t)
  ctx.lineTo(nowX, rect.height - MARGIN.b)
  ctx.stroke()
  ctx.setLineDash([])

  /* 当前读数角标 */
  {
    const v0 = sampleValue(0)
    if (v0 != null && Number.isFinite(v0)) {
      const y0 = sy(v0)
      ctx.beginPath()
      ctx.arc(nowX, y0, 3, 0, Math.PI * 2)
      ctx.fillStyle = c_cyan
      ctx.fill()
      const label = `${format(v0, sensor.digits)} ${sensor.unit}`
      ctx.font = '10px Consolas, "Cascadia Mono", monospace'
      const width = ctx.measureText(label).width + 14
      const bx = Math.min(rect.width - MARGIN.r - width - 2, nowX + 10)
      const by = Math.max(MARGIN.t + 2, y0 - 28)
      if (typeof ctx.roundRect === 'function') {
        ctx.beginPath()
        ctx.roundRect(bx, by, width, 20, 4)
        ctx.fillStyle = 'rgba(122,215,245,.14)'
        ctx.fill()
        ctx.strokeStyle = 'rgba(122,215,245,.45)'
        ctx.stroke()
        ctx.fillStyle = c_text
        ctx.textAlign = 'left'
        ctx.textBaseline = 'middle'
        ctx.fillText(label, bx + 7, by + 10)
      }
    }
  }

  /* === 越界标记 === */
  props.crossings.forEach(crossing => {
    const x = sx(crossing.h)
    const y = sy(crossing.value)
    if (!Number.isFinite(y)) return
    const color = crossing.kind === 'crit' ? c_bad : c_warn
    ctx.beginPath()
    ctx.arc(x, y, 4.5, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.fill()
    ctx.beginPath()
    ctx.arc(x, y, 8, 0, Math.PI * 2)
    ctx.strokeStyle = crossing.kind === 'crit' ? 'rgba(248,81,73,.35)' : 'rgba(210,153,34,.35)'
    ctx.stroke()
  })

  /* === 悬停/固定十字线 === */
  const cursor = pinned || hover
  if (cursor) {
    const total = HISTORY + props.horizon
    const t = windowSec.value.from + ((cursor.x - MARGIN.l) / (rect.width - MARGIN.l - MARGIN.r)) * total
    const clamped = Math.max(windowSec.value.from, Math.min(props.horizon, t))
    const x = sx(clamped)
    const isFuture = clamped > 0
    const offset = isFuture ? clamped : clamped
    const v = isFuture ? medianValue(offset) : sampleValue(clamped)
    if (v != null && Number.isFinite(v)) {
      const y = sy(v)
      ctx.strokeStyle = c_crosshair
      ctx.setLineDash([2, 3])
      ctx.beginPath()
      ctx.moveTo(x, MARGIN.t)
      ctx.lineTo(x, rect.height - MARGIN.b)
      ctx.stroke()
      ctx.setLineDash([])
      ctx.beginPath()
      ctx.arc(x, y, 3.5, 0, Math.PI * 2)
      ctx.fillStyle = c_text
      ctx.fill()

      const deltaSec = clamped
      const bandWidth = isFuture ? bandValue(offset) : 0
      tooltip.value.value = format(v, sensor.digits)
      tooltip.value.delta = Math.round(deltaSec)
      tooltip.value.deltaLabel = deltaSec === 0 ? '现在' : `${deltaSec > 0 ? '+' : ''}${Math.round(deltaSec)}s`
      tooltip.value.band = isFuture
        ? `${format(v - bandWidth, sensor.digits)} – ${format(v + bandWidth, sensor.digits)}`
        : '采样'
      tooltipVisible.value = true
    } else {
      tooltipVisible.value = false
    }
  } else {
    tooltipVisible.value = false
  }
}

// ---------- ResizeObserver + 事件 ----------
function onPointerMove(e) {
  const rect = wrapRef.value?.getBoundingClientRect()
  if (!rect) return
  hover = { x: e.clientX - rect.left, y: e.clientY - rect.top }
  draw()
}
function onPointerLeave() {
  hover = null
  draw()
}
function onClick() {
  pinned = hover ? { ...hover } : null
  draw()
}

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return
  canvas.addEventListener('pointermove', onPointerMove)
  canvas.addEventListener('pointerleave', onPointerLeave)
  canvas.addEventListener('click', onClick)

  // ResizeObserver
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => draw())
    ro.observe(canvas)
  }
  draw()
})

onBeforeUnmount(() => {
  const canvas = canvasRef.value
  if (canvas) {
    canvas.removeEventListener('pointermove', onPointerMove)
    canvas.removeEventListener('pointerleave', onPointerLeave)
    canvas.removeEventListener('click', onClick)
  }
  ro?.disconnect()
})

// props 变化重绘
watch(
  () => [
    props.sensor.key, props.horizon, props.shadowEnabled, props.now,
    props.generatedAt, props.crossings, props.live, props.history, props.forecast
  ],
  () => draw(),
  { deep: true }
)
</script>

<style scoped>
.forecast-chart-host {
  position: relative;
  width: 100%;
  height: 100%;
  --fc-accent: var(--forecast-accent, #2496ED);
  --fc-cyan: var(--forecast-cyan, #7AD7F5);
  --fc-text: var(--forecast-text, #E8F2F7);
  --fc-muted: var(--forecast-muted, #92A6B5);
  --fc-dim: #5D6B78;
}

.forecast-chart-canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.forecast-chart-tooltip {
  position: absolute;
  z-index: 5;
  min-width: 150px;
  padding: 9px 11px;
  border: 1px solid var(--ds-color-border-strong, rgba(159, 190, 207, .34));
  border-radius: 5px;
  background: var(--ds-surface-overlay, #1B212A);
  color: var(--fc-text);
  font: 11px/1.6 Consolas, 'Cascadia Mono', ui-monospace, monospace;
  pointer-events: none;
  transform: translate(-50%, -110%);
  opacity: 0;
  transition: opacity 120ms ease;
}

.forecast-chart-tooltip[style*="opacity"] {
  opacity: 1;
}

.forecast-chart-tooltip b {
  display: block;
  color: var(--fc-cyan);
  margin-bottom: 4px;
}

.forecast-chart-tooltip span {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--fc-muted);
}
</style>
