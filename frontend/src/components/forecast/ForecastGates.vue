<template>
  <div class="fc-gates">
    <div
      v-for="sensor in sensors"
      :key="sensor.key"
      class="fc-gate"
      :class="{ 'fc-gate--on': sensor.key === primaryKey }"
      :title="`门控权重 ${sensor.en}`"
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
  primaryKey: { type: String, default: 'ect' }
})

const sensors = SENSORS

// 演示口径：确定性伪随机，主传感器额外高亮 +0.14
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
