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
      :title="live ? `${item.sensor.cn} ${item.metric || ''}` : `切到 ${item.sensor.cn}`"
      @click="!live && $emit('switch-sensor', item.sensor.key)"
    >
      <span class="fc-crossing__row">
        <b>{{ item.sensor.cn }} {{ item.sensor.en }}</b>
        <span class="fc-crossing__when" :class="{ 'fc-crossing__when--crit': item.kind === 'crit' }">
          +{{ item.h }}s
        </span>
      </span>
      <small>
        {{ item.kind === 'crit' ? '越界' : '预警' }}
        {{ fmt(item.threshold, item.sensor.digits ?? 1) }} {{ item.unit || '' }}
        · 置信 {{ confidenceText(item) }}
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
  crossings: { type: Array, default: () => [] },
  /** live 态：后端已算好越界，名称/单位取真实指标。 */
  live: { type: Boolean, default: false },
  sensorCn: { type: String, default: '' },
  sensorEn: { type: String, default: '' },
  /** live 态：后端 crossings 不带 metric，需由调用方补齐才能选对文案。 */
  metricName: { type: String, default: '' },
  sensorDigits: { type: Number, default: 1 },
  unit: { type: String, default: '' }
})

defineEmits(['switch-sensor'])

function fmt(v, d) {
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d })
}

/** live 态置信度由后端给（启发式、未校准），缺省时不编造数字。 */
function confidenceText(item) {
  const value = Number(item.confidence)
  return Number.isFinite(value) ? value.toFixed(2) : '—'
}

// 聚合越界事件，按时间排，最多 4 条
const allCrossings = computed(() => {
  const nowSec = props.generatedAt + props.now
  const list = []
  if (props.live) {
    // 真实链路只有当前选中的一个指标，后端已给出它的越界事件。
    const digits = Number.isFinite(Number(props.sensorDigits)) ? Number(props.sensorDigits) : 1
    const metric = props.metricName || ''
    props.crossings.forEach((c) => {
      list.push({
        ...c,
        sensor: { key: props.primaryKey, cn: props.sensorCn, en: props.sensorEn, digits, metric }
      })
    })
    return list.sort((a, b) => a.h - b.h).slice(0, 4)
  }
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
  if (props.live) {
    return `${props.sensorCn || props.primaryKey}在 ${props.horizon}s 视野内没有达到阈值；` +
      '可把视野拉长到 120s 再看，或保持现况。'
  }
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
