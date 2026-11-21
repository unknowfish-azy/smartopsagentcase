<template>
  <div class="fc-gates">
    <!-- live 态没有 GRU 门控：权重不可得，如实说明而不是画假条 -->
    <p v-if="live" class="fc-gates__empty">
      当前预测走统计降级（{{ mode || 'linear / seasonal_naive' }}），没有可导出的门控权重。
      PatchTST 权重加载后这里才会显示真实注意力/门控结构。
    </p>
    <div
      v-for="sensor in sensors"
      v-else
      :key="sensor.key"
      class="fc-gate"
      :class="{ 'fc-gate--on': sensor.key === primaryKey }"
      :title="`门控权重 ${sensor.en}（演示口径）`"
    >
      <span class="fc-gate__label">{{ sensor.en }}</span>
      <span class="fc-gate__track">
        <span
          class="fc-gate__fill"
          :style="{ transform: `scaleX(${weightFor(sensor)})` }"
        ></span>
      </span>
      <b class="fc-gate__value">{{ weightFor(sensor).toFixed(2) }}</b>
    </div>
  </div>
</template>

<script setup>
import { SENSORS } from '../../domain/forecast/syntheticSeries.js'

const props = defineProps({
  primaryKey: { type: String, default: 'ect' },
  /** live 态不显示合成门控权重。 */
  live: { type: Boolean, default: false },
  mode: { type: String, default: '' }
})

const sensors = SENSORS

// 演示口径：确定性伪随机，主传感器额外高亮 +0.14；仅 demo 态渲染。
function weightFor(sensor) {
  const base = 0.12 + Math.abs(Math.sin(sensor.base)) * 0.32
  const boost = sensor.key === props.primaryKey ? 0.14 : 0
  return Math.min(0.99, base + boost)
}
</script>

<style scoped>
.fc-gates {
  display: grid;
  gap: 9px;
  padding: 13px 15px 15px;
}

.fc-gates__empty {
  margin: 0;
  color: var(--forecast-muted, #92A6B5);
  font-size: 11.5px;
  line-height: 1.7;
}

.fc-gate {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) 34px;
  align-items: center;
  gap: 9px;
  color: var(--forecast-muted, #92A6B5);
  font-size: 11px;
}

.fc-gate--on {
  color: var(--forecast-text, #E8F2F7);
}

.fc-gate__track {
  position: relative;
  height: 4px;
  background: var(--forecast-line, rgba(255, 255, 255, .06));
  border-radius: 2px;
  overflow: hidden;
}

.fc-gate__fill {
  position: absolute;
  inset: 0;
  background: var(--forecast-accent, #2496ED);
  transform-origin: 0 50%;
  transition: transform 500ms cubic-bezier(.22, 1, .36, 1);
}

.fc-gate--on .fc-gate__fill {
  background: var(--forecast-cyan, #7AD7F5);
}

.fc-gate__value {
  text-align: right;
  color: var(--forecast-muted, #92A6B5);
  font: 10px var(--forecast-font-mono);
  font-variant-numeric: tabular-nums;
}

.fc-gate--on .fc-gate__value {
  color: var(--forecast-text, #E8F2F7);
}
</style>
