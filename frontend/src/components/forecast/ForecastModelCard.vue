<template>
  <div class="fc-model">
    <!-- 结构图 -->
    <div class="fc-model__arch">
      <div class="fc-layer fc-layer--io">
        <small>输入</small>
        <span>12×6</span>
      </div>
      <span class="fc-model__arrow">→</span>
      <div class="fc-layer">
        <small>GRU</small>
        <span>64</span>
      </div>
      <span class="fc-model__arrow">→</span>
      <div class="fc-layer">
        <small>GRU</small>
        <span>32</span>
      </div>
      <span class="fc-model__arrow">→</span>
      <div class="fc-layer">
        <small>MLP</small>
        <span>16→1</span>
      </div>
    </div>

    <!-- 指标 -->
    <div class="fc-model__metrics" role="group" aria-label="模型指标">
      <div class="fc-model__metric">
        <span>MAE</span>
        <b>{{ fmt(metrics?.mae ?? NaN) }}</b>
        <em>{{ unit }}</em>
      </div>
      <div class="fc-model__metric">
        <span>RMSE</span>
        <b>{{ fmt(metrics?.rmse ?? NaN) }}</b>
        <em>{{ unit }}</em>
      </div>
      <div class="fc-model__metric">
        <span>MAPE</span>
        <b>{{ fmt(metrics?.mape ?? NaN) }}</b>
        <em>%</em>
      </div>
    </div>

    <!-- 页脚元数据 -->
    <div class="fc-model__foot">
      <span>参数 <b>{{ formatNum(params) }}</b></span>
      <span>{{ trainedAtText }}</span>
      <span>{{ epochs }} epochs</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  metrics: { type: Object, default: () => ({ mae: null, rmse: null, mape: null }) },
  unit: { type: String, default: '' },
  params: { type: Number, default: null },
  trainedAt: { type: String, default: '' },
  epochs: { type: Number, default: null }
})

function fmt(v) {
  if (v == null || Number.isNaN(v)) return '—'
  return Number(v).toFixed(2)
}
function formatNum(n) {
  if (n == null) return '—'
  return n.toLocaleString('en-US')
}
const trainedAtText = computed(() => {
  if (!props.trainedAt) return '训练时间 —'
  try {
    const d = new Date(props.trainedAt)
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return props.trainedAt }
})
</script>

<style scoped>
.fc-model {
  display: grid;
  gap: 1px;
}

.fc-model__arch {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 14px 15px 4px;
  overflow: auto;
}

.fc-layer {
  display: grid;
  justify-items: center;
  gap: 3px;
  padding: 7px 8px;
  border: 1px solid var(--forecast-line-strong, rgba(159, 190, 207, .34));
  border-radius: 4px;
  background: rgba(36, 150, 237, .06);
  color: var(--forecast-text, #E8F2F7);
  font: 10px var(--forecast-font-mono);
  letter-spacing: .04em;
  white-space: nowrap;
}

.fc-layer small {
  color: var(--forecast-muted, #92A6B5);
  font-size: 8px;
}

.fc-layer--io {
  background: rgba(122, 215, 245, .08);
  border-color: rgba(122, 215, 245, .35);
}

.fc-model__arrow {
  color: var(--forecast-muted, #92A6B5);
  font-size: 10px;
}

.fc-model__metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  margin: 12px 15px 0;
  background: var(--forecast-line, rgba(255, 255, 255, .06));
  border: 1px solid var(--forecast-line, rgba(255, 255, 255, .06));
}

.fc-model__metric {
  background: var(--forecast-card, #151A21);
  padding: 9px 10px;
}

.fc-model__metric span {
  display: block;
  color: var(--forecast-muted, #92A6B5);
  font: 8.5px var(--forecast-font-mono);
  letter-spacing: .14em;
}

.fc-model__metric b {
  display: block;
  margin-top: 5px;
  font: 16px var(--forecast-font-mono);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--forecast-text, #E8F2F7);
}

.fc-model__metric em {
  font-style: normal;
  color: var(--forecast-muted, #92A6B5);
  font-size: 10px;
}

.fc-model__foot {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 15px 13px;
  color: var(--forecast-muted, #92A6B5);
  font: 9px var(--forecast-font-mono);
  letter-spacing: .08em;
}

.fc-model__foot b {
  color: var(--forecast-text, #E8F2F7);
  font-weight: 500;
}
</style>
