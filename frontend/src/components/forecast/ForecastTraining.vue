<template>
  <div class="fc-train-strip">
    <div class="fc-train-copy">
      <h2>训练与评估</h2>
      <p v-if="statFallback">
        本次预测走统计降级（{{ modeLabel }}），没有训练过程、验证集损失与门控权重可展示；
        采样 {{ sampleCountText }} · 推理 {{ inferenceText }}。
      </p>
      <p v-else>
        验证集损失随 epoch 下降，第 {{ bestEpoch }} 轮后不再改善即早停；
        门禁只看验证集，不看训练集。
      </p>
    </div>
    <div class="fc-train-chart">
      <canvas v-if="!statFallback" ref="canvasRef"></canvas>
      <p v-else class="fc-train__fallback">
        无训练产物：{{ modelStatusDetail || '模型权重未加载，预测由统计基线产出' }}
      </p>
    </div>
    <div class="fc-train-state">
      <span v-if="!statFallback">
        门禁 <b :class="{ 'fc-train__warn': gate !== 'PASS' }">{{ gateLabel }}</b>
      </span>
      <span v-if="!statFallback && bestEpoch">
        最佳 epoch <b>{{ bestEpoch }}</b>
      </span>
      <span v-if="!statFallback">
        下次重训 <b>{{ retrainLabel }}</b>
      </span>
      <span v-if="statFallback">
        模型状态 <b class="fc-train__warn">{{ gateLabel }}</b>
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  gate: { type: String, default: 'PASS' },        // PASS | FAIL | PENDING | FALLBACK
  bestEpoch: { type: Number, default: 38 },
  retrainAt: { type: String, default: '' },
  /** live 态：真实链路，无训练产物时如实说明。 */
  live: { type: Boolean, default: false },
  kind: { type: String, default: '' },
  mode: { type: String, default: '' },
  modelStatusDetail: { type: String, default: '' },
  sampleCount: { type: Number, default: null },
  inferenceMs: { type: Number, default: null },
  /** demo 态仍画合成训练曲线。 */
  demo: { type: Boolean, default: false }
})

const canvasRef = ref(null)
let ro = null

/** 统计降级（无 PatchTST 权重）时不存在训练曲线，改用文字说明。 */
const statFallback = computed(() => props.live && props.kind !== 'neural')
const modeLabel = computed(() => {
  const mode = props.mode || 'unknown'
  if (mode === 'linear') return '线性基线'
  if (mode === 'seasonal_naive') return '季节朴素基线'
  return mode
})
const sampleCountText = computed(() => (props.sampleCount == null ? '—' : `${props.sampleCount} 点`))
const inferenceText = computed(() => (props.inferenceMs == null ? '—' : `${Number(props.inferenceMs).toFixed(0)}ms`))

const gateLabel = computed(() => {
  if (props.gate === 'PASS') return '通过'
  if (props.gate === 'FAIL') return '未通过'
  if (props.gate === 'FALLBACK') return '降级'
  return '等待中'
})

const retrainLabel = computed(() => {
  if (!props.retrainAt) return '—'
  try {
    const target = new Date(props.retrainAt).getTime()
    const diff = target - Date.now()
    if (diff <= 0) return '已到期'
    const h = Math.round(diff / 3600000)
    if (h < 1) return `${Math.round(diff / 60000)}m`
    return `${h}h`
  } catch { return '—' }
})

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return
  canvas.width = Math.round(rect.width * dpr)
  canvas.height = Math.round(rect.height * dpr)
  canvas.style.width = `${rect.width}px`
  canvas.style.height = `${rect.height}px`
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, rect.width, rect.height)

  const epochs = 46
  const line = (value, color, dash) => {
    ctx.beginPath()
    for (let i = 0; i < epochs; i += 1) {
      const x = (i / (epochs - 1)) * (rect.width - 8) + 4
      const y = rect.height - 6 - value(i) * (rect.height - 12)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    }
    ctx.strokeStyle = color
    ctx.lineWidth = 1.4
    ctx.setLineDash(dash || [])
    ctx.stroke()
    ctx.setLineDash([])
  }
  line(i => Math.exp(-i / 11) * 0.92 + 0.05 + Math.sin(i / 3) * 0.012, 'rgba(36,150,237,.75)')
  line(i => Math.exp(-i / 12) * 0.84 + 0.12 + Math.sin(i / 2.4) * 0.02, 'rgba(122,215,245,.9)', [4, 3])

  ctx.fillStyle = '#5D6B78'
  ctx.font = '9px Consolas, monospace'
  ctx.textAlign = 'left'
  ctx.fillText('train', 4, 10)
  ctx.fillStyle = '#7AD7F5'
  ctx.fillText('val', 40, 10)
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

watch(() => [props.gate, props.bestEpoch], () => draw())
</script>

<style scoped>
.fc-train-strip {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px auto;
  gap: 18px;
  align-items: center;
  padding: 14px 16px;
}

.fc-train-copy h2 {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 500;
  color: var(--forecast-text, #E8F2F7);
}

.fc-train-copy p {
  margin: 0;
  color: var(--forecast-muted, #92A6B5);
  font-size: 11.5px;
  line-height: 1.7;
}

.fc-train-chart canvas {
  display: block;
  width: 100%;
  height: 56px;
}

.fc-train__fallback {
  display: flex;
  align-items: center;
  height: 56px;
  margin: 0;
  padding: 0 12px;
  color: var(--forecast-muted, #92A6B5);
  font: 10px var(--forecast-font-mono);
  letter-spacing: .04em;
  line-height: 1.6;
}

.fc-train-state {
  display: grid;
  gap: 4px;
  justify-items: end;
  color: var(--forecast-muted, #92A6B5);
  font: 10px var(--forecast-font-mono);
  letter-spacing: .08em;
  white-space: nowrap;
}

.fc-train-state b {
  color: var(--forecast-ok, #8bcfb4);
  font-weight: 500;
}

.fc-train__warn {
  color: var(--forecast-warn, #D29922) !important;
}

@media (max-width: 760px) {
  .fc-train-strip {
    grid-template-columns: minmax(0, 1fr);
  }
  .fc-train-state {
    grid-auto-flow: column;
    justify-items: start;
    gap: 16px;
  }
}
</style>
