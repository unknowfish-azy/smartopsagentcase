<template>
  <div class="forecast-residual-host">
    <canvas ref="canvasRef" class="forecast-residual-canvas"></canvas>
    <p class="forecast-residual-label">窗口 MAE <b>{{ maeText }}</b><em v-if="demo">· 演示值</em></p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { valueAt, slopeAt } from '../../domain/forecast/syntheticSeries.js'

const props = defineProps({
  sensor: { type: Object, required: true },
  now: { type: Number, default: 0 },
  generatedAt: { type: Number, default: 0 },
  demo: { type: Boolean, default: false }
})

const HISTORY = 120
const BARS = 48

const canvasRef = ref(null)
let ro = null
let maeValue = 0

const maeText = computed(() => maeValue.toFixed(2))

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
  const t0 = props.generatedAt + props.now
  const step = rect.width / BARS
  let sum = 0
  for (let i = 0; i < BARS; i += 1) {
    const t = t0 - HISTORY + (i / BARS) * HISTORY
    const err = Math.abs(valueAt(sensor, t) - (valueAt(sensor, t - 6) + slopeAt(sensor, t - 6) * 6))
    sum += err
    const h = Math.min(rect.height - 2, (err / (sensor.amp * 0.6)) * (rect.height - 4) + 2)
    // 超过 35% 幅度转琥珀
    ctx.fillStyle = err > sensor.amp * 0.35
      ? 'rgba(210,153,34,.7)'
      : 'rgba(36,150,237,.55)'
    ctx.fillRect(i * step, rect.height - h, Math.max(1, step - 2), h)
  }
  maeValue = (sum / BARS) * 0.62
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

watch(() => [props.sensor.key, props.now], () => draw())
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
