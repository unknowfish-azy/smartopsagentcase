<template>
  <section class="bento-dashboard" aria-label="工作仪表盘">
    <!-- 加载骨架：只占位不造数 -->
    <template v-if="loading">
      <div class="bento-briefing ops-card">
        <span class="ui-skeleton ui-skeleton--title" />
        <span class="ui-skeleton ui-skeleton--text" style="width: 72%" />
      </div>
      <div class="bento-kpi">
        <article v-for="n in 4" :key="n" class="ops-card">
          <span class="ui-skeleton ui-skeleton--text" style="width: 42%" />
          <span class="ui-skeleton" style="height: 34px; margin-top: 12px" />
          <span class="ui-skeleton ui-skeleton--text" style="width: 64%" />
        </article>
      </div>
      <div class="bento-main">
        <article class="ops-card bento-alerts"><span class="ui-skeleton ui-skeleton--block" /></article>
        <article class="ops-card bento-actions"><span class="ui-skeleton ui-skeleton--block" /></article>
      </div>
    </template>

    <template v-else>
      <!-- AI 情境简报：只基于真实巡检摘要与最近事件 -->
      <header class="bento-briefing ops-card">
        <div class="briefing-avatar" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M12 2a5 5 0 0 0-5 5v4H5a1 1 0 0 0 0 2h2v2a5 5 0 0 0 10 0v-2h2a1 1 0 1 0 0-2h-2V7a5 5 0 0 0-5-5Z" /><circle cx="10" cy="7" r=".8" fill="currentColor" /><circle cx="14" cy="7" r=".8" fill="currentColor" /></svg>
        </div>
        <div class="briefing-content">
          <span class="briefing-label">Agent 巡检简报 · {{ briefingTime }}</span>
          <p class="briefing-text">{{ briefingText }}</p>
        </div>
      </header>

      <!-- KPI 带（态势总览）：服务器 / 活跃告警 / 知识库 / Agent 巡检 -->
      <div class="bento-kpi bento-status ml-stagger-cols-4">
        <article v-for="kpi in kpis" :key="kpi.key" class="ops-card ops-card--interactive kpi-card">
          <header class="kpi-head">
            <span class="u-overline">{{ kpi.label }}</span>
            <span class="ui-tag ui-tag--sm" :class="`ui-tag--${kpi.tone}`">{{ kpi.pill }}</span>
          </header>
          <strong class="ops-kpi__value u-num"><KpiNumber :value="kpi.value" /></strong>
          <small class="u-caption">{{ kpi.sub }}</small>
        </article>
      </div>

      <div class="bento-main">
        <!-- 告警流（活动流） -->
        <article class="ops-card bento-alerts bento-activity">
          <header class="ops-card__head">
            <div class="ops-card__titles">
              <span class="u-overline">ALERT STREAM</span>
              <h3 class="u-section">活跃告警</h3>
            </div>
            <RouterLink class="bento-more" to="/sentinel/alerts">打开告警中心 →</RouterLink>
          </header>
          <p v-if="sentinelNote" class="bento-note">{{ sentinelNote }}</p>
          <p v-else-if="activeAlerts.length === 0" class="bento-note">当前没有待处理告警，最近一次巡检结果见右侧图表。</p>
          <ol v-else class="alert-stream ml-stagger">
            <li v-for="alert in activeAlerts.slice(0, 5)" :key="alert.id" class="alert-row">
              <span class="ui-tag ui-tag--sm" :class="`ui-tag--${severityTone(alert.severity)}`">{{ alert.severity || 'P3' }}</span>
              <div class="alert-body">
                <strong>{{ alert.title || '未命名告警' }}</strong>
                <span class="u-caption">{{ alert.metric || '指标' }} = {{ alert.observedValue ?? '—' }}（阈值 {{ alert.thresholdValue ?? '—' }}）</span>
              </div>
              <span class="ui-tag ui-tag--sm ui-tag--neutral">{{ statusLabel(alert.status) }}</span>
              <time class="alert-time u-caption">{{ alert.firedAt || '—' }}</time>
            </li>
          </ol>
        </article>

        <!-- 小鱼面板（快捷对话 + RAG/训练状态 + 快捷入口） -->
        <XiaoyuDashboardCard class="bento-xiaoyu" />
      </div>

      <!-- 图表：巡检结果分布 + 近 7 日事件 -->
      <div class="bento-charts">
        <article class="ops-card bento-distribution">
          <header class="ops-card__head">
            <div class="ops-card__titles">
              <span class="u-overline">INSPECTOR · DISTRIBUTION</span>
              <h3 class="u-section">巡检结果分布</h3>
            </div>
            <span class="u-caption">来源：/api/inspector/summary</span>
          </header>
          <p v-if="!summary" class="bento-note">巡检摘要不可用（未登录或后端未接入），暂无分布数据。</p>
          <OpsChart
            v-else
            title="巡检结果分布"
            type="bar"
            :labels="distribution.labels"
            :series="distribution.series"
            :colors="distribution.colors"
            unit="次"
            :height="200"
          />
        </article>

        <article class="ops-card bento-trend">
          <header class="ops-card__head">
            <div class="ops-card__titles">
              <span class="u-overline">INSPECTOR · EVENTS</span>
              <h3 class="u-section">近 7 日事件</h3>
            </div>
            <span class="u-caption">最近 {{ events.length }} 条真实事件</span>
          </header>
          <p v-if="events.length === 0" class="bento-note">暂无巡检事件，无法生成趋势。</p>
          <OpsChart
            v-else
            title="近 7 日巡检事件"
            type="line"
            :labels="trend.labels"
            :series="trend.series"
            unit="条"
            :height="200"
          />
        </article>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, defineAsyncComponent, onMounted, reactive, ref } from 'vue'
import { getInspectorEvents, getInspectorSummary } from '../../api/inspector'
import { getServers } from '../../api/server'
import { listKnowledgeLibraries } from '../../api/personalKnowledge.ts'
import { loadSentinel, sentinelState } from '../../views/sentinel/sentinelStore.js'
import { ALERT_STATUSES } from '../../views/sentinel/sentinelModel.js'
import OpsChart from './OpsChart.vue'
import KpiNumber from './KpiNumber.vue'
const XiaoyuDashboardCard = defineAsyncComponent(() => import('./XiaoyuDashboardCard.vue'))

/* 全部数据来自真实接口；任一来源失败即标记失败并显示「—」，绝不回填看起来像真的假数据。 */
const ACTIVE_ALERT_STATUSES = new Set(['OPEN', 'PENDING_APPROVAL', 'REMEDIATING'])
const SEVERITY_ORDER = { P0: 0, P1: 1, P2: 2, P3: 3 }

const loading = ref(true)
const failures = reactive({ servers: false, knowledge: false })
const servers = ref([])
const libraries = ref([])
const summary = ref(null)
const events = ref([])

const num = value => Number(value ?? 0) || 0

const serverStats = computed(() => {
  if (failures.servers) return null
  const status = item => String(item?.status || '').toUpperCase()
  return {
    total: servers.value.length,
    online: servers.value.filter(item => status(item) === 'ONLINE').length,
    warning: servers.value.filter(item => status(item) === 'WARNING').length
  }
})

const activeAlerts = computed(() => {
  if (sentinelState.status !== 'ready') return []
  return sentinelState.alerts
    .filter(alert => ACTIVE_ALERT_STATUSES.has(String(alert?.status || '').toUpperCase()))
    .sort((a, b) => (SEVERITY_ORDER[a?.severity] ?? 9) - (SEVERITY_ORDER[b?.severity] ?? 9))
})

const sentinelNote = computed(() => {
  if (sentinelState.status === 'ready') return ''
  if (sentinelState.status === 'unauthorized') return '未登录，哨兵告警暂不可用。'
  if (sentinelState.status === 'unavailable') return sentinelState.reason || '哨兵接口不可用。'
  return '正在读取哨兵告警…'
})

const kpis = computed(() => {
  const server = serverStats.value
  const alertCount = sentinelState.status === 'ready' ? activeAlerts.value.length : null
  const inspector = summary.value
  const abnormal = inspector ? num(inspector.warning) + num(inspector.high) + num(inspector.critical) : 0
  return [
    {
      key: 'servers',
      label: '服务器',
      value: server ? String(server.total) : '—',
      sub: server ? `${server.online} 在线 · ${server.warning} 异常` : '服务器接口不可用',
      tone: server && server.warning ? 'warning' : 'neutral',
      pill: server && server.warning ? 'ATTENTION' : 'INVENTORY'
    },
    {
      key: 'alerts',
      label: '活跃告警',
      value: alertCount === null ? '—' : String(alertCount),
      sub: alertCount === null ? '哨兵数据不可用' : alertCount ? '待处理 / 待审批 / 处置中' : '当前无活跃告警',
      tone: alertCount === null ? 'neutral' : alertCount ? 'warning' : 'success',
      pill: alertCount === null ? 'OFFLINE' : alertCount ? 'ACTION' : 'CLEAR'
    },
    {
      key: 'knowledge',
      label: '知识库',
      value: failures.knowledge ? '—' : String(libraries.value.length),
      sub: failures.knowledge ? '知识接口不可用' : '个人知识库',
      tone: 'neutral',
      pill: 'KNOWLEDGE'
    },
    {
      key: 'inspector',
      label: 'Agent 巡检',
      value: inspector ? String(num(inspector.total)) : '—',
      sub: inspector ? `${num(inspector.pass)} 通过 · ${abnormal} 异常` : '巡检接口不可用',
      tone: inspector && abnormal ? 'warning' : 'neutral',
      pill: inspector ? 'INSPECTOR' : 'OFFLINE'
    }
  ]
})

const distribution = computed(() => {
  const source = summary.value
  return {
    labels: ['通过', '警告', '高危', '严重'],
    series: [{ name: '巡检结果', data: source ? [num(source.pass), num(source.warning), num(source.high), num(source.critical)] : [0, 0, 0, 0] }],
    colors: ['--ds-chart-3', '--ds-chart-4', '--ds-chart-5', '--ds-chart-5']
  }
})

const trend = computed(() => {
  const days = []
  const now = new Date()
  for (let offset = 6; offset >= 0; offset -= 1) {
    const day = new Date(now)
    day.setDate(now.getDate() - offset)
    const key = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
    days.push({ key, label: key.slice(5) })
  }
  const counts = new Map(days.map(day => [day.key, 0]))
  events.value.forEach(event => {
    const key = String(event?.createdAt || '').slice(0, 10)
    if (counts.has(key)) counts.set(key, counts.get(key) + 1)
  })
  return {
    labels: days.map(day => day.label),
    series: [{ name: '事件数', data: days.map(day => counts.get(day.key)) }]
  }
})

const briefingTime = computed(() => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }))

const briefingText = computed(() => {
  const source = summary.value
  if (!source) return '巡检接口不可用（未登录或后端未接入），暂无 Agent 简报。'
  const parts = []
  const total = num(source.total)
  if (total > 0) {
    parts.push(`累计 ${total} 次核查：${num(source.pass)} 通过，${num(source.warning)} 警告`)
    if (num(source.high)) parts.push(`${num(source.high)} 高危`)
    if (num(source.critical)) parts.push(`${num(source.critical)} 严重`)
  }
  const latest = events.value[0]
  if (latest) {
    parts.push(`最新事件：[${latest.severity || 'INFO'}] ${String(latest.reason || latest.category || latest.taskId || '').slice(0, 60)}`)
  }
  return parts.join('；') || '暂无巡检记录，一切平静。'
})

const severityTone = severity => {
  const level = String(severity || '').toUpperCase()
  return level === 'P0' || level === 'P1' ? 'danger' : level === 'P2' ? 'warning' : 'neutral'
}
const statusLabel = id => ALERT_STATUSES.find(item => item.id === id)?.label ?? id ?? '—'

async function load() {
  loading.value = true
  await Promise.allSettled([
    getServers()
      .then(response => { servers.value = Array.isArray(response?.data) ? response.data : (response?.data?.items || []) })
      .catch(() => { failures.servers = true }),
    listKnowledgeLibraries()
      .then(response => { const data = response?.data; libraries.value = Array.isArray(data) ? data : (data?.items || []) })
      .catch(() => { failures.knowledge = true }),
    getInspectorSummary()
      .then(response => { summary.value = response?.data || null })
      .catch(() => { summary.value = null }),
    getInspectorEvents(100)
      .then(response => { events.value = Array.isArray(response?.data) ? response.data : [] })
      .catch(() => { events.value = [] }),
    loadSentinel()
  ])
  loading.value = false
}

onMounted(load)
</script>

<style scoped>
.bento-dashboard {
  display: grid;
  gap: var(--ds-grid-gutter, 24px);
  padding: var(--ds-space-6, 24px);
  background: var(--ds-surface-base);
  min-height: calc(100dvh - 112px);
  grid-template-columns: repeat(12, 1fr);
  align-content: start;
}

.bento-briefing { grid-column: 1 / -1; flex-direction: row; align-items: flex-start; gap: 14px; }
.briefing-avatar {
  flex-shrink: 0; width: 32px; height: 32px; display: grid; place-content: center;
  color: var(--ds-color-primary);
  background: var(--ds-pill-info-bg);
  border-radius: 8px;
}
.briefing-content { min-width: 0; }
.briefing-label { display: block; font: 10px var(--ds-font-mono); color: var(--ds-color-muted); letter-spacing: .1em; }
.briefing-text { margin: 4px 0 0; font-size: var(--ds-type-body-caption-size); line-height: var(--ds-line-height-base); color: var(--ds-color-text); }

.bento-kpi, .bento-main, .bento-charts { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(12, 1fr); gap: var(--ds-grid-gutter, 24px); }
.kpi-card { grid-column: span 3; gap: 8px; }
.kpi-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.kpi-card .ops-kpi__value { color: var(--ds-color-text); }

.bento-alerts { grid-column: span 6; }
.bento-xiaoyu { grid-column: span 6; }
.bento-distribution { grid-column: span 7; }
.bento-trend { grid-column: span 5; }

.bento-more { margin-left: auto; padding: 4px 0; color: var(--ds-color-primary); font-size: var(--ds-type-caption-size); white-space: nowrap; }
.bento-more:hover { color: var(--ds-color-primary-strong); }
.bento-note { margin: 4px 0; color: var(--ds-color-muted); font-size: var(--ds-type-body-caption-size); line-height: var(--ds-line-height-base); }

.alert-stream { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }
.alert-row {
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; align-items: center; gap: 10px;
  padding: 10px 12px; border-radius: var(--ds-radius-md);
  background: color-mix(in srgb, var(--ds-color-text) 3%, var(--ds-surface-raised));
  transition: background var(--ds-motion-duration) var(--ds-ease-out);
}
.alert-row:hover { background: color-mix(in srgb, var(--ds-color-primary) 7%, var(--ds-surface-raised)); }
.alert-body { display: grid; gap: 2px; min-width: 0; }
.alert-body strong { color: var(--ds-color-text); font-size: var(--ds-type-body-caption-size); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alert-time { font-family: var(--ds-font-mono); white-space: nowrap; }

.quick-grid { display: grid; gap: 8px; }
.quick-link {
  display: grid; gap: 2px; padding: 10px 12px;
  border: 1px solid var(--ds-hairline); border-radius: var(--ds-radius-md);
  background: transparent; transition: border-color var(--ds-motion-duration) var(--ds-ease-out), background var(--ds-motion-duration) var(--ds-ease-out);
}
.quick-link strong { color: var(--ds-color-text); font-size: var(--ds-type-body-size); font-weight: 500; }
.quick-link:hover { border-color: var(--ds-color-border); background: color-mix(in srgb, var(--ds-color-primary) 6%, transparent); }

@media (max-width: 1024px) {
  .kpi-card { grid-column: span 6; }
  .bento-alerts, .bento-actions, .bento-distribution, .bento-trend { grid-column: span 12; }
}
@media (max-width: 640px) {
  .bento-dashboard { padding: var(--ds-space-4); gap: var(--ds-space-4); }
  .kpi-card { grid-column: span 12; }
  .alert-row { grid-template-columns: auto minmax(0, 1fr); }
  .alert-row .ui-tag--neutral, .alert-time { grid-column: 2; justify-self: start; }
}
@media (prefers-reduced-motion: reduce) {
  .alert-row, .quick-link { transition: none; }
}
</style>
