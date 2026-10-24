<template>
  <section class="model-analytics" :aria-busy="loading && !isDemo">
    <header class="analytics-heading">
      <div><p class="eyebrow">MODEL OBSERVATORY / 模型观测</p><h1>{{ isTokens ? 'Token 用量与额度' : '模型强度' }}</h1>
        <p class="intro">{{ isTokens ? '看清每一次调用的消耗，让月度用量保持可控。' : '从实际调用中观察可用性与响应表现。' }}</p>
      </div>
      <RouterLink class="outline-button" to="/model-settings">管理模型连接 <span aria-hidden="true">↗</span></RouterLink>
    </header>

    <nav class="analytics-tabs" aria-label="模型页面">
      <RouterLink to="/model-strength" :aria-current="!isTokens ? 'page' : undefined">模型强度</RouterLink>
      <RouterLink to="/token-usage" :aria-current="isTokens ? 'page' : undefined">Token 用量与额度</RouterLink>
    </nav>

    <!-- 真实里程碑入口：本月调用达到档位才出现（演示模式不显示，不拿虚构数据炫耀） -->
    <RouterLink v-if="isTokens && !isDemo && callsMilestone" class="milestone-link" to="/milestones">
      <i class="milestone-dot" aria-hidden="true" />
      本月调用已达成 {{ callsMilestone.toLocaleString('zh-CN') }} 次里程碑 · 查看里程碑战报
      <span aria-hidden="true">↗</span>
    </RouterLink>

    <div class="demo-controls">
      <span>{{ isDemo ? '当前查看：虚构案例' : '想先了解图表？可以查看虚构案例。' }}</span>
      <button type="button" class="outline-button" :disabled="saving" :aria-pressed="isDemo" @click="demoEnabled = !demoEnabled">{{ isDemo ? '返回真实数据' : '查看虚构案例' }}</button>
    </div>
    <aside v-if="isDemo" class="demo-banner" role="status">
      <strong>演示模式 · 虚构数据</strong>
      <h2>Nginx 502 故障排查</h2>
      <p>2026 年 9 月 19–25 日，模拟使用排障助手分析错误日志、检查上游服务并生成排查步骤。共 250 次调用，242 次成功；5 次超时、3 次空回复。</p>
      <p>以下图表、模型和额度均为虚构案例，仅用于展示界面，不计入真实账本，也不会修改已保存额度。</p>
    </aside>

    <div v-if="!isDemo" class="analytics-filters">
      <div class="filter-fields">
        <label>统计月份 <input v-model="month" aria-label="统计月份" type="month" min="2000-01" max="2100-12" :disabled="saving" /></label>
        <label>模型连接 <select v-model="connectionId" aria-label="模型连接" :disabled="saving"><option value="">全部模型</option><option v-for="item in connectionOptions" :key="item.id" :value="String(item.id)">{{ item.name }}</option></select></label>
        <div v-if="isTokens" class="period-switch" role="group" aria-label="统计周期">
          <button v-for="item in periodOptions" :key="item.value" type="button" :aria-pressed="period === item.value" @click="period = item.value">{{ item.label }}</button>
        </div>
      </div>
      <div class="filter-actions">
        <span v-if="isTokens && refreshNote" class="refresh-note" role="status">{{ refreshNote }}</span>
        <label v-if="isTokens" class="auto-refresh"><input v-model="autoRefresh" type="checkbox" :disabled="saving"><span>自动刷新 60 秒</span></label>
        <span v-if="isTokens && lastUpdated" class="refresh-stamp">更新于 {{ lastUpdated }}</span>
        <button class="outline-button" type="button" :disabled="loading || saving" @click="loadReport()">{{ loading ? '读取中…' : '刷新统计' }}</button>
      </div>
    </div>
    <p v-if="connectionWarning && !isDemo" class="source-note">{{ connectionWarning }}</p>
    <div v-if="error && !isDemo" class="state-panel error-panel" role="alert"><h2>暂时无法读取统计</h2><p>{{ error }}</p><button type="button" class="outline-button" :disabled="loading" @click="loadReport()">重新加载</button></div>
    <div v-else-if="loading && !isDemo" class="state-panel" role="status">正在读取 {{ month }} 的调用记录…</div>

    <template v-else-if="report">
      <div class="metric-grid">
        <article v-for="metric in metrics" :key="metric.label" class="metric-card"><p>{{ metric.label }}</p><strong>{{ metric.value }}<small v-if="metric.unit">{{ metric.unit }}</small></strong><em v-if="metric.delta" class="metric-delta" :data-direction="metric.delta.direction">{{ deltaText(metric.delta) }}</em><MetricSparkline v-if="metric.spark" :values="metric.spark" /><span>{{ metric.note }}</span></article>
      </div>

      <div v-if="!summary.calls" class="empty-notice"><strong>本月暂无调用记录</strong><p>接入模型并通过 SmartOps 完成调用后，这里会显示真实统计。功能启用前的历史调用不会补录。</p></div>

      <div v-if="isTokens" class="token-layout">
        <div class="token-charts">
        <article class="analytics-panel trend-panel">
          <div class="panel-title"><div><p class="eyebrow">DAILY CONSUMPTION</p><h2>每日 Token 用量</h2></div><span class="unit-label">TOKEN / 日</span></div>
          <ChartLineDefault title="每日 Token 用量" :labels="dates" :series="tokenSeries" :reference="paceReference" />
          <p class="source-note">{{ isDemo ? '虚构案例 · 仅展示 9 月 19–25 日的七天样本。输入 100,000、输出 50,000，合计 150,000 Token。' : '按 UTC 自然日统计。仅汇总服务商已上报值；输入、输出和总量可能分别缺失。空缺不按零补齐，未来日期不作预测。' }}</p>
          <p v-if="paceReference" class="source-note">虚线为额度节奏线（月度额度 ÷ {{ daysOfMonth }} 天），只对照消耗速度，不是服务商计费线。</p>
        </article>

        <article class="analytics-panel stack-panel">
          <div class="panel-title"><div><p class="eyebrow">DAILY COMPOSITION</p><h2>每日用量构成</h2></div><span class="unit-label">TOKEN / 日</span></div>
          <ChartBarStack title="每日用量构成" :labels="dates" :series="stackSeries" />
          <p class="source-note">{{ isDemo ? '虚构案例的输入 / 输出堆叠：输入占三分之二，输出占三分之一。' : '按 UTC 自然日堆叠。仅统计服务商已上报的输入与输出；与上图中总量的差异为未知或待确认用量，不按零补齐。' }}</p>
        </article>

        <ModelShareDonut :rows="leaderRows" :unit-label="`${report.month} · 按已知 Token`" :note="isDemo ? '虚构案例的模型分区，仅作演示，不计入真实账本。' : '按当月已知 Token 计算份额；用量未知的调用不计入，不按零伪造。'" />
        </div>

        <article class="analytics-panel budget-panel">
          <p class="eyebrow">MONTHLY BUDGET</p><h2>{{ isDemo ? '演示月度 Token 额度' : '月度 Token 额度' }}</h2><p class="source-note">{{ report.month }} · {{ isDemo ? '虚构预算 · 已使用 30%' : '全部模型共享，不随连接筛选变化' }}</p>
          <div class="budget-total"><strong>{{ formatMetric(report.budgetUsedTokens) }}</strong><span> / {{ report.budget == null ? '未设额度' : formatMetric(report.budget) }} Token</span></div>
          <div v-if="report.budget != null" class="budget-ring-row">
            <QuotaRing :budget="report.budget" :used="report.budgetUsedTokens" />
            <div class="budget-total"><strong>{{ formatMetric(report.budgetUsedTokens) }}</strong><span> / {{ formatMetric(report.budget) }} Token</span></div>
          </div>
          <div v-else class="budget-total"><strong>{{ formatMetric(report.budgetUsedTokens) }}</strong><span> / 未设额度 Token</span></div>
          <div v-if="pace.dailyRate != null" class="pace-readout">
            <p class="eyebrow">USAGE PACE / 消耗速率</p>
            <div class="pace-row"><span>日均消耗（已知用量线性推算）</span><strong>{{ formatMetric(Math.round(pace.dailyRate)) }}<small>Token / 日</small></strong></div>
            <div class="pace-row"><span>按当前速率预计全月</span><strong>{{ formatMetric(Math.round(pace.projected)) }}<small v-if="pace.pacePercent != null">Token · 额度的 {{ formatMetric(pace.pacePercent, 1) }}%</small><small v-else>Token</small></strong></div>
            <p class="pace-forecast" :class="{ 'is-over': paceOver }">{{ paceForecast }}</p>
          </div>
          <p class="budget-remaining" :class="{ 'is-over': budget.overage > 0 }">{{ budget.overage > 0 ? `已知用量超出 ${formatMetric(budget.overage)} Token` : report.budget == null ? '设置额度后可查看使用进度' : `按已知用量剩余 ${formatMetric(budget.remaining)} Token` }}</p>
          <p v-if="report.budgetUnknownCalls" class="budget-warning">另有 {{ formatMetric(report.budgetUnknownCalls) }} 次调用用量未知或待确认，实际剩余额度可能更少。</p>
          <form v-if="!isDemo" class="budget-form" @submit.prevent="saveBudget">
            <label for="token-budget">设置本月额度（Token）</label>
            <input id="token-budget" v-model="budgetInput" type="text" inputmode="numeric" autocomplete="off" placeholder="留空表示不设额度" :disabled="saving" :aria-invalid="!!budgetError" aria-describedby="budget-help" />
            <p id="budget-help" class="source-note">支持 0–1,000,000,000,000 的整数。清空后保存可取消额度。</p>
            <p v-if="budgetError" class="form-error" role="alert">{{ budgetError }}</p>
            <p v-if="saveMessage" class="save-message" role="status">{{ saveMessage }}</p>
            <button class="primary-button" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存额度' }}</button>
          </form>
          <p class="budget-disclaimer">{{ isDemo ? '演示额度仅供查看，不会写入服务器。返回真实数据后可管理实际自设额度。' : '这是 SmartOps 自设提醒额度，不代表服务商账户余额，也不会自动阻断调用。' }}</p>
        </article>
      </div>

      <UsageQualityPanel v-if="isTokens" :aggregate="periodAgg" :period-label="periodLabel" />
      <ModelLeaderboard v-if="isTokens" :rows="leaderRows" :unit-label="`${report.month} · 按已知 Token`" :note="leaderNote" />

      <template v-else>
        <div class="strength-charts">
          <article class="analytics-panel"><div class="panel-title"><div><p class="eyebrow">RELIABILITY</p><h2>每日调用成功率</h2></div><span class="unit-label">%</span></div><ChartLineDefault title="每日调用成功率" :labels="dates" :series="successSeries" unit="%" :maximum="100" /></article>
          <article class="analytics-panel"><div class="panel-title"><div><p class="eyebrow">RESPONSE TIME</p><h2>平均响应耗时</h2></div><span class="unit-label">MS</span></div><ChartLineDefault title="平均响应耗时" :labels="dates" :series="latencySeries" unit="ms" /></article>
        </div>
        <p v-if="isDemo" class="source-note strength-note">虚构趋势解读：9 月 22 日响应耗时短暂上升至 2,200 ms，之后下降至 1,400 ms。七天成功率为 96.8%；平均耗时按每日成功调用次数加权。以上仅作界面演示，不代表真实模型性能。</p>
        <p class="source-note strength-note">“模型强度”在这里指调用表现，不是通用能力评分。成功率 = 有效回复 / 已完成调用；耗时仅统计成功调用的完整响应时间，不是首 Token 延迟。样本量、网络和任务长度都会影响结果。</p>
      </template>

      <article class="analytics-panel model-breakdown">
        <div class="panel-title"><div><p class="eyebrow">MODEL BREAKDOWN</p><h2>{{ isDemo ? '演示模型明细' : '模型明细' }}</h2></div><span class="unit-label">{{ report.month }} · UTC</span></div>
        <div class="table-scroll" tabindex="0" aria-label="模型统计明细">
          <table><thead><tr><th scope="col">模型 / 连接</th><th scope="col">调用次数</th><th scope="col">成功率</th><th scope="col">输入 Token</th><th scope="col">输出 Token</th><th scope="col">已知 Token</th><th scope="col">平均耗时</th><th scope="col">待确认 / 用量未知</th></tr></thead>
            <tbody><tr v-for="item in report.models" :key="`${item.connectionId}-${item.modelName}`"><th scope="row"><b>{{ item.modelName }}</b><small>{{ connectionName(item.connectionId) }}</small></th><td>{{ formatMetric(item.calls) }}</td><td>{{ formatMetric(item.successRate, 1) }}{{ item.successRate == null ? '' : '%' }}</td><td>{{ formatMetric(item.inputTokens) }}</td><td>{{ formatMetric(item.outputTokens) }}</td><td>{{ formatMetric(item.knownTokens) }}</td><td>{{ formatMetric(item.averageLatencyMs) }}{{ item.averageLatencyMs == null ? '' : ' ms' }}</td><td>{{ item.pendingCalls }} / {{ item.unknownUsageCalls }}</td></tr>
              <tr v-if="!report.models.length"><td colspan="8" class="empty-table">暂无模型调用数据</td></tr>
            </tbody></table>
        </div>
      </article>
      <footer class="analytics-footer"><span>{{ isDemo ? '来源：本地虚构案例 · 非真实调用' : `来源：SmartOps 调用账本 · ${report.timezone || 'UTC'}` }}</span><span>{{ isDemo ? '仅作界面演示，不代表任何服务商的真实用量或性能。' : '仅记录本系统调用，不包含服务商账户的其他消耗。' }}</span></footer>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ChartBarStack from '../../components/ui/v-chart-bar.vue'
import ChartLineDefault from '../../components/ui/v-chart-4.vue'
import QuotaRing from '../../components/model/QuotaRing.vue'
import MetricSparkline from '../../components/model/MetricSparkline.vue'
import ModelLeaderboard from '../../components/model/ModelLeaderboard.vue'
import UsageQualityPanel from '../../components/model/UsageQualityPanel.vue'
import { getModelAnalytics, saveModelTokenBudget } from '../../api/modelAnalytics.ts'
import { getModelConnections } from '../../api/model.ts'
import { budgetState, daysInMonth, formatMetric, modelLeaderboard, parseTokenBudget, periodAggregate, periodDelta, priorPeriodAggregate, usagePace, validMonth } from '../../components/model/modelAnalytics.js'
import { createTokenUsageDemo } from '../../components/model/tokenUsageDemo.js'
import { callMilestoneReached } from '../../components/celebrate/achievements.js'
import ModelShareDonut from '../../components/model/ModelShareDonut.vue'

const props = defineProps({ mode: { type: String, default: 'strength' } })
const isTokens = computed(() => props.mode === 'tokens')
// 周期三档（claude-usage 的今日/本周/本月）：今日与近 7 天按 UTC 从 daily 切片，本月用 summary 权威口径
const DEMO_TODAY = '2026-09-25' // 虚构案例的"今天"，与 demo 七天样本最后一天对齐
const periodOptions = [{ value: 'month', label: '本月' }, { value: 'week', label: '近 7 天' }, { value: 'today', label: '今日' }]
const period = ref('month')
const periodLabel = computed(() => periodOptions.find(item => item.value === period.value)?.label || '本月')
const todayStamp = computed(() => isDemo.value ? DEMO_TODAY : new Date().toISOString().slice(0, 10))
const periodAgg = computed(() => periodAggregate(report.value?.daily, report.value?.summary, period.value, todayStamp.value))
// 环比：week/today 档对上一等长周期；month 档接口不提供上月口径，不给徽标也不猜
const priorAgg = computed(() => period.value === 'month' ? null : priorPeriodAggregate(report.value?.daily, period.value, todayStamp.value))
const deltaOf = key => {
  if (!priorAgg.value?.available || !periodAgg.value.available) return null
  return periodDelta(periodAgg.value[key], priorAgg.value[key])
}
const deltaText = delta => delta.direction === 'up' ? `较上一${period.value === 'today' ? '日' : '周期'} ↑ ${delta.percent.toFixed(1)}%`
  : delta.direction === 'down' ? `较上一${period.value === 'today' ? '日' : '周期'} ↓ ${delta.percent.toFixed(1)}%`
  : delta.direction === 'new' ? `较上一${period.value === 'today' ? '日' : '周期'} 新增消耗`
  : '较上一周期 基本持平'
const sparkWindow = computed(() => {
  const daily = report.value?.daily || []
  const usable = daily.filter(day => day.date <= todayStamp.value)
  return period.value === 'month' ? usable : usable.slice(-7)
})
const sparkOf = key => sparkWindow.value.map(day => day[key] ?? null)
const month = ref(new Date().toISOString().slice(0, 7)), connectionId = ref('')
const realReport = ref(null), connections = ref([]), historicalConnections = ref([])
const demoEnabled = ref(false)
const isDemo = computed(() => demoEnabled.value)
const demoReport = createTokenUsageDemo()
const report = computed(() => isDemo.value ? demoReport : realReport.value)
watch(isTokens, () => { demoEnabled.value = false })
const loading = ref(false), saving = ref(false), error = ref(''), connectionWarning = ref('')
const budgetInput = ref(''), budgetError = ref(''), saveMessage = ref('')
// 自动刷新（Claude-Code-Agent-Monitor 的推流策略在无推流通道下的等价适配）：
// 定时轮询 + 页面不可见时暂停 + 重新可见立即补一次；静默刷新不清空已有内容，失败保留上一次数据
const autoRefresh = ref(false), refreshing = ref(false), lastUpdated = ref(''), refreshNote = ref('')
let requestVersion = 0, disposed = false, refreshTimer = 0
function stampUpdate() { lastUpdated.value = new Date().toTimeString().slice(0, 8); refreshNote.value = '' }
function stopAutoRefresh() { if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = 0 } }
watch(autoRefresh, enabled => {
  stopAutoRefresh()
  if (!enabled) return
  loadReport({ silent: true })
  refreshTimer = setInterval(() => { if (!disposed && document.visibilityState === 'visible') loadReport({ silent: true }) }, 60000)
})
function onVisibilityChange() { if (autoRefresh.value && !disposed && document.visibilityState === 'visible') loadReport({ silent: true }) }
const summary = computed(() => report.value?.summary || {})
// 真实里程碑入口：本月调用达到档位才显示（tremor 徽标语言的庆祝变体；未达档不炫耀）
const callsMilestone = computed(() => callMilestoneReached(summary.value.calls))
const dates = computed(() => report.value?.daily?.map(day => day.date) || [])
const series = (name, key) => ({ name, data: report.value?.daily?.map(day => day[key] ?? null) || [] })
const tokenSeries = computed(() => [series('总量', 'knownTokens'), series('输入', 'inputTokens'), series('输出', 'outputTokens')])
const stackSeries = computed(() => [series('输入', 'inputTokens'), series('输出', 'outputTokens')])
const successSeries = computed(() => [series('成功率', 'successRate')])
const latencySeries = computed(() => [series('响应耗时', 'averageLatencyMs')])
const budget = computed(() => budgetState(report.value?.budget, report.value?.budgetUsedTokens))
const connectionOptions = computed(() => {
  const map = new Map(historicalConnections.value.map(item => [String(item.id), item]))
  connections.value.forEach(item => map.set(String(item.id), { id: item.id, name: item.name }))
  return [...map.values()]
})
const connectionName = id => isDemo.value ? '演示连接 · 不会发起模型调用' : connectionOptions.value.find(item => String(item.id) === String(id))?.name || `连接 #${id}（历史记录）`
const metrics = computed(() => isTokens.value ? [
  { label: `已知总用量 · ${periodLabel.value}`, value: formatMetric(periodAgg.value.knownTokens), unit: 'Token', note: periodAgg.value.available ? (isDemo.value ? '虚构案例合计' : '服务商已上报的总量') : '所选周期暂无调用记录', spark: sparkOf('knownTokens'), delta: deltaOf('knownTokens') },
  { label: `输入 Token · ${periodLabel.value}`, value: formatMetric(periodAgg.value.inputTokens), note: periodAgg.value.available ? (isDemo.value ? '虚构日志与提示词消耗' : '仅汇总已上报输入') : '所选周期暂无已上报输入', spark: sparkOf('inputTokens'), delta: deltaOf('inputTokens') },
  { label: `输出 Token · ${periodLabel.value}`, value: formatMetric(periodAgg.value.outputTokens), note: periodAgg.value.available ? (isDemo.value ? '虚构排查建议消耗' : '仅汇总已上报输出') : '所选周期暂无已上报输出', spark: sparkOf('outputTokens'), delta: deltaOf('outputTokens') },
  { label: `用量未知 / 待确认 · ${periodLabel.value}`, value: `${formatMetric(periodAgg.value.unknownUsageCalls)} / ${formatMetric(periodAgg.value.pendingCalls)}`, note: `${periodLabel.value}共 ${formatMetric(periodAgg.value.calls)} 次调用` }
] : [
  { label: isDemo.value ? '演示调用成功率' : '调用成功率', value: formatMetric(summary.value.successRate, 1), unit: summary.value.successRate == null ? '' : '%', note: `${formatMetric(summary.value.successes)} 成功 / ${formatMetric(summary.value.failures)} 失败` },
  { label: '平均响应耗时', value: formatMetric(summary.value.averageLatencyMs), unit: summary.value.averageLatencyMs == null ? '' : 'ms', note: isDemo.value ? '虚构成功调用的加权平均耗时' : '成功调用的完整响应耗时' },
  { label: '调用次数', value: formatMetric(summary.value.calls), note: isDemo.value ? '七天虚构案例合计' : '包含成功、失败与待确认调用' },
  { label: '待确认调用', value: formatMetric(summary.value.pendingCalls), note: isDemo.value ? '演示样本均已结束' : '处理中或最终结果尚未写入' }
])
// 消耗速率与全月预计（token-monitor 的实时速率）：纯线性推算，只用于对照额度节奏
const pace = computed(() => usagePace(report.value?.budget, report.value?.budgetUsedTokens, report.value?.month || month.value, todayStamp.value))
const daysOfMonth = computed(() => daysInMonth(report.value?.month || month.value))
const paceReference = computed(() => {
  const limit = report.value?.budget
  return limit != null && limit > 0 ? { name: '额度节奏线', value: Math.max(1, Math.round(limit / daysOfMonth.value)) } : null
})
const paceOver = computed(() => {
  const limit = report.value?.budget
  return limit != null && pace.value.projected != null && pace.value.projected > limit
})
const paceForecast = computed(() => {
  const state = pace.value, limit = report.value?.budget
  if (state.dailyRate == null) return isDemo.value ? '演示样本不足，无法推算消耗速率。' : '今日暂无已上报用量，速率自明天起累计。'
  const projected = Math.round(state.projected)
  if (limit == null) return `按当前速率，预计全月消耗 ${formatMetric(projected)} Token。`
  if (state.exhaustDate) return `按当前速率预计 ${state.exhaustDate.slice(5)} 触及额度线，全月将超出 ${formatMetric(projected - limit)} Token。`
  if (projected > limit) return `按当前速率预计全月超出 ${formatMetric(projected - limit)} Token。`
  return `按当前速率预计全月剩余 ${formatMetric(limit - projected)} Token。`
})
// 模型消耗榜：排名/占比在纯函数里算定，这里只补连接名
const leaderRows = computed(() => modelLeaderboard(report.value?.models || []).rows.map(row => ({ ...row, connection: connectionName(row.connectionId) })))
const leaderNote = computed(() => isDemo.value ? '虚构案例的模型分区，仅作演示，不计入真实账本。' : '按当月已知 Token 降序；用量未知的调用排最后且不计入占比，不按零伪造。')
const unwrap = response => response?.data ?? response
async function loadReport({ silent = false } = {}) {
  const version = ++requestVersion
  error.value = ''; budgetError.value = ''; saveMessage.value = ''
  if (!silent) { realReport.value = null; refreshNote.value = '' }
  if (!validMonth(month.value)) { if (!silent) error.value = '请选择 2000–2100 年间的有效月份。'; loading.value = false; return }
  if (!silent) loading.value = true
  refreshing.value = true
  try {
    const data = unwrap(await getModelAnalytics(month.value, connectionId.value))
    if (disposed || version !== requestVersion) return
    realReport.value = data; budgetInput.value = data.budget == null ? '' : String(data.budget)
    if (!connectionId.value) historicalConnections.value = (data.models || []).map(item => ({ id: item.connectionId, name: `${item.modelName} · #${item.connectionId}` }))
    stampUpdate()
  } catch (err) {
    if (disposed || version !== requestVersion) return
    if (silent) refreshNote.value = `自动刷新失败（${err.message || '网络错误'}），显示的是上一次数据。`
    else error.value = err.message || '统计服务暂不可用，请重试。'
  } finally { if (!disposed && version === requestVersion) { loading.value = false; refreshing.value = false } }
}
async function saveBudget() {
  if (saving.value || isDemo.value) return
  budgetError.value = ''; saveMessage.value = ''
  let limit
  try { limit = parseTokenBudget(budgetInput.value) } catch (err) { budgetError.value = err.message; return }
  saving.value = true
  const currentMonth = month.value
  try {
    const saved = unwrap(await saveModelTokenBudget(currentMonth, limit))
    if (disposed || currentMonth !== month.value || !report.value) return
    realReport.value = { ...realReport.value, budget: saved.budget, budgetUsedTokens: saved.budgetUsedTokens, budgetUnknownCalls: saved.budgetUnknownCalls }
    saveMessage.value = limit == null ? '已取消本月额度。' : '本月额度已保存。'
  } catch (err) { if (!disposed) budgetError.value = err.message || '保存失败，请重试。' }
  finally { if (!disposed) saving.value = false }
}
watch([month, connectionId], () => loadReport(), { immediate: true })
onMounted(async () => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  try { const data = unwrap(await getModelConnections()); if (!disposed) connections.value = Array.isArray(data) ? data : [] }
  catch { if (!disposed) connectionWarning.value = '连接列表暂不可用，仍可按已有调用记录筛选。' }
})
onBeforeUnmount(() => { disposed = true; requestVersion++; stopAutoRefresh(); document.removeEventListener('visibilitychange', onVisibilityChange) })
</script>

<style scoped>
.demo-controls { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin: 20px 0; color: var(--smart-muted); font-size: 12px; }.demo-controls button[aria-pressed=true] { border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); }.demo-banner { padding: 20px; margin: 0 0 24px; border: 1px solid var(--smart-primary-strong); border-radius: 12px; background: var(--smart-surface); }.demo-banner strong { display: inline-block; color: var(--smart-primary-strong); font-size: 12px; margin-bottom: 12px; }.demo-banner p { color: var(--smart-muted); font-size: 12px; line-height: 1.8; margin: 10px 0 0; }
.model-analytics { max-width: 1280px; margin: 0 auto; padding: 12px 0 36px; color: var(--smart-text); font-family: var(--font-cn); }
.analytics-heading { display: flex; justify-content: space-between; gap: 24px; align-items: center; }.eyebrow { margin: 0 0 10px; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .13em; }h1 { margin: 0; font-size: clamp(26px, 3vw, 36px); font-weight: 550; letter-spacing: -.03em; }.intro { color: var(--smart-muted); font-size: 13px; line-height: 1.8; margin: 12px 0 0; }h2 { margin: 0; font-size: 17px; font-weight: 550; }
.outline-button, .primary-button { display: inline-flex; align-items: center; justify-content: center; gap: 14px; min-height: 40px; padding: 9px 16px; border: 1px solid var(--smart-border); border-radius: 8px; font: inherit; font-size: 12px; color: var(--smart-text); background: var(--smart-surface); text-decoration: none; cursor: pointer; transition: border-color 140ms, background 140ms; white-space: nowrap; }.outline-button:hover { border-color: var(--smart-primary-strong); }.primary-button { background: var(--smart-primary-strong); color: var(--smart-bg); border-color: transparent; font-weight: 600; }button:disabled { opacity: .5; cursor: wait; }button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 3px; }
.analytics-tabs { display: flex; gap: 28px; margin-top: 30px; border-bottom: 1px solid var(--smart-border); }.analytics-tabs a { padding: 14px 0; text-decoration: none; color: var(--smart-muted); font-size: 13px; border-bottom: 2px solid transparent; }.analytics-tabs a[aria-current=page] { color: var(--smart-primary-strong); border-color: currentColor; }
.milestone-link { display: inline-flex; align-items: center; gap: 10px; margin-top: 16px; padding: 8px 15px; border: 1px solid var(--smart-border); border-radius: 999px; font-size: 12px; color: var(--smart-muted); text-decoration: none; transition: border-color 140ms, color 140ms; }.milestone-link:hover { border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); }.milestone-dot { width: 7px; height: 7px; background: var(--smart-primary-strong); transform: rotate(45deg); }
.analytics-filters { display: flex; justify-content: space-between; align-items: end; gap: 16px; margin: 24px 0; }.filter-fields { display: flex; gap: 16px; min-width: 0; }.filter-fields label { display: grid; gap: 8px; font-size: 11px; color: var(--smart-muted); min-width: 0; }input, select { min-height: 40px; min-width: 0; max-width: 100%; border: 1px solid var(--smart-border); border-radius: 7px; padding: 8px 12px; color: var(--smart-text); background: var(--smart-surface); font: inherit; font-size: 13px; }.filter-fields select { width: 240px; text-overflow: ellipsis; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 24px; }
/* HUD 切角 KPI 卡：与哨兵统计卡同一语言（clip-path 切角 + inset 描边 + 顶部渐隐高光） */
.metric-card { position: relative; padding: 22px; background: var(--smart-surface); border-radius: 0; min-width: 0; clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px); box-shadow: inset 0 0 0 1px var(--smart-border), inset 0 0 24px var(--smart-primary-soft); }
.metric-card::after { content: ''; position: absolute; inset: 0 0 auto 0; height: 1px; background: linear-gradient(90deg, transparent, var(--smart-primary-strong), transparent); opacity: .8; }
.metric-card p { font-size: 11px; letter-spacing: .06em; color: var(--smart-muted); margin: 0 0 14px; }
.metric-card strong { display: block; font-family: var(--font-mono); font-size: clamp(24px, 2.5vw, 34px); font-weight: 600; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }.metric-card strong small { font-size: 12px; color: var(--smart-muted); margin-left: 7px; }
/* 环比徽标（tremor KPI Card 的 delta badge）：用量指标无褒贬，升/新增用主色、降用弱色，不用红绿涨跌色 */
.metric-delta { display: inline-block; margin: 10px 0 2px; padding: 3px 9px; border: 1px solid var(--smart-border); border-radius: 999px; font: 10px/1.4 var(--font-mono); font-style: normal; letter-spacing: .04em; color: var(--smart-muted); font-variant-numeric: tabular-nums; }
.metric-delta[data-direction=up], .metric-delta[data-direction=new] { color: var(--smart-primary-strong); border-color: var(--smart-primary-strong); }
.metric-card > span { display: block; color: var(--smart-muted); font-size: 11px; line-height: 1.6; margin-top: 12px; }
.analytics-panel { border: 1px solid var(--smart-border); border-radius: 12px; background: var(--smart-surface); padding: 24px; min-width: 0; }.panel-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 26px; }.unit-label { color: var(--smart-muted); font: 10px var(--font-mono); white-space: nowrap; }.token-layout { display: grid; grid-template-columns: minmax(0, 1.8fr) minmax(290px, 1fr); gap: 20px; align-items: start; }.token-charts { display: grid; gap: 20px; min-width: 0; }.budget-ring-row { display: flex; align-items: center; gap: 22px; margin: 20px 0 16px; }.budget-ring-row .budget-total { margin: 0; }.strength-charts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }.source-note { color: var(--smart-muted); font-size: 11px; line-height: 1.8; margin: 12px 0 0; }.strength-note { margin: 18px 0 24px; }.budget-total { margin: 28px 0 16px; font-variant-numeric: tabular-nums; }.budget-total strong { font-size: 28px; font-weight: 500; overflow-wrap: anywhere; }.budget-total > span { display: block; font-size: 12px; color: var(--smart-muted); margin-top: 8px; }.budget-remaining { font-size: 12px; margin: 12px 0 22px; }.budget-warning, .is-over { color: var(--el-color-warning); font-size: 12px; line-height: 1.8; }.budget-form { display: grid; gap: 10px; border-top: 1px solid var(--smart-border); padding-top: 20px; }.budget-form label { font-size: 12px; }.budget-form .source-note { margin: 0; }.budget-form button { margin-top: 4px; }.budget-disclaimer { color: var(--smart-muted); font-size: 11px; line-height: 1.8; margin: 18px 0 0; }.form-error { color: var(--el-color-danger); font-size: 12px; margin: 0; line-height: 1.7; }.save-message { color: var(--smart-primary-strong); font-size: 12px; margin: 0; }
.model-breakdown { margin-top: 24px; }.table-scroll { overflow-x: auto; }table { width: 100%; border-collapse: collapse; font-size: 12px; font-variant-numeric: tabular-nums; }th, td { padding: 16px 14px; border-bottom: 1px solid var(--smart-border); text-align: right; white-space: nowrap; }thead th { color: var(--smart-muted); font-size: 11px; font-weight: 400; }th:first-child { text-align: left; padding-left: 0; }tbody th b { display: block; font-weight: 500; }tbody th small { display: block; margin-top: 6px; font-weight: 400; color: var(--smart-muted); }.empty-table { text-align: center; color: var(--smart-muted); padding: 30px; }.analytics-footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; margin-top: 20px; color: var(--smart-muted); font-size: 10px; line-height: 1.8; }.state-panel { padding: 54px 24px; text-align: center; border: 1px solid var(--smart-border); border-radius: 12px; background: var(--smart-surface); color: var(--smart-muted); font-size: 13px; }.state-panel p { margin: 14px 0 24px; }.empty-notice { border-left: 2px solid var(--smart-primary-strong); padding: 2px 16px; margin: 0 0 24px; font-size: 12px; }.empty-notice p { color: var(--smart-muted); line-height: 1.8; margin: 6px 0; }
.period-switch { display: inline-flex; border: 1px solid var(--smart-border); border-radius: 8px; overflow: hidden; align-self: end; }.period-switch button { min-height: 40px; padding: 8px 15px; border: 0; background: var(--smart-surface); color: var(--smart-muted); font: inherit; font-size: 12px; cursor: pointer; transition: background 140ms, color 140ms; }.period-switch button + button { border-left: 1px solid var(--smart-border); }.period-switch button[aria-pressed=true] { background: var(--smart-primary-strong); color: var(--smart-bg); font-weight: 600; }
.filter-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 14px; }.auto-refresh { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: var(--smart-muted); white-space: nowrap; cursor: pointer; }.auto-refresh input { min-height: 0; width: 15px; height: 15px; accent-color: var(--smart-primary-strong); cursor: pointer; }.refresh-stamp { font-size: 11px; color: var(--smart-muted); white-space: nowrap; font-variant-numeric: tabular-nums; }.refresh-note { font-size: 11px; color: var(--el-color-warning); white-space: nowrap; }
.metric-spark { display: block; width: 100%; height: 30px; margin: 12px 0 2px; color: var(--smart-primary-strong); opacity: .8; }
.pace-readout { border-top: 1px solid var(--smart-border); padding-top: 16px; }.pace-readout .eyebrow { margin-bottom: 6px; }.pace-row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; font-size: 12px; color: var(--smart-muted); padding: 6px 0; }.pace-row strong { color: var(--smart-text); font-weight: 550; font-variant-numeric: tabular-nums; white-space: nowrap; }.pace-row strong small { color: var(--smart-muted); font-weight: 400; margin-left: 6px; }.pace-forecast { font-size: 12px; line-height: 1.7; margin: 8px 0 0; color: var(--smart-primary-strong); }.pace-forecast.is-over { color: var(--el-color-warning); }
@media(max-width: 1100px) { .token-layout { grid-template-columns: minmax(0, 1fr); }.budget-panel { max-width: none; }.strength-charts { grid-template-columns: minmax(0, 1fr); } }
@media(max-width: 767px) { .model-analytics { padding-top: 4px; }.analytics-heading { align-items: start; flex-direction: column; gap: 16px; }.analytics-tabs { margin-top: 20px; gap: 24px; }.analytics-filters { flex-wrap: wrap; }.filter-fields { width: 100%; gap: 12px; display: grid; grid-template-columns: 1fr 1fr; }.filter-fields select { width: 100%; }.filter-fields input { width: 100%; box-sizing: border-box; }.period-switch { grid-column: 1 / -1; width: 100%; }.period-switch button { flex: 1; }.filter-actions { width: 100%; }.metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }.metric-card { padding: 16px; }.metric-card strong { font-size: 22px; }.analytics-panel { padding: 18px 14px; }.panel-title { gap: 8px; }.analytics-footer { flex-direction: column; }.token-layout { gap: 16px; } }
/* 桌面端双栏工作台：Token 用量图区（左）与月度额度区（右）各自独立滚动——
   与团队空间 / 里程碑战报同一「红框两栏互不干扰」契约。
   206 = 顶栏 56 + 工作区条 54 + main.content 底部留白 96（global.css .content）。
   注意：本页 token-layout 下方仍有质量面板、模型榜与明细表，页面保持自然滚动，
   不整页锁死；两栏 min-height:0 + overflow-y:auto，滚一栏另一栏不动。
   栏内滚到头时滚道顺延给页面（不用 overscroll-behavior:contain），保证下方内容可达。
   ≤1100px 单列时回退自然流式布局。 */
@media (min-width: 1101px) {
  .token-layout { height: calc(100dvh - 206px); align-items: stretch; }
  .token-charts, .budget-panel { min-height: 0; overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--smart-border) transparent; padding-right: 2px; }
}
</style>
