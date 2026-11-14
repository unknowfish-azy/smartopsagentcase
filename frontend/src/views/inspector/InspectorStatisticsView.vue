<template>
  <div class="statistics-page">
    <header class="statistics-head">
      <div>
        <p class="eyebrow">MEMORY · INSPECTOR STATISTICS</p>
        <h1>Inspector Statistics</h1>
        <p class="lede">仅展示数据库中的真实纠察数据；无统计时不生成示意数值。</p>
      </div>
      <div class="statistics-head__actions">
        <span class="status-chip" :class="`status-chip--${status}`">{{ statusLabel }}</span>
        <button type="button" class="ghost-button" :disabled="status === 'loading'" @click="load">刷新</button>
        <RouterLink class="ghost-button" to="/inspector">返回中心</RouterLink>
        <RouterLink class="ghost-button" to="/inspector/desk?view=stats&window=24h">在洞察台打开</RouterLink>
      </div>
    </header>

    <p v-if="status === 'unavailable'" class="state-banner state-banner--warn">
      统计接口不可用（未登录或后端未接入）。如需预览可视化，可在洞察台点击「查看演示数据」。
    </p>
    <p v-else-if="status === 'empty'" class="state-banner">
      已连接，暂无统计与事件样本。图表区保留空态占位，等待后端写入数据。
    </p>

    <InspectorSummary :summary="data.summary || {}" />

    <div class="chart-grid">
      <section class="chart-card">
        <h2>等级分布</h2>
        <div class="donut-row">
          <svg class="donut" viewBox="0 0 120 120" role="img" aria-label="纠察等级分布">
            <circle cx="60" cy="60" r="42" fill="none" stroke="var(--ds-color-border, rgba(159,190,207,.18))" stroke-width="14" />
            <circle
              v-for="slice in donutSlices"
              :key="slice.key"
              cx="60" cy="60" r="42" fill="none"
              :stroke="slice.color"
              stroke-width="14"
              :stroke-dasharray="slice.dash"
              :stroke-dashoffset="slice.offset"
              transform="rotate(-90 60 60)"
            />
            <text x="60" y="57" text-anchor="middle" class="donut__value">{{ donutTotal || '—' }}</text>
            <text x="60" y="75" text-anchor="middle" class="donut__label">总纠察</text>
          </svg>
          <ul class="donut-legend">
            <li v-for="slice in donutSlices" :key="slice.key">
              <i :style="{ background: slice.color }" aria-hidden="true"></i>
              <span>{{ slice.label }}</span>
              <strong>{{ slice.value }}</strong>
            </li>
            <li v-if="!donutTotal" class="donut-legend__empty">暂无等级统计</li>
          </ul>
        </div>
      </section>

      <section class="chart-card">
        <h2>按纠察维度 · By Category</h2>
        <OpsChart
          v-if="categoryLabels.length"
          title="按纠察维度分布"
          type="bar"
          :labels="categoryLabels"
          :series="categorySeries"
          :height="196"
          unit="条"
        />
        <AppEmpty v-else description="暂无分类统计" />
      </section>

      <section class="chart-card">
        <h2>按目标 · By Target</h2>
        <OpsChart
          v-if="targetLabels.length"
          title="按目标分布"
          type="bar"
          :labels="targetLabels"
          :series="targetSeries"
          :height="196"
          unit="条"
        />
        <AppEmpty v-else description="暂无目标统计" />
      </section>

      <section class="chart-card">
        <h2>近 7 日事件趋势</h2>
        <OpsChart
          v-if="hasTrend"
          title="近 7 日纠察事件"
          type="line"
          :labels="trend.labels"
          :series="trendSeries"
          :height="196"
          unit="条"
        />
        <AppEmpty v-else description="暂无事件样本，无法生成趋势" />
      </section>
    </div>
  </div>
</template>

<script setup>
/**
 * 统计页 · P1 图表化
 *
 *  - 纯文字 <p> 列表 → OpsChart 柱状/折线（复用既有 ECharts 封装，自带 motionQuery 降级与数据表）；
 *  - 新增等级分布环（纯 SVG，无新增依赖）与近 7 日趋势（前端按事件真实时间分箱，不造数）；
 *  - 三态 ready / empty / unavailable 与中心页口径一致；
 *  - category 用 dimensions.js 的共享别名映射成中文，保证三页口径一致；
 *  - 深链带 view=stats&window=24h，与洞察台共用同一条证据链。
 */
import { computed, onMounted, ref } from 'vue'
import { getInspectorEvents, getInspectorStatistics } from '../../api/inspector'
import { DIMENSIONS, toEventTimestamp } from '../../components/inspector/dimensions'
import InspectorSummary from '../../components/inspector/InspectorSummary.vue'
import OpsChart from '../../components/dashboard/OpsChart.vue'
import AppEmpty from '../../components/common/AppEmpty.vue'

const data = ref({})
const events = ref([])
const status = ref('loading')

const STATUS_LABELS = {
  loading: '连接中',
  ready: '实时数据',
  empty: '已连接 · 暂无统计',
  unavailable: '接口不可用'
}
const statusLabel = computed(() => STATUS_LABELS[status.value] || '—')

const SEVERITY_DEFS = [
  { key: 'pass', label: 'PASS', color: '#3fb950' },
  { key: 'warning', label: 'WARN', color: '#d29922' },
  { key: 'high', label: 'HIGH', color: '#e08a3c' },
  { key: 'critical', label: 'CRITICAL', color: '#f85149' }
]
const CIRCUMFERENCE = 2 * Math.PI * 42

const donutTotal = computed(() => SEVERITY_DEFS.reduce(
  (total, item) => total + (Number(data.value.summary?.[item.key]) || 0), 0
))

const donutSlices = computed(() => {
  let accumulated = 0
  return SEVERITY_DEFS.map(item => {
    const value = Number(data.value.summary?.[item.key]) || 0
    const fraction = donutTotal.value ? value / donutTotal.value : 0
    const slice = {
      ...item,
      value,
      dash: `${fraction * CIRCUMFERENCE} ${CIRCUMFERENCE}`,
      offset: -accumulated * CIRCUMFERENCE
    }
    accumulated += fraction
    return slice
  })
})

function categoryLabel(raw) {
  const key = String(raw || '').toUpperCase()
  const found = DIMENSIONS.find(item => item.aliases.includes(key))
  return found ? found.cn : (String(raw || '未分类').slice(0, 12))
}

function topItems(list, limit = 8) {
  return Array.isArray(list)
    ? list.filter(item => item && item.count != null).slice(0, limit)
    : []
}

const categoryItems = computed(() => topItems(data.value.byCategory))
const targetItems = computed(() => topItems(data.value.byTarget))
const categoryLabels = computed(() => categoryItems.value.map(item => categoryLabel(item.category)))
const targetLabels = computed(() => targetItems.value.map(item => String(item.target || '未知').slice(0, 12)))
const categorySeries = computed(() => [{ name: '纠察数', data: categoryItems.value.map(item => Number(item.count) || 0) }])
const targetSeries = computed(() => [{ name: '纠察数', data: targetItems.value.map(item => Number(item.count) || 0) }])

const trend = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = []
  for (let offset = 6; offset >= 0; offset -= 1) {
    const day = new Date(today.getTime() - offset * 86400000)
    days.push({ start: day.getTime(), label: `${day.getMonth() + 1}/${day.getDate()}` })
  }
  const counts = days.map(() => 0)
  events.value.forEach(event => {
    const stamp = toEventTimestamp(event)
    if (!stamp) return
    for (let index = 0; index < days.length; index += 1) {
      if (stamp >= days[index].start && stamp < days[index].start + 86400000) {
        counts[index] += 1
        break
      }
    }
  })
  return { labels: days.map(day => day.label), counts }
})
const hasTrend = computed(() => trend.value.counts.some(count => count > 0))
const trendSeries = computed(() => [{ name: '纠察事件', data: trend.value.counts }])

async function load() {
  status.value = 'loading'
  const [statsResult, eventsResult] = await Promise.allSettled([
    getInspectorStatistics(),
    getInspectorEvents(200)
  ])
  data.value = statsResult.status === 'fulfilled' ? (statsResult.value?.data || {}) : {}
  events.value = eventsResult.status === 'fulfilled' && Array.isArray(eventsResult.value?.data)
    ? eventsResult.value.data
    : []

  const hasStats = categoryItems.value.length > 0 || targetItems.value.length > 0 || donutTotal.value > 0
  const hasEvents = events.value.length > 0
  if (statsResult.status === 'rejected' && !hasEvents) status.value = 'unavailable'
  else status.value = (hasStats || hasEvents) ? 'ready' : 'empty'
}

onMounted(load)
</script>

<style scoped>
.statistics-page {
  display: grid;
  gap: 18px;
  padding: 22px;
  color: var(--ds-color-text, #e8f2f7);
  background: var(--ds-color-surface, #071018);
  border: 1px solid var(--ds-hairline, rgba(159, 190, 207, .18));
  border-radius: 12px;
}
.statistics-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 16px; }
.eyebrow { margin: 0 0 6px; color: var(--ds-color-primary-strong, #7ad7f5); font: 11px var(--font-mono, ui-monospace, monospace); letter-spacing: .1em; }
.statistics-head h1 { margin: 0; font-size: var(--ds-type-h1-size, 28px); font-weight: var(--ds-type-h1-weight, 500); }
.lede { margin: 6px 0 0; color: var(--ds-color-muted, #92a6b5); font-size: 13px; }
.statistics-head__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.status-chip { padding: 4px 10px; border: 1px solid var(--ds-color-border, rgba(159, 190, 207, .18)); border-radius: 999px; color: var(--ds-color-muted, #92a6b5); font: 11px var(--font-mono, ui-monospace, monospace); }
.status-chip--ready { color: var(--ds-semantic-success, #3fb950); border-color: var(--ds-semantic-success, #3fb950); }
.status-chip--unavailable { color: var(--ds-semantic-danger, #f85149); border-color: var(--ds-semantic-danger, #f85149); }
.ghost-button {
  display: inline-flex; align-items: center; min-height: 32px; padding: 6px 12px;
  border: 1px solid var(--ds-color-border, rgba(159, 190, 207, .18)); border-radius: 7px;
  background: var(--ds-surface-raised, #151a21); color: var(--ds-color-text, #e8f2f7);
  font-size: 12px; text-decoration: none; cursor: pointer;
  transition: border-color var(--ds-duration-micro, 150ms) ease, color var(--ds-duration-micro, 150ms) ease;
}
.ghost-button:hover { border-color: var(--ds-color-primary, #2496ed); color: var(--ds-color-primary-strong, #7ad7f5); }
.ghost-button:disabled { opacity: .5; cursor: not-allowed; }
.state-banner { margin: 0; padding: 10px 14px; border: 1px solid var(--ds-hairline, rgba(159, 190, 207, .18)); border-radius: 8px; background: var(--ds-surface-raised, #151a21); color: var(--ds-color-muted, #92a6b5); font-size: 12px; line-height: 1.6; }
.state-banner--warn { border-color: var(--ds-semantic-danger, #f85149); color: var(--ds-color-text, #e8f2f7); }
.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.chart-card { min-width: 0; display: grid; gap: 10px; padding: 16px; border: 1px solid var(--ds-hairline, rgba(159, 190, 207, .18)); border-radius: 10px; background: var(--ds-surface-raised, #151a21); }
.chart-card h2 { margin: 0; font-size: var(--ds-type-h3-size, 18px); font-weight: var(--ds-type-h3-weight, 500); }
.donut-row { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
.donut { width: 132px; height: 132px; flex: none; }
.donut__value { fill: var(--ds-color-text, #e8f2f7); font: 300 22px var(--font-mono, ui-monospace, monospace); }
.donut__label { fill: var(--ds-color-muted, #92a6b5); font-size: 10px; }
.donut-legend { list-style: none; display: grid; gap: 8px; margin: 0; padding: 0; min-width: 130px; }
.donut-legend li { display: grid; grid-template-columns: 8px 1fr auto; align-items: center; gap: 8px; font-size: 12px; }
.donut-legend i { width: 8px; height: 8px; border-radius: 50%; }
.donut-legend span { color: var(--ds-color-muted, #92a6b5); font: 11px var(--font-mono, ui-monospace, monospace); }
.donut-legend strong { font-variant-numeric: var(--ds-type-num, tabular-nums); }
.donut-legend__empty { grid-template-columns: 1fr; color: var(--ds-color-muted, #92a6b5); }
.chart-card :deep(.empty) { padding: 28px; }
@media (max-width: 1023px) { .chart-grid { grid-template-columns: 1fr; } }
@media (max-width: 767px) { .statistics-page { padding: 16px; } }
@media (prefers-reduced-motion: reduce) { .ghost-button { transition: none; } }
</style>
