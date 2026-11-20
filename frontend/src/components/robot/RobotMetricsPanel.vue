<template>
  <section class="metrics" aria-labelledby="metrics-title">
    <header class="metrics-head">
      <div>
        <p class="metrics-eyebrow">OBSERVABILITY · 真实遥测</p>
        <h3 id="metrics-title">运行指标</h3>
      </div>
      <span class="metrics-note">仅统计已上报数据，不补齐空缺</span>
    </header>

    <div class="kpi-grid">
      <article class="kpi">
        <span class="kpi-label">在线设备</span>
        <strong>{{ kpis.online }}<small> / {{ kpis.total }}</small></strong>
        <div class="kpi-track"><span :style="{ width: onlineRatio }"></span></div>
      </article>
      <article class="kpi">
        <span class="kpi-label">执行中任务</span>
        <strong>{{ kpis.running }}</strong>
        <span class="kpi-foot">失败 {{ kpis.failed }} · 暂停 {{ kpis.paused }}</span>
      </article>
      <article class="kpi">
        <span class="kpi-label">未确认预警</span>
        <strong :class="{ warn: kpis.alerts > 0 }">{{ kpis.alerts }}</strong>
        <span class="kpi-foot">严重 {{ kpis.critical }} · 高 {{ kpis.high }}</span>
      </article>
      <article class="kpi">
        <span class="kpi-label">机队平均电量</span>
        <strong>{{ kpis.avgBattery === null ? '—' : `${kpis.avgBattery}%` }}</strong>
        <div class="kpi-track"><span :style="{ width: `${kpis.avgBattery || 0}%` }"></span></div>
      </article>
    </div>

    <div class="metrics-grid">
      <article class="chart-card">
        <header class="chart-head">
          <h4>{{ selectedName }} · 电量趋势</h4>
          <span>{{ selectedBatteryNow === null ? '暂无上报' : `${selectedBatteryNow}%` }}</span>
        </header>
        <svg v-if="batterySpark" class="spark" viewBox="0 0 280 70" preserveAspectRatio="none" role="img" aria-label="电量趋势">
          <defs>
            <linearGradient id="batteryFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#3abe84" stop-opacity="0.32" />
              <stop offset="100%" stop-color="#3abe84" stop-opacity="0" />
            </linearGradient>
          </defs>
          <path :d="batterySpark.area" fill="url(#batteryFill)" />
          <path :d="batterySpark.line" fill="none" stroke="#3abe84" stroke-width="2" stroke-linejoin="round" />
          <line x1="0" y1="56" x2="280" y2="56" stroke="#22303f" stroke-width="1" />
        </svg>
        <p v-else class="chart-empty">等待设备上报至少 2 个电量采样</p>
      </article>

      <article class="chart-card">
        <header class="chart-head">
          <h4>{{ selectedName }} · 移动速度</h4>
          <span>{{ lastSpeed === null ? '暂无位移' : `${lastSpeed.toFixed(2)} m/s` }}</span>
        </header>
        <svg v-if="speedSpark" class="spark" viewBox="0 0 280 70" preserveAspectRatio="none" role="img" aria-label="移动速度趋势">
          <defs>
            <linearGradient id="speedFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#5b8cff" stop-opacity="0.3" />
              <stop offset="100%" stop-color="#5b8cff" stop-opacity="0" />
            </linearGradient>
          </defs>
          <path :d="speedSpark.area" fill="url(#speedFill)" />
          <path :d="speedSpark.line" fill="none" stroke="#5b8cff" stroke-width="2" stroke-linejoin="round" />
          <line x1="0" y1="56" x2="280" y2="56" stroke="#22303f" stroke-width="1" />
        </svg>
        <p v-else class="chart-empty">速度由相邻遥测位姿差计算，暂无有效位移</p>
      </article>

      <article class="chart-card">
        <header class="chart-head">
          <h4>{{ selectedName }} · 任务结果</h4>
          <span>最近 {{ tasks.length }} 条</span>
        </header>
        <div v-if="taskBuckets.length" class="bucket-list">
          <div v-for="bucket in taskBuckets" :key="bucket.key" class="bucket">
            <span class="bucket-label">{{ bucket.label }}</span>
            <div class="bucket-track"><span :class="bucket.key.toLowerCase()" :style="{ width: `${bucket.percent}%` }"></span></div>
            <span class="bucket-value">{{ bucket.count }}</span>
          </div>
        </div>
        <p v-else class="chart-empty">该设备还没有任务记录</p>
      </article>

      <article class="chart-card">
        <header class="chart-head">
          <h4>机队电量分布</h4>
          <span>{{ batteryDevices.length }} 台有数据</span>
        </header>
        <div v-if="batteryDevices.length" class="bucket-list">
          <div v-for="item in batteryDevices" :key="item.key" class="bucket">
            <button type="button" class="bucket-label link" @click="emit('select', item.key)">{{ item.name }}</button>
            <div class="bucket-track"><span :class="item.level" :style="{ width: `${item.battery}%` }"></span></div>
            <span class="bucket-value">{{ item.battery }}%</span>
          </div>
        </div>
        <p v-else class="chart-empty">暂无设备上报电量</p>
      </article>
    </div>

    <div class="alert-strip">
      <span class="strip-title">预警构成</span>
      <span v-for="item in alertBuckets" :key="item.key" class="strip-chip" :class="item.key.toLowerCase()">
        {{ item.label }} <b>{{ item.count }}</b>
      </span>
      <span v-if="!totalActiveAlerts" class="strip-empty">当前无未确认预警</span>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  devices: { type: Array, default: () => [] },
  states: { type: Object, default: () => ({}) },
  history: { type: Object, default: () => ({}) },
  alerts: { type: Array, default: () => [] },
  taskSummary: { type: Object, default: () => ({ running: 0, paused: 0, failed: 0 }) },
  tasks: { type: Array, default: () => [] },
  selectedKey: { type: String, default: '' }
})

const emit = defineEmits(['select'])

function batteryPercent(raw) {
  const value = Number(raw)
  if (!Number.isFinite(value)) return null
  return Math.round(value <= 1 ? value * 100 : value)
}

const selectedDevice = computed(() => props.devices.find(device => device.deviceKey === props.selectedKey))
const selectedName = computed(() => selectedDevice.value?.name || props.selectedKey || '未选择设备')
const selectedHistory = computed(() => props.history[props.selectedKey] || [])

const kpis = computed(() => {
  const enabled = props.devices.filter(device => device.enabled !== false)
  const online = enabled.filter(device => props.states[device.deviceKey]?.bridgeConnected).length
  const batteries = enabled
    .map(device => batteryPercent(props.states[device.deviceKey]?.telemetry?.battery))
    .filter(value => value !== null)
  const active = props.alerts.filter(alert => !alert.acked)
  return {
    total: enabled.length,
    online,
    running: Number(props.taskSummary?.running) || 0,
    paused: Number(props.taskSummary?.paused) || 0,
    failed: Number(props.taskSummary?.failed) || 0,
    alerts: active.length,
    critical: active.filter(alert => alert.severity === 'CRITICAL').length,
    high: active.filter(alert => alert.severity === 'HIGH').length,
    avgBattery: batteries.length
      ? Math.round(batteries.reduce((sum, value) => sum + value, 0) / batteries.length)
      : null
  }
})

const onlineRatio = computed(() => `${kpis.value.total ? Math.round((kpis.value.online / kpis.value.total) * 100) : 0}%`)

const selectedBatteryNow = computed(() => {
  const list = selectedHistory.value
  for (let index = list.length - 1; index >= 0; index -= 1) {
    if (list[index].battery !== null) return list[index].battery
  }
  return null
})

const lastSpeed = computed(() => {
  const list = selectedHistory.value
  for (let index = list.length - 1; index >= 0; index -= 1) {
    if (list[index].speed !== null) return list[index].speed
  }
  return null
})

function buildSpark(values, width = 280, height = 56) {
  const usable = values.filter(value => Number.isFinite(value))
  if (usable.length < 2) return null
  const min = Math.min(...usable)
  const max = Math.max(...usable)
  const span = max - min || 1
  const stepX = width / (values.length - 1)
  const points = []
  values.forEach((value, index) => {
    if (!Number.isFinite(value)) return
    const x = index * stepX
    const y = height - ((value - min) / span) * (height - 10) - 4
    points.push({ x, y })
  })
  if (points.length < 2) return null
  const line = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' ')
  const area = `${line} L${points[points.length - 1].x.toFixed(1)} ${height} L${points[0].x.toFixed(1)} ${height} Z`
  return { line, area }
}

const batterySpark = computed(() => buildSpark(selectedHistory.value.slice(-60).map(item => item.battery)))
const speedSpark = computed(() => buildSpark(selectedHistory.value.slice(-60).map(item => item.speed)))

const TASK_LABELS = {
  RUNNING: '执行中',
  PAUSED: '已暂停',
  DONE: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消'
}

const taskBuckets = computed(() => {
  const counts = new Map()
  props.tasks.forEach((task) => {
    const key = String(task?.status || 'UNKNOWN').toUpperCase()
    counts.set(key, (counts.get(key) || 0) + 1)
  })
  const total = props.tasks.length || 1
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({
      key,
      count,
      label: TASK_LABELS[key] || key,
      percent: Math.round((count / total) * 100)
    }))
})

const batteryDevices = computed(() => props.devices
  .filter(device => device.enabled !== false)
  .map((device) => {
    const battery = batteryPercent(props.states[device.deviceKey]?.telemetry?.battery)
    return battery === null ? null : {
      key: device.deviceKey,
      name: device.name || device.deviceKey,
      battery,
      level: battery < 15 ? 'danger' : battery < 30 ? 'warn' : 'good'
    }
  })
  .filter(Boolean)
  .sort((a, b) => a.battery - b.battery))

const activeAlerts = computed(() => props.alerts.filter(alert => !alert.acked))
const totalActiveAlerts = computed(() => activeAlerts.value.length)

const alertBuckets = computed(() => {
  const defs = [
    { key: 'CRITICAL', label: '严重' },
    { key: 'HIGH', label: '高' },
    { key: 'WARN', label: '警告' },
    { key: 'INFO', label: '提示' }
  ]
  return defs.map(item => ({
    ...item,
    count: activeAlerts.value.filter(alert => alert.severity === item.key).length
  }))
})
</script>

<style scoped>
.metrics {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-3);
  padding: var(--ds-card-padding, var(--ds-space-4));
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
  min-width: 0;
}

.metrics-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ds-space-2);
}

.metrics-eyebrow {
  margin: 0 0 2px;
  color: var(--ds-color-muted);
  font-size: 10px;
  letter-spacing: 0.12em;
}

.metrics-head h3 {
  margin: 0;
  font-size: var(--ds-font-md);
}

.metrics-note {
  color: var(--ds-color-muted);
  font-size: 10px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--ds-space-2);
}

.kpi {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
}

.kpi-label {
  color: var(--ds-color-muted);
  font-size: 10px;
}

.kpi strong {
  font-size: 22px;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.kpi strong small {
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  font-weight: 400;
}

.kpi strong.warn {
  color: #f0c260;
}

.kpi-track {
  height: 4px;
  border-radius: var(--ds-radius-pill);
  background: rgba(120, 140, 160, 0.16);
  overflow: hidden;
}

.kpi-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--ds-color-primary);
  transition: width var(--ds-duration-base) ease;
}

.kpi-foot {
  color: var(--ds-color-muted);
  font-size: 10px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--ds-space-2);
}

.chart-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  min-width: 0;
}

.chart-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.chart-head h4 {
  margin: 0;
  overflow: hidden;
  font-size: var(--ds-font-xs);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chart-head span {
  flex-shrink: 0;
  color: var(--ds-color-muted);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.spark {
  width: 100%;
  height: 70px;
}

.chart-empty {
  margin: 0;
  padding: 18px 0;
  color: var(--ds-color-muted);
  font-size: 10px;
  text-align: center;
}

.bucket-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.bucket {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
}

.bucket-label {
  width: 58px;
  flex-shrink: 0;
  overflow: hidden;
  color: var(--ds-color-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bucket-label.link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ds-color-primary);
  text-align: left;
  cursor: pointer;
}

.bucket-track {
  flex: 1;
  height: 4px;
  border-radius: var(--ds-radius-pill);
  background: rgba(120, 140, 160, 0.16);
  overflow: hidden;
}

.bucket-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--ds-color-primary);
}

.bucket-track span.good,
.bucket-track span.done { background: #3abe84; }
.bucket-track span.warn,
.bucket-track span.paused { background: #e3a008; }
.bucket-track span.danger,
.bucket-track span.failed { background: #e0646e; }
.bucket-track span.running { background: #5b8cff; }
.bucket-track span.cancelled { background: #6b7c8d; }

.bucket-value {
  width: 32px;
  flex-shrink: 0;
  color: var(--ds-color-text);
  font-family: var(--ds-font-mono);
  font-size: 10px;
  text-align: right;
}

.alert-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding-top: var(--ds-space-2);
  border-top: 1px solid var(--ds-color-border);
}

.strip-title {
  color: var(--ds-color-muted);
  font-size: 10px;
}

.strip-chip {
  padding: 2px 8px;
  border-radius: var(--ds-radius-pill);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-muted);
  font-size: 10px;
}

.strip-chip b {
  color: var(--ds-color-text);
}

.strip-chip.critical b { color: #ff9aa4; }
.strip-chip.high b { color: #f0c260; }
.strip-chip.warn b { color: #d9b96d; }

.strip-empty {
  color: var(--ds-color-muted);
  font-size: 10px;
}
</style>
