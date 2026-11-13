<template>
  <section class="insights-page">
    <header class="page-header insights-header">
      <p class="editorial-label">NATURAL LANGUAGE INSIGHTS</p>
      <h1 class="u-h1">自然语言洞察</h1>
      <p class="u-body-caption">用一句话提问，系统在真实接口数据上做规则匹配与聚合。图表标注数据来源；接口不可用时明确显示「不可用」，不做任何补数。</p>
    </header>

    <form class="insights-query" role="search" @submit.prevent="analyze">
      <input
        v-model="query"
        type="text"
        maxlength="120"
        aria-label="输入运维问题"
        placeholder="例如：现在的告警级别分布怎么样？"
        :disabled="loading"
      />
      <button type="submit" :disabled="loading || !query.trim()">{{ loading ? '分析中…' : '分析' }}</button>
    </form>

    <div class="insights-examples" aria-label="示例问题">
      <span class="u-overline">示例</span>
      <button v-for="example in examples" :key="example" type="button" :disabled="loading" @click="askExample(example)">{{ example }}</button>
    </div>

    <div class="insights-result" aria-live="polite">
      <div v-if="loading" class="ops-card">
        <span class="ui-skeleton ui-skeleton--title" />
        <span class="ui-skeleton ui-skeleton--block" />
      </div>

      <article v-else-if="result" class="ops-card insights-card">
        <header class="ops-card__head">
          <div class="ops-card__titles">
            <span class="u-overline">RESULT · {{ result.badge }}</span>
            <h2 class="u-h3">{{ result.title }}</h2>
          </div>
          <span class="ui-tag ui-tag--sm ui-tag--mono">{{ result.source }}</span>
        </header>

        <p class="u-body-caption">{{ result.description }}</p>

        <p v-if="result.kind === 'unavailable'" class="insights-note insights-note--warn" role="status">
          {{ result.note }}
        </p>

        <template v-else>
          <div v-if="result.charts?.length" class="insights-charts ml-stagger-cols-2">
            <OpsChart
              v-for="(chart, index) in result.charts"
              :key="index"
              :title="chart.title"
              :type="chart.type"
              :labels="chart.labels"
              :series="chart.series"
              :colors="chart.colors || []"
              :unit="chart.unit || ''"
              :height="220"
            />
          </div>

          <ul v-if="result.items?.length" class="insights-list ml-stagger">
            <li v-for="item in result.items" :key="item.name">
              <strong>{{ item.name }}</strong>
              <span v-if="item.desc" class="u-caption">{{ item.desc }}</span>
            </li>
          </ul>

          <p v-if="result.note" class="insights-note">{{ result.note }}</p>
        </template>

        <footer class="ops-card__foot insights-meta u-caption">
          <span>问题：{{ result.question }}</span>
          <time>{{ result.updatedAt }}</time>
        </footer>
      </article>

      <p v-else class="insights-idle u-body-caption">输入问题后，这里会显示图表与结论。可先试试上面的示例。</p>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { getInspectorEvents, getInspectorSummary } from '../../api/inspector'
import { getServers } from '../../api/server'
import { listKnowledgeLibraries } from '../../api/personalKnowledge.ts'
import { loadSentinel, sentinelState } from '../sentinel/sentinelStore.js'
import OpsChart from '../../components/dashboard/OpsChart.vue'

/* 规则匹配：只识别四类可落到真实接口的问题，不做自由生成，避免编造指标。 */
const ACTIVE_ALERT_STATUSES = new Set(['OPEN', 'PENDING_APPROVAL', 'REMEDIATING'])
const SERVER_STATUS_LABELS = { ONLINE: '在线', WARNING: '异常', OFFLINE: '离线', UNKNOWN: '未知' }
const INTENTS = [
  { id: 'alerts', test: /告警|报警|预警|故障/ },
  { id: 'servers', test: /服务器|主机|节点|在线率/ },
  { id: 'knowledge', test: /知识|文档|资料|经验/ },
  { id: 'health', test: /健康|巡检|体检|评分|状态分/ }
]
const examples = [
  '现在的告警级别分布怎么样？',
  '我的服务器在线状态如何？',
  '巡检健康情况怎么样？',
  '我有哪些个人知识库？'
]

const query = ref('')
const loading = ref(false)
const result = ref(null)

const now = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
const num = value => Number(value ?? 0) || 0
const asList = response => {
  const data = response?.data
  return Array.isArray(data) ? data : (data?.items || [])
}

function unavailable({ badge, title, source, description, note, question }) {
  return { kind: 'unavailable', badge, title, source, description, note, question, updatedAt: now() }
}

async function alertInsight(question) {
  await loadSentinel()
  const base = { badge: 'ALERTS', title: '活跃告警级别分布', source: '/api/sentinel/alerts', question }
  if (sentinelState.status !== 'ready') {
    return unavailable({
      ...base,
      description: '按级别统计当前仍在处置链路上的告警。',
      note: sentinelState.status === 'unauthorized' ? '未登录或没有哨兵权限，告警数据不可用。' : (sentinelState.reason || '哨兵接口不可用。')
    })
  }
  const active = sentinelState.alerts.filter(alert => ACTIVE_ALERT_STATUSES.has(String(alert?.status || '').toUpperCase()))
  const levels = ['P0', 'P1', 'P2', 'P3']
  return {
    kind: 'chart',
    ...base,
    description: `当前 ${active.length} 条活跃告警，按级别统计如下。`,
    charts: [{
      title: '活跃告警级别分布',
      type: 'bar',
      labels: levels,
      series: [{ name: '告警数', data: levels.map(level => active.filter(alert => alert.severity === level).length) }],
      colors: ['--ds-chart-5', '--ds-chart-5', '--ds-chart-4', '--ds-chart-neutral'],
      unit: '条'
    }],
    note: active.length ? '口径：待处理 / 待审批 / 处置中。' : '当前没有活跃告警。',
    updatedAt: now()
  }
}

async function serverInsight(question) {
  const base = { badge: 'SERVERS', title: '服务器状态分布', source: '/api/servers', question }
  let list
  try {
    list = asList(await getServers())
  } catch {
    return unavailable({ ...base, description: '统计已纳管服务器的运行状态。', note: '服务器接口不可用（未登录或后端未接入）。' })
  }
  if (!list.length) {
    return unavailable({ ...base, description: '统计已纳管服务器的运行状态。', note: '尚未纳管任何服务器，暂无可统计的数据。' })
  }
  const statuses = [...new Set(list.map(item => String(item?.status || 'UNKNOWN').toUpperCase()))]
  return {
    kind: 'chart',
    ...base,
    description: `共 ${list.length} 台服务器，按运行状态统计如下。`,
    charts: [{
      title: '服务器状态分布',
      type: 'bar',
      labels: statuses.map(status => SERVER_STATUS_LABELS[status] || status),
      series: [{ name: '服务器数', data: statuses.map(status => list.filter(item => String(item?.status || 'UNKNOWN').toUpperCase() === status).length) }],
      colors: statuses.map(status => status === 'ONLINE' ? '--ds-chart-3' : status === 'WARNING' ? '--ds-chart-4' : '--ds-chart-5'),
      unit: '台'
    }],
    updatedAt: now()
  }
}

async function knowledgeInsight(question) {
  const base = { badge: 'KNOWLEDGE', title: '个人知识库清单', source: '个人知识库接口', question }
  let list
  try {
    list = asList(await listKnowledgeLibraries())
  } catch {
    return unavailable({ ...base, description: '列出当前账号下的个人知识库。', note: '知识库接口不可用（未登录或后端未接入）。' })
  }
  return {
    kind: 'list',
    ...base,
    description: `当前共有 ${list.length} 个个人知识库。`,
    items: list.map(item => ({ name: item?.name || item?.title || `知识库 #${item?.id ?? '—'}`, desc: item?.description || '' })),
    note: list.length ? '条目数统计接口未提供，这里只展示知识库清单，不估算条目数量。' : '还没有个人知识库，可在知识库页面新建。',
    updatedAt: now()
  }
}

async function healthInsight(question) {
  const base = { badge: 'INSPECTOR', title: '巡检健康概览', source: '/api/inspector/summary', question }
  let summary
  let events = []
  try {
    const [summaryResponse, eventsResponse] = await Promise.all([getInspectorSummary(), getInspectorEvents(100).catch(() => null)])
    summary = summaryResponse?.data || null
    events = Array.isArray(eventsResponse?.data) ? eventsResponse.data : []
  } catch {
    summary = null
  }
  if (!summary || num(summary.total) <= 0) {
    return unavailable({ ...base, description: '基于巡检摘要统计通过 / 警告 / 高危 / 严重分布。', note: '暂无巡检记录或巡检接口不可用，无法给出健康概览。' })
  }
  const latest = events[0]
  return {
    kind: 'chart',
    ...base,
    description: `累计 ${num(summary.total)} 次核查：${num(summary.pass)} 通过，${num(summary.warning)} 警告，${num(summary.high)} 高危，${num(summary.critical)} 严重。`,
    charts: [{
      title: '巡检结果分布',
      type: 'bar',
      labels: ['通过', '警告', '高危', '严重'],
      series: [{ name: '次数', data: [num(summary.pass), num(summary.warning), num(summary.high), num(summary.critical)] }],
      colors: ['--ds-chart-3', '--ds-chart-4', '--ds-chart-5', '--ds-chart-5'],
      unit: '次'
    }],
    note: latest
      ? `最新事件：[${latest.severity || 'INFO'}] ${String(latest.reason || latest.category || latest.taskId || '').slice(0, 60)}（近 ${events.length} 条事件样本）`
      : '暂无巡检事件样本。',
    updatedAt: now()
  }
}

const builders = { alerts: alertInsight, servers: serverInsight, knowledge: knowledgeInsight, health: healthInsight }

async function analyze() {
  const question = query.value.trim()
  if (!question || loading.value) return
  loading.value = true
  result.value = null
  try {
    const intent = INTENTS.find(item => item.test.test(question))
    if (!intent) {
      result.value = unavailable({
        badge: 'UNRECOGNIZED',
        title: '未识别的问题类型',
        source: '规则匹配',
        description: '目前支持四类问题：告警级别、服务器状态、个人知识库、巡检健康。',
        note: '换个说法试试，例如「告警级别分布」「服务器在线状态」「巡检健康情况」「我的知识库」。',
        question,
        updatedAt: now()
      })
      return
    }
    result.value = await builders[intent.id](question)
  } finally {
    loading.value = false
  }
}

function askExample(example) {
  query.value = example
  analyze()
}
</script>

<style scoped>
.insights-page { display: grid; gap: var(--ds-space-4); padding-bottom: var(--ds-space-12); }
.insights-header { padding-bottom: var(--ds-space-4); }
.insights-header .u-body-caption { max-width: 72ch; margin: 8px 0 0; line-height: var(--ds-line-height-base); }
.insights-query { display: flex; gap: 8px; }
.insights-query input {
  flex: 1; min-width: 0; height: 40px; padding: 0 14px;
  border: 1px solid var(--ds-color-border); border-radius: var(--ds-radius-md);
  background: var(--ds-surface-raised); color: var(--ds-color-text); font-size: var(--ds-type-body-size);
}
.insights-query input::placeholder { color: var(--ds-color-muted); }
.insights-query input:focus-visible { border-color: var(--ds-color-primary); outline: 2px solid var(--ds-pill-info-bg); outline-offset: 1px; }
.insights-query button {
  height: 40px; padding: 0 18px; border: 1px solid transparent; border-radius: var(--ds-radius-md);
  background: var(--ds-color-primary); color: #ffffff; font-size: var(--ds-type-body-size); font-weight: 500;
  transition: opacity var(--ds-motion-duration) var(--ds-ease-out);
}
.insights-query button:hover:not(:disabled) { opacity: .88; }
.insights-query button:disabled { opacity: .45; cursor: not-allowed; }
.insights-examples { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.insights-examples button {
  min-height: 28px; padding: 0 10px;
  border: 1px solid var(--ds-hairline); border-radius: var(--ds-radius-pill);
  background: transparent; color: var(--ds-color-muted); font-size: var(--ds-type-caption-size);
  transition: color var(--ds-motion-duration) var(--ds-ease-out), border-color var(--ds-motion-duration) var(--ds-ease-out);
}
.insights-examples button:hover:not(:disabled) { color: var(--ds-color-text); border-color: var(--ds-color-border); }
.insights-result { display: grid; gap: var(--ds-space-4); }
.insights-card { gap: 12px; }
.insights-charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: var(--ds-space-4); }
.insights-note {
  margin: 0; padding: 10px 12px;
  border: 1px solid var(--ds-hairline); border-radius: var(--ds-radius-md);
  background: color-mix(in srgb, var(--ds-color-text) 3%, var(--ds-surface-base));
  color: var(--ds-color-muted); font-size: var(--ds-type-body-caption-size); line-height: 1.6;
}
.insights-note--warn { border-color: var(--ds-pill-warning-bg); color: var(--ds-pill-warning-fg); }
.insights-list { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }
.insights-list li { display: grid; gap: 2px; padding: 10px 12px; border: 1px solid var(--ds-hairline); border-radius: var(--ds-radius-md); }
.insights-list strong { color: var(--ds-color-text); font-size: var(--ds-type-body-size); font-weight: 500; }
.insights-meta { display: flex; justify-content: space-between; gap: 12px; }
.insights-idle { margin: 0; padding: var(--ds-space-4) 0; }
@media (max-width: 640px) {
  .insights-page { padding-inline: 0; }
  .insights-query { flex-direction: column; }
  .insights-query button { width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  .insights-query button, .insights-examples button { transition: none; }
}
</style>
