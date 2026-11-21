<template>
  <table class="fc-sources">
    <thead>
      <tr>
        <th scope="col">{{ labelHeader }}</th>
        <th scope="col">采样</th>
        <th scope="col">缺失</th>
        <th scope="col">延迟</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="item in rows" :key="item.sensor.key">
        <td><b>{{ item.sensor.cn }} {{ item.sensor.en }}</b></td>
        <td class="fc-sources__num">{{ numText(item.sampleRate, 's') }}</td>
        <td class="fc-sources__num" :class="{ 'fc-sources__warn': item.missing > 0.3 }">{{ pctText(item.missing) }}</td>
        <td class="fc-sources__num">{{ numText(item.latency, ' s') }}</td>
      </tr>
    </tbody>
  </table>
</template>

<script setup>
import { computed } from 'vue'
import { SENSORS } from '../../domain/forecast/syntheticSeries.js'

// 确定性演示数据源质量（与设计稿口径一致）
const DEMO_QUALITY = Object.freeze({
  ect:  { sampleRate: 1, missing: 0.10, latency: 0.8 },
  rpm:  { sampleRate: 1, missing: 0.16, latency: 1.0 },
  egt:  { sampleRate: 1, missing: 0.22, latency: 1.2 },
  oilp: { sampleRate: 1, missing: 0.28, latency: 1.4 },
  iat:  { sampleRate: 1, missing: 0.34, latency: 1.6 },
  vbat: { sampleRate: 1, missing: 0.40, latency: 1.8 }
})

const props = defineProps({
  // 后端返回的真实槽位：{ key, label, metric, unit, sampleRate, missing, latency }
  sourceData: { type: Array, default: () => [] },
  /** live 态列头写「指标」，demo 态仍写「传感器」。 */
  labelHeader: { type: String, default: '传感器' }
})

function numText(value, suffix) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return `${Number(value)}${suffix}`
}
function pctText(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return `${Number(value).toFixed(2)}%`
}

const rows = computed(() => {
  // 优先用后端真实槽位；否则用演示口径
  if (props.sourceData?.length) {
    return props.sourceData.map(s => {
      const demo = SENSORS.find(x => x.key === s.key)
      return {
        sensor: {
          key: s.key,
          // live 的真实指标名（cn 已含中文语义，en 用于别名提示）
          cn: s.label || demo?.cn || s.key,
          en: demo?.en || ''
        },
        sampleRate: s.sampleRate,
        missing: s.missing,
        latency: s.latency
      }
    })
  }
  return SENSORS.map(s => ({
    sensor: s,
    ...DEMO_QUALITY[s.key]
  }))
})
</script>

<style scoped>
.fc-sources {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}

.fc-sources th,
.fc-sources td {
  padding: 7px 15px;
  text-align: left;
  border-top: 1px solid var(--forecast-line, rgba(255, 255, 255, .06));
  color: var(--forecast-muted, #92A6B5);
}

.fc-sources th {
  color: var(--forecast-muted, #92A6B5);
  font: 8.5px var(--forecast-font-mono);
  letter-spacing: .12em;
  border-top: 0;
}

.fc-sources td b {
  color: var(--forecast-text, #E8F2F7);
  font-weight: 500;
}

.fc-sources__num {
  font-family: var(--forecast-font-mono);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.fc-sources__warn {
  color: var(--forecast-warn, #D29922);
}

.fc-sources tbody tr:hover td {
  background: var(--forecast-overlay, #1B212A);
}
</style>
