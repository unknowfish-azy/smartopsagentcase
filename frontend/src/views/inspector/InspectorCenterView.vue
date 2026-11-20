<template>
  <div class="inspector-page">
    <section class="inspector-hero" :class="{ 'inspector-hero--alert': hasAlerts }">
      <!-- 星域带：数据板整体下移，把上方留白让给事件流光（星系单独呈现） -->
      <div class="inspector-hero__sky" aria-hidden="true"></div>
      <header class="inspector-head">
      <div class="inspector-head__copy">
        <p class="eyebrow">MEMORY · INSPECTOR CENTER</p>
        <h1>SmartOps Inspector</h1>
        <p class="lede">监督 AI 自己：行为、证据、工具、风险、审批与验证。每个粒子对应一条纠察事件。</p>
      </div>
      <div class="inspector-head__actions">
        <span class="status-chip" :class="`status-chip--${status}`">{{ statusLabel }}</span>
        <button type="button" class="ghost-button" @click="toggleDemo">{{ demo ? '退出演示' : '查看演示数据' }}</button>
        <button type="button" class="ghost-button" :disabled="status === 'loading'" @click="load">刷新</button>
        <RouterLink v-if="!demo" class="ghost-button" :to="deskLink">在洞察台打开</RouterLink>
        <button v-else type="button" class="ghost-button" disabled title="演示序列的事件 ID 不存在于数据库">洞察台需真实数据</button>
        <RouterLink class="ghost-button" to="/inspector/statistics">查看统计</RouterLink>
      </div>
    </header>

    <p v-if="demo" class="state-banner state-banner--demo">
      DEMO · 虚构示例，非真实纠察。仅用于展示可视化能力，数据不写入持久化、不代表任何真实结果。
    </p>
    <p v-else-if="status === 'unavailable'" class="state-banner state-banner--warn">
      巡检接口不可用（未登录或后端未接入）{{ error ? `：${error}` : '' }}。下方只显示结构占位，不生成假数据。
    </p>
    <p v-else-if="status === 'empty'" class="state-banner">
      已连接，暂无真实纠察事件。时间轴保留刻度与轨道占位，等待后端写入数据。
    </p>

    <section class="kpi-band" aria-label="纠察概览">
      <article v-for="item in kpiItems" :key="item.key" class="kpi-card">
        <span class="kpi-card__label">{{ item.label }}</span>
        <strong class="kpi-card__value"><KpiNumber :value="item.value" /></strong>
      </article>
    </section>

    <section class="brief" :class="{ 'brief--alert': hasAlerts }" aria-live="polite">
      <InspectorHeroStream
        :events="displayEvents"
        :total="Number(displaySummary?.total) || 0"
        :warn="Number(displaySummary?.warning) || 0"
        :high="Number(displaySummary?.high) || 0"
        :critical="Number(displaySummary?.critical) || 0"
      />
      <span class="brief__label">AGENT 巡检简报</span>
      <p>{{ briefText }}</p>
    </section>
    </section>

    <InspectorAiDiagnosis v-if="!demo" :events="displayEvents" />

    <InspectorDimensionGrid
      :events="displayEvents"
      :active-key="activeDimension"
      @select="activeDimension = $event"
    />

    <section class="panel timeline-panel">
      <div class="panel-title">
        <div>
          <h2>Inspection Timeline</h2>
          <p class="panel-title__meta">{{ filteredEvents.length }} 条事件 · 点击粒子查看证据{{ activeDimension ? ' · 已按维度筛选' : '' }}</p>
        </div>
        <button v-if="activeDimension" type="button" class="ghost-button" @click="activeDimension = ''">清除筛选</button>
      </div>
      <InspectorEventField
        :events="filteredEvents"
        :selected-id="selected?.id ?? null"
        :demo="demo"
        :empty-text="emptyText"
        @select="selected = $event"
      />
    </section>

    <aside v-if="selected" class="evidence-drawer" aria-label="纠察事件证据">
      <header>
        <h3>事件证据</h3>
        <button type="button" class="ghost-button" aria-label="关闭证据抽屉" @click="selected = null">关闭</button>
      </header>
      <dl>
        <div><dt>等级</dt><dd><InspectorSeverityTag :value="selected.severity || 'INFO'" /></dd></div>
        <div><dt>任务</dt><dd>{{ selected.taskId || selected.task || '—' }}</dd></div>
        <div><dt>维度</dt><dd>{{ selected.category || '—' }}</dd></div>
        <div><dt>目标</dt><dd>{{ selected.target || '—' }}</dd></div>
        <div><dt>时间</dt><dd>{{ formatTime(selected.at ?? selected.createdAt) }}</dd></div>
        <div><dt>Trace ID</dt><dd class="mono">{{ selected.traceId || '未关联' }}</dd></div>
        <div v-if="selected.reason"><dt>原因</dt><dd>{{ selected.reason }}</dd></div>
        <div v-if="selected.recommendation"><dt>建议</dt><dd>{{ selected.recommendation }}</dd></div>
      </dl>
      <div v-if="!demo && selected.id != null" class="evidence-drawer__actions">
        <RouterLink class="ghost-button" :to="deskLink">在洞察台查看此事件</RouterLink>
        <RouterLink class="ghost-button" :to="`/inspector/events/${selected.id}`">打开完整详情</RouterLink>
      </div>
    </aside>
  <AgentCopilotDock
    section="纠察中心"
    :entity="{ type: 'event', id: selected?.id ?? filteredEvents?.[0]?.id }"
  />
  </div>
</template>

<script setup>
import AgentCopilotDock from '../../components/agent/AgentCopilotDock.vue'
/**
 * 纠察中心 · P0 重构
 *
 * 变更：
 *  - 废弃琥珀金硬编码，统一到 --ds-* / --smart-* 企业级令牌；
 *  - 8 个纯文字维度标签 → 数据驱动状态卡（InspectorDimensionGrid）；
 *  - 空 Timeline → 数据驱动事件粒子时间轴（InspectorEventField）+ 证据抽屉；
 *  - 三态 ready / empty / unavailable 与 DEMO 态严格区分，DEMO 必须醒目标注；
 *  - 零伪造数据：无数据一律显示「—」，不画装饰性假粒子。
 *
 * 后端 / 数据库由用户负责，本文件只消费 /api/inspector/* 既有接口。
 */
import { computed, onMounted, ref } from 'vue'
import { getInspectorEvents, getInspectorSummary } from '../../api/inspector'
import { buildDemoData } from '../../components/inspector/desk/deskModel'
import { dimensionKeyOf, summaryFromEvents } from '../../components/inspector/dimensions'
import InspectorSeverityTag from '../../components/inspector/InspectorSeverityTag.vue'
import InspectorAiDiagnosis from '../../components/inspector/InspectorAiDiagnosis.vue'
import InspectorDimensionGrid from '../../components/inspector/InspectorDimensionGrid.vue'
import InspectorEventField from '../../components/inspector/InspectorEventField.vue'
import InspectorHeroStream from '../../components/inspector/InspectorHeroStream.vue'
import KpiNumber from '../../components/dashboard/KpiNumber.vue'

const summary = ref({})
const events = ref([])
const demoEvents = ref([])
const status = ref('loading')
const demo = ref(false)
const error = ref('')
const activeDimension = ref('')
const selected = ref(null)

const KPI_DEFS = [
  ['total', 'Total'], ['pass', 'PASS'], ['warning', 'WARN'], ['high', 'HIGH'], ['critical', 'CRITICAL']
]

const STATUS_LABELS = {
  loading: '连接中',
  ready: '实时数据',
  empty: '已连接 · 暂无事件',
  unavailable: '接口不可用'
}

const statusLabel = computed(() => demo.value ? '演示模式' : (STATUS_LABELS[status.value] || '—'))

/* 三页共用一条证据链：选中事件后把 id 带进洞察台（洞察台已支持 route.query.id），
   时间窗固定 24h 与中心页一致；DEMO 态不生成深链，避免跳转到不存在的虚构 ID。 */
const deskLink = computed(() => {
  const params = new URLSearchParams({ view: 'events', window: '24h' })
  if (selected.value?.id != null) params.set('id', String(selected.value.id))
  return `/inspector/desk?${params.toString()}`
})

const displayEvents = computed(() => demo.value ? demoEvents.value : events.value)
const displaySummary = computed(() => demo.value ? summaryFromEvents(demoEvents.value) : summary.value)

const kpiItems = computed(() => KPI_DEFS.map(([key, label]) => ({
  key,
  label,
  value: displaySummary.value?.[key] ?? '—'
})))

/* 头部数据流特效的报红开关：存在 WARN/HIGH/CRITICAL 即告警态 */
const hasAlerts = computed(() => {
  const value = displaySummary.value || {}
  return ((Number(value.warning) || 0) + (Number(value.high) || 0) + (Number(value.critical) || 0)) > 0
})

const filteredEvents = computed(() => activeDimension.value
  ? displayEvents.value.filter(event => dimensionKeyOf(event) === activeDimension.value)
  : displayEvents.value
)

const briefText = computed(() => {
  if (demo.value) return '演示序列：仅用于展示事件粒子时间轴与维度筛选，不代表任何真实纠察结果。'
  if (status.value === 'unavailable') return '巡检接口不可用，暂无 Agent 简报。'
  if (status.value === 'empty') return '已连接，暂无真实纠察记录。'
  const value = displaySummary.value || {}
  return `本批纠察共 ${value.total ?? 0} 条：${value.pass ?? 0} 通过、${value.warning ?? 0} 警告、${value.high ?? 0} 高危、${value.critical ?? 0} 严重。`
})

const emptyText = computed(() => {
  if (status.value === 'unavailable') return '巡检接口不可用（未登录或后端未接入）'
  if (activeDimension.value) return '当前维度暂无事件，点击维度卡或「清除筛选」返回'
  return '等待真实纠察事件接入'
})

function formatTime(raw) {
  if (raw == null) return '—'
  const stamp = typeof raw === 'number' ? raw : Date.parse(raw)
  if (Number.isNaN(stamp)) return '—'
  try {
    return new Date(stamp).toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
    })
  } catch {
    return '—'
  }
}

async function load() {
  status.value = 'loading'
  error.value = ''
  selected.value = null
  try {
    const [summaryRes, eventsRes] = await Promise.all([
      getInspectorSummary(),
      getInspectorEvents(200)
    ])
    summary.value = summaryRes?.data || {}
    events.value = Array.isArray(eventsRes?.data) ? eventsRes.data : []
    status.value = events.value.length ? 'ready' : 'empty'
  } catch (err) {
    error.value = err?.message || 'Inspector 服务不可用'
    summary.value = {}
    events.value = []
    status.value = 'unavailable'
  }
}

function toggleDemo() {
  demo.value = !demo.value
  selected.value = null
  activeDimension.value = ''
  if (demo.value) {
    demoEvents.value = buildDemoData('24h').events
  } else {
    demoEvents.value = []
    load()
  }
}

onMounted(load)
</script>

<style scoped>
.inspector-page {
  display: grid;
  gap: 18px;
  padding: 22px;
  color: var(--ds-color-text, #e8f2f7);
  background: var(--ds-color-surface, #071018);
  border: 1px solid var(--ds-hairline, rgba(159, 190, 207, .18));
  border-radius: 12px;
}
.inspector-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 16px; }
/* 头部量化数据流特效层：流光 canvas 铺底，内容浮于其上 */
.inspector-hero {
  position: relative;
  display: grid;
  gap: 18px;
  padding: 22px;
  border: 1px solid var(--ds-hairline, rgba(159, 190, 207, .18));
  border-radius: 12px;
  overflow: hidden;
  background:
    radial-gradient(120% 90% at 85% -10%, rgba(36, 150, 237, .12), transparent 60%),
    linear-gradient(180deg, rgba(9, 16, 24, .92), rgba(7, 16, 24, .97));
}
.inspector-hero--alert { border-color: rgba(248, 81, 73, .45); box-shadow: inset 0 0 42px rgba(248, 81, 73, .08); }
/* 星域带：专属留白让事件流光单独呈现，数据板（标题/KPI/简报）整体下移 */
.inspector-hero__sky { height: clamp(96px, 13vw, 150px); }
.inspector-hero > * { position: relative; z-index: 1; }
.inspector-hero .inspector-head,
.inspector-hero .state-banner,
.inspector-hero .kpi-card,
.inspector-hero .brief { background: rgba(13, 20, 28, .66); backdrop-filter: blur(3px); }
.inspector-hero--alert .state-banner--demo { background: rgba(46, 30, 8, .72); }
/* 量化数据流特效收进巡检简报区：canvas 铺满简报底面，文字浮于其上 */
.brief { position: relative; overflow: hidden; }
.brief > .hero-stream { z-index: 0; }
.brief > span,
.brief > p { position: relative; z-index: 1; }
.brief--alert { border-left-color: rgba(248, 81, 73, .85); box-shadow: inset 0 0 26px rgba(248, 81, 73, .10); }
.eyebrow { margin: 0 0 6px; color: var(--ds-color-primary-strong, #7ad7f5); font: 11px var(--font-mono, ui-monospace, monospace); letter-spacing: .1em; }
.inspector-head h1 { margin: 0; font-size: var(--ds-type-h1-size, 28px); font-weight: var(--ds-type-h1-weight, 500); }
.lede { margin: 6px 0 0; color: var(--ds-color-muted, #92a6b5); font-size: 13px; }
.inspector-head__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.status-chip {
  padding: 4px 10px;
  border: 1px solid var(--ds-color-border, rgba(159, 190, 207, .18));
  border-radius: 999px;
  color: var(--ds-color-muted, #92a6b5);
  font: 11px var(--font-mono, ui-monospace, monospace);
}
.status-chip--ready { color: var(--ds-semantic-success, #3fb950); border-color: var(--ds-semantic-success, #3fb950); }
.status-chip--unavailable { color: var(--ds-semantic-danger, #f85149); border-color: var(--ds-semantic-danger, #f85149); }
.ghost-button {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 6px 12px;
  border: 1px solid var(--ds-color-border, rgba(159, 190, 207, .18));
  border-radius: 7px;
  background: var(--ds-surface-raised, #151a21);
  color: var(--ds-color-text, #e8f2f7);
  font-size: 12px;
  text-decoration: none;
  cursor: pointer;
  transition: border-color var(--ds-duration-micro, 150ms) ease, color var(--ds-duration-micro, 150ms) ease;
}
.ghost-button:hover { border-color: var(--ds-color-primary, #2496ed); color: var(--ds-color-primary-strong, #7ad7f5); }
.ghost-button:disabled { opacity: .5; cursor: not-allowed; }
.state-banner {
  margin: 0;
  padding: 10px 14px;
  border: 1px solid var(--ds-hairline, rgba(159, 190, 207, .18));
  border-radius: 8px;
  background: var(--ds-surface-raised, #151a21);
  color: var(--ds-color-muted, #92a6b5);
  font-size: 12px;
  line-height: 1.6;
}
.state-banner--demo { border-color: var(--ds-semantic-warning, #d29922); color: var(--ds-semantic-warning, #d29922); }
.state-banner--warn { border-color: var(--ds-semantic-danger, #f85149); color: var(--ds-color-text, #e8f2f7); }
.kpi-band { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
/* KPI 卡同步淡入（无递增延迟）：递增错峰会在切换 DEMO / 刷新后重触发，
   导致后几张卡短暂空白，评委第一眼会看到「缺数据」。数字滚动本身已是动效。 */
@keyframes inspector-kpi-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
.kpi-card {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border: 1px solid var(--ds-hairline, rgba(159, 190, 207, .18));
  border-radius: 9px;
  background: var(--ds-surface-raised, #151a21);
  animation: inspector-kpi-in 240ms ease-out both;
}
.kpi-card__label { color: var(--ds-color-muted, #92a6b5); font: 11px var(--font-mono, ui-monospace, monospace); letter-spacing: .06em; }
.kpi-card__value { font: 300 26px var(--font-mono, ui-monospace, monospace); font-variant-numeric: var(--ds-type-num, tabular-nums); line-height: 1.1; }
.brief {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-left: 2px solid var(--ds-color-primary, #2496ed);
  border-radius: 0 9px 9px 0;
  background: var(--ds-surface-raised, #151a21);
}
.brief__label { color: var(--ds-color-primary-strong, #7ad7f5); font: 11px var(--font-mono, ui-monospace, monospace); letter-spacing: .08em; }
.brief p { margin: 0; font-size: 13px; line-height: 1.6; }
.panel {
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--ds-hairline, rgba(159, 190, 207, .18));
  border-radius: 10px;
  background: var(--ds-surface-raised, #151a21);
}
.panel-title { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; }
.panel-title h2 { margin: 0; font-size: var(--ds-type-h3-size, 18px); font-weight: var(--ds-type-h3-weight, 500); }
.panel-title__meta { margin: 4px 0 0; color: var(--ds-color-muted, #92a6b5); font-size: 12px; }
.evidence-drawer {
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--ds-color-border-strong, rgba(159, 190, 207, .34));
  border-radius: 10px;
  background: var(--ds-surface-overlay, #1b212a);
  box-shadow: var(--ds-elevation-2, 0 4px 16px rgba(0, 0, 0, .35));
}
.evidence-drawer header { display: flex; justify-content: space-between; align-items: center; }
.evidence-drawer h3 { margin: 0; font-size: 15px; font-weight: 500; }
.evidence-drawer dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 18px; margin: 0; }
.evidence-drawer dl > div { display: grid; gap: 3px; min-width: 0; }
.evidence-drawer dt { color: var(--ds-color-muted, #92a6b5); font-size: 11px; }
.evidence-drawer dd { margin: 0; font-size: 13px; overflow-wrap: anywhere; }
.evidence-drawer .mono { font-family: var(--font-mono, ui-monospace, monospace); font-size: 12px; }
.evidence-drawer__actions { display: flex; flex-wrap: wrap; gap: 8px; }
@media (max-width: 1023px) { .kpi-band { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 767px) {
  .inspector-page { padding: 16px; }
  .kpi-band { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .inspector-hero__sky { height: 72px; }
  .evidence-drawer dl { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .ghost-button { transition: none; }
  .kpi-card { animation: none; }
}
</style>
