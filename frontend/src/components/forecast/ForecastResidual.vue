<template>
  <div class="forecast-residual-host">
    <canvas ref="canvasRef" class="forecast-residual-canvas"></canvas>
    <p class="forecast-residual-label">
      窗口 MAE <b>{{ maeText }}</b><em v-if="demo">· 演示值</em><em v-else-if="!hasData">· 数据不足</em>
    </p>
  </div>
</template>

<script setup>
/**
 * 残差条：最近 120s 的逐步误差柱状 + 窗口 MAE。
 *
 * demo 态：沿用合成口径（|实测 − 6 秒前外推|），只作管线自检。
 * live  态：用后端返回的真实历史序列算同样的逐步误差；MAE 只是"这批采样的粗糙波动度量"，
 *           不是模型评测指标——真实 MAE/RMSE/MAPE 需要独立测试集，目前无评测产物。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { valueAt, slopeAt } from '../../domain/forecast/syntheticSeries.js'

const props = defineProps({
  sensor: { type: Object, required: true },
  now: { type: Number, default: 0 },
  generatedAt: { type: Number, default: 0 },
  demo: { type: Boolean, default: false },
  series: { type: Array, default: () => [] },
  live: { type: Boolean, default: false }
})

const HISTORY = 120
const BARS = 48

const canvasRef = ref(null)
let ro = null
let maeValue = 0
const hasData = ref(false)

const maeText = computed(() => (hasData.value ? maeValue.toFixed(2) : '—'))

/** live 态：按秒偏移取真实采样值（线性插值，不加密数据）。 */
function liveValue(offsetSec) {
  const points = props.series || []
  if (!points.length) return null
  let prev = points[0]
  for (let i = 1; i < points.length; i += 1) {
    const next = points[i]
    if (offsetSec <= next.t) {
      const span = next.t - prev.t
      if (span <= 0) return next.v
      return prev.v + (next.v - prev.v) * ((offsetSec - prev.t) / span)
    }
    prev = next
  }
  return prev.v
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  if (rect.width === 0) return
  canvas.width = Math.round(rect.width * dpr)
  canvas.height = Math.round(rect.height * dpr)
  canvas.style.width = `${rect.width}px`
  canvas.style.height = `${rect.height}px`
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, rect.width, rect.height)

  const sensor = props.sensor
  const step = rect.width / BARS
  let sum = 0
  let counted = 0
  hasData.value = false

  for (let i = 0; i < BARS; i += 1) {
    const offset = -HISTORY + (i / BARS) * HISTORY
    let observed
    let extrapolated
    if (props.live) {
      observed = liveValue(offset)
      const back = liveValue(offset - 6)
      const ahead = liveValue(offset + 6)
      if (observed == null || back == null) continue
      const slope = ahead == null ? 0 : (ahead - back) / 12
      extrapolated = back + slope * 6
    } else {
      const t = props.generatedAt + props.now + offset
      observed = valueAt(sensor, t)
      extrapolated = valueAt(sensor, t - 6) + slopeAt(sensor, t - 6) * 6
    }
    const err = Math.abs(observed - extrapolated)
    const scale = sensor.amp || Math.max(1, Math.abs(observed) * 0.1)
    sum += err
    counted += 1
    const h = Math.min(rect.height - 2, (err / (scale * 0.6)) * (rect.height - 4) + 2)
    ctx.fillStyle = err > scale * 0.35
      ? 'rgba(210,153,34,.7)'
      : 'rgba(36,150,237,.55)'
    ctx.fillRect(i * step, rect.height - h, Math.max(1, step - 2), h)
  }

  if (counted > 0) {
    // 与 demo 同口径的缩放系数，让两态量级可比（仅视觉，不是评测指标）。
    maeValue = (sum / counted) * (props.live ? 1 : 0.62)
    hasData.value = true
  }
}

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => draw())
    ro.observe(canvas)
  }
  draw()
})

onBeforeUnmount(() => ro?.disconnect())

watch(() => [props.sensor.key, props.now, props.live, props.series], () => draw(), { deep: true })
</script>

<style scoped>
.forecast-residual-host {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 8px 15px;
}

.forecast-residual-canvas {
  display: block;
  width: 100%;
  height: 44px;
}

.forecast-residual-label {
  margin: 0;
  color: var(--forecast-muted, #92A6B5);
  font: 10px var(--forecast-font-mono, Consolas, monospace);
  letter-spacing: .08em;
  white-space: nowrap;
}

.forecast-residual-label b {
  color: var(--forecast-text, #E8F2F7);
  font-weight: 500;
}

.forecast-residual-label em {
  font-style: normal;
  color: var(--forecast-muted, #92A6B5);
  font-size: 10px;
  margin-left: 4px;
}
</style>
