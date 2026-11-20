<template>
  <div ref="wrapRef" class="so-chart-host">
    <canvas ref="canvasRef" class="so-chart-canvas" :aria-label="ariaLabel" role="img"></canvas>
    <div v-if="tooltipVisible" class="so-chart-tooltip" :style="tooltipStyle">
      <b>{{ tooltip.timeLabel }}</b>
      <span v-for="row in tooltip.rows" :key="row.key">
        <i :style="{ color: row.color }">{{ row.en }}</i>
        <i>{{ row.offset }}%</i>
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  sensors: { type: Array, default: () => [] },          // 选中的 sensor 对象（forecast SENSORS 子集）
  series: { type: Object, default: () => ({}) },        // { [key]: [{t, o}] } 归一化偏移序列
  generatedAt: { type: Number, default: 0 },            // 窗口终点（秒）
  windowSec: { type: Number, default: 120 }
})

const PALETTE = ['#2496ED', '#7AD7F5', '#C792EA', '#F0C674', '#8BD450', '#E8A0BF']

const wrapRef = ref(null)
const canvasRef = ref(null)
let ro = null
let lastDpr = 1
let hover = null
const MARGIN = { l: 46, r: 14, t: 14, b: 26 }

const tooltipVisible = ref(false)
const tooltip = ref({ timeLabel: '', rows: [] })
const tooltipStyle = ref({})

const ariaLabel = computed(() =>
  `多测点归一化偏移叠加图 · ${props.sensors.map(s => s.en).join('/') || '未选择'}（单位：相对基线带宽 %）`
)

function niceStep(raw) {
  const power = Math.pow(10, Math.floor(Math.log10(Math.max(1e-6, raw))))
  const norm = raw / power
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10
  return step * power
}

function draw() {
  const canvas = canvasRef.value
  const host = wrapRef.value
  if (!canvas || !host) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const rect = host.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return

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

  const c_dim = '#5D6B78'
  const c_zero = 'rgba(232,242,247,.35)'
  const c_grid = 'rgba(255,255,255,.06)'

  const t1 = props.generatedAt || Math.floor(Date.now() / 1000)
  const t0 = t1 - props.windowSec

  // 边界（对称化：让 0 居中观感稳定）
  let rawMax = 10
  for (const key of props.sensors.map(s => s.key)) {
    for (const p of props.series[key] || []) rawMax = Math.max(rawMax, Math.abs(p.o))
  }
  const step = niceStep(rawMax / 3 || 1)
  const bound = Math.ceil((rawMax * 1.1) / step) * step

  const sx = t => MARGIN.l + ((t - t0) / props.windowSec) * (rect.width - MARGIN.l - MARGIN.r)
  const sy = o => MARGIN.t + (1 - (o + bound) / (2 * bound)) * (rect.height - MARGIN.t - MARGIN.b)

  ctx.font = '10px Consolas, "Cascadia Mono", monospace'
  ctx.textBaseline = 'middle'

  // 横向网格 + ±刻度
  const rows = Math.max(2, Math.round((2 * bound) / step))
  for (let i = 0; i <= rows; i += 1) {
    const o = bound - step * i
    const y = sy(o)
    ctx.strokeStyle = Math.abs(o) < 1e-9 ? c_zero : c_grid
    ctx.beginPath()
    ctx.moveTo(MARGIN.l, y)
    ctx.lineTo(rect.width - MARGIN.r, y)
    ctx.stroke()
    ctx.fillStyle = c_dim
    ctx.textAlign = 'left'
    ctx.fillText(`${o > 0 ? '+' : ''}${Math.round(o)}%`, 6, y)
  }

  // 时间刻度（窗口 1/4 分格）
  for (let i = 0; i <= 4; i += 1) {
    const t = t0 + (props.windowSec / 4) * i
    const x = sx(t)
    ctx.strokeStyle = c_grid
    ctx.beginPath()
    ctx.moveTo(x, MARGIN.t)
    ctx.lineTo(x, rect.height - MARGIN.b)
    ctx.stroke()
    ctx.fillStyle = c_dim
    ctx.textAlign = 'center'
    ctx.fillText(i === 4 ? '现在' : `−${Math.round(t1 - t)}s`, x, rect.height - 10)
    ctx.textAlign = 'left'
  }

  // 各测点叠加曲线
  props.sensors.forEach((sensor, idx) => {
    const pts = props.series[sensor.key] || []
    if (!pts.length) return
    ctx.beginPath()
    pts.forEach((p, i) => {
      const x = sx(p.t), y = sy(Math.max(-bound, Math.min(bound, p.o)))
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.strokeStyle = PALETTE[idx % PALETTE.length]
    ctx.lineWidth = 1.6
    ctx.stroke()
  })

  // 悬停十字线 + 各测点读数
  if (hover) {
    const t = t0 + ((hover.x - MARGIN.l) / (rect.width - MARGIN.l - MARGIN.r)) * props.windowSec
    const clamped = Math.max(t0, Math.min(t1, t))
    const x = sx(clamped)
    ctx.strokeStyle = 'rgba(232,242,247,.25)'
    ctx.setLineDash([2, 3])
    ctx.beginPath()
    ctx.moveTo(x, MARGIN.t)
    ctx.lineTo(x, rect.height - MARGIN.b)
    ctx.stroke()
    ctx.setLineDash([])

    const rows = props.sensors.map((sensor, idx) => {
      const pts = props.series[sensor.key] || []
      let best = pts[0]
      for (const p of pts) {
        if (Math.abs(p.t - clamped) < Math.abs(best.t - clamped)) best = p
      }
      const color = PALETTE[idx % PALETTE.length]
      if (best) {
        const y = sy(Math.max(-bound, Math.min(bound, best.o)))
        ctx.beginPath()
        ctx.arc(x, y, 3.2, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()
      }
      return {
        key: sensor.key,
        en: sensor.en,
        color,
        offset: best ? `${best.o > 0 ? '+' : ''}${best.o.toFixed(1)}` : '—'
      }
    })
    tooltip.value.timeLabel = clamped >= t1 ? '现在' : `−${Math.round(t1 - clamped)}s`
    tooltip.value.rows = rows
    const hostRect = host.getBoundingClientRect()
    tooltipStyle.value = {
      left: `${Math.min(hostRect.width - 110, Math.max(90, hover.x))}px`,
      top: `${Math.max(56, hover.y - 10)}px`
    }
    tooltipVisible.value = true
  } else {
    tooltipVisible.value = false
  }
}

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

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return
  canvas.addEventListener('pointermove', onPointerMove)
  canvas.addEventListener('pointerleave', onPointerLeave)
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
  }
  ro?.disconnect()
})

watch(
  () => [props.sensors.map(s => s.key).join(','), props.series, props.generatedAt, props.windowSec],
  () => draw(),
  { deep: true }
)
</script>

<style scoped>
.so-chart-host {
  position: relative;
  width: 100%;
  height: 100%;
  --so-text: var(--ds-color-text, var(--smart-text, #E8F2F7));
}

.so-chart-canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.so-chart-tooltip {
  position: absolute;
  z-index: 5;
  min-width: 130px;
  padding: 9px 11px;
  border: 1px solid var(--ds-color-border-strong, rgba(159, 190, 207, .34));
  border-radius: 5px;
  background: var(--ds-surface-overlay, #1B212A);
  color: var(--so-text);
  font: 11px/1.6 Consolas, 'Cascadia Mono', ui-monospace, monospace;
  pointer-events: none;
  transform: translate(-50%, -110%);
}

.so-chart-tooltip b {
  display: block;
  margin-bottom: 4px;
}

.so-chart-tooltip span {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.so-chart-tooltip i {
  font-style: normal;
  color: var(--ds-color-muted, var(--smart-muted, #92A6B5));
}

@media (prefers-reduced-motion: reduce) {
  .so-chart-host * { transition: none !important; animation: none !important; }
}
</style>
