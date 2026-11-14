<template>
  <div class="fc-crossings">
    <!-- 主传感器无越界时的友好提示 -->
    <p v-if="!primaryCrossings.length" class="fc-crossings__empty">
      {{ primaryEmptyHint }}
    </p>

    <button
      v-for="(item, idx) in items"
      :key="`${item.sensor.key}-${item.kind}-${item.h}-${idx}`"
      type="button"
      class="fc-crossing"
      :class="{ 'fc-crossing--crit': item.kind === 'crit' }"
      :title="`切到 ${item.sensor.cn}`"
      @click="$emit('switch-sensor', item.sensor.key)"
    >
      <span class="fc-crossing__row">
        <b>{{ item.sensor.cn }} {{ item.sensor.en }}</b>
        <span class="fc-crossing__when" :class="{ 'fc-crossing__when--crit': item.kind === 'crit' }">
          +{{ item.h }}s
        </span>
      </span>
      <small>
        {{ item.kind === 'crit' ? '越界' : '预警' }}
        {{ fmt(item.threshold, item.sensor.digits) }} {{ item.sensor.unit }}
        · 置信 {{ (0.9 - item.h / (horizon * 4)).toFixed(2) }}
      </small>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { SENSORS, crossingEvents } from '../../domain/forecast/syntheticSeries.js'

const props = defineProps({
  primaryKey: { type: String, required: true },
  generatedAt: { type: Number, default: 0 },
  now: { type: Number, default: 0 },
  horizon: { type: Number, default: 30 },
  crossings: { type: Array, default: () => [] }
})

defineEmits(['switch-sensor'])

function fmt(v, d) {
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d })
}

// 聚合所有传感器的越界事件，按时间排，最多 4 条
const allCrossings = computed(() => {
  const nowSec = props.generatedAt + props.now
  const list = []
  // 如果主传感器有 crossings prop 数据，用它；否则实时算
  if (props.crossings?.length) {
    const primary = SENSORS.find(s => s.key === props.primaryKey) || SENSORS[0]
    props.crossings.forEach(c => {
      list.push({ sensor: primary, ...c })
    })
  } else {
    for (const sensor of SENSORS) {
      for (const c of crossingEvents(sensor, nowSec, props.horizon, 2)) {
        list.push({ sensor, ...c })
      }
    }
  }
  list.sort((a, b) => a.h - b.h)
  return list.slice(0, 4)
})

const primaryCrossings = computed(() =>
  allCrossings.value.filter(x => x.sensor.key === props.primaryKey)
)

const items = computed(() => {
  // 先主传感器的，再其他，保持时间顺序
  const rest = allCrossings.value.filter(x => x.sensor.key !== props.primaryKey)
  return [...primaryCrossings.value, ...rest].slice(0, 4)
})

const primaryEmptyHint = computed(() => {
  const sensor = SENSORS.find(s => s.key === props.primaryKey) || SENSORS[0]
  return `${sensor.cn}在 ${props.horizon}s 视野内不会越过阈值；可把视野拉长到 120s 再看。`
})
</script>

<style scoped>
.fc-crossings {
  display: grid;
  gap: 1px;
  background: var(--forecast-line, rgba(255, 255, 255, .06));
}

.fc-crossing {
  display: grid;
  gap: 3px;
  padding: 11px 15px;
  background: var(--forecast-card, #151A21);
  border: 0;
  cursor: pointer;
  text-align: left;
  width: 100%;
  transition: background-color 120ms ease;
}

.fc-crossing:hover {
  background: var(--forecast-overlay, #1B212A);
}

.fc-crossing__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.fc-crossing b {
  font-size: 12px;
  font-weight: 500;
  color: var(--forecast-text, #E8F2F7);
}

.fc-crossing__when {
  color: var(--forecast-warn, #D29922);
  font: 10px var(--forecast-font-mono);
  font-weight: 500;
}

.fc-crossing__when--crit {
  color: var(--forecast-bad, #F85149);
}

.fc-crossing small {
  color: var(--forecast-muted, #92A6B5);
  font: 9.5px var(--forecast-font-mono);
  letter-spacing: .06em;
}

.fc-crossings__empty {
  padding: 16px 15px;
  margin: 0;
  color: var(--forecast-muted, #92A6B5);
  font-size: 12px;
  line-height: 1.7;
  background: var(--forecast-card, #151A21);
}
</style>
