<template>
  <div class="ag-shell">
    <header class="ag-head">
      <div>
        <p class="ag-eyebrow">GUARD REPORT · 逐条证据 · 可复算</p>
        <h1 class="ag-title">测评报告 #{{ runId }}</h1>
        <p class="ag-lede">
          报告保留每条用例的输入、响应、命中规则与判定。分数由逐条结果加权计算；
          设为基线后，后续测评会自动与它比对并给出发布门禁结论。
        </p>
      </div>
      <div class="ag-actions">
        <router-link class="ag-btn" to="/guard/runs">返回任务</router-link>
        <button class="ag-btn" :disabled="exporting" @click="exportReport">{{ exporting ? '导出中…' : '导出 JSON' }}</button>
        <button
          v-if="run && run.status === 'COMPLETED' && !run.baseline"
          class="ag-btn ag-btn--primary"
          :disabled="busy"
          @click="makeBaseline"
        >设为基线</button>
      </div>
    </header>

    <div v-if="error" class="ag-error">{{ error }}</div>

    <template v-if="run">
      <div class="ag-grid">
        <section class="ag-card">
          <div class="ag-card__head">
            <h2 class="ag-card__title">测评结论</h2>
            <span class="ag-pill" :class="statusPillClass(run.status)">{{ statusLabel(run.status) }}</span>
          </div>
          <div class="ag-score">
            <div
              class="ag-ring"
              :style="{ '--ag-ring-value': run.score ?? 0, '--ag-ring-color': scoreColor(run.score) }"
            >
              <div class="ag-ring__inner">
                <div class="ag-ring__value">{{ run.score ?? '—' }}</div>
                <div class="ag-ring__unit">安全分 / 100</div>
              </div>
            </div>
            <div class="ag-meta" style="flex: 1">
              <div class="ag-meta__row"><span>被测目标</span><span>{{ run.targetName }}</span></div>
              <div class="ag-meta__row"><span>套件</span><span>{{ suiteLabel(run.suite) }}</span></div>
              <div class="ag-meta__row">
                <span>风险等级</span>
                <span class="ag-pill" :class="riskPillClass(run.riskLevel)">{{ riskLabel(run.riskLevel) }}</span>
              </div>
              <div class="ag-meta__row"><span>通过 / 失败 / 异常</span><span>{{ run.passedCases }} / {{ run.failedCases }} / {{ run.errorCases }}</span></div>
              <div class="ag-meta__row"><span>开始 / 完成</span><span>{{ run.startedAt || '—' }} → {{ run.finishedAt || '—' }}</span></div>
            </div>
          </div>
          <p v-if="run.errorMessage" class="ag-note" style="margin-top: 10px; color: var(--ag-fail)">{{ run.errorMessage }}</p>
        </section>

        <section class="ag-card">
          <div class="ag-card__head">
            <h2 class="ag-card__title">回归门禁</h2>
            <span class="ag-card__sub">{{ run.baseline ? '本次测评是当前基线' : '与同目标基线比对' }}</span>
          </div>
          <template v-if="regression && regression.available">
            <div class="ag-verdict" :class="`ag-verdict--${(regression.verdict || 'pass').toLowerCase()}`">
              <h3 class="ag-verdict__title">{{ verdictTitle(regression.verdict) }}</h3>
              <p class="ag-verdict__text">{{ regression.summary }}</p>
            </div>
            <div class="ag-meta">
              <div class="ag-meta__row"><span>基线测评</span><span>#{{ regression.baseline?.id }} · {{ regression.baseline?.targetName }}</span></div>
              <div class="ag-meta__row"><span>分数</span><span>{{ regression.baselineScore }} → {{ regression.currentScore }}（{{ formatDelta(regression.delta) }}）</span></div>
              <div class="ag-meta__row"><span>新增失败 / 已修复 / 持续失败</span><span>{{ regression.newFailures?.length ?? 0 }} / {{ regression.fixed?.length ?? 0 }} / {{ regression.persisting?.length ?? 0 }}</span></div>
            </div>
            <p class="ag-note" style="margin: 10px 0 0">门禁口径：新增高危失败或安全分下降超过 5 分即 BLOCK。</p>
          </template>
          <p v-else-if="regression" class="ag-note">{{ regression.reason }}</p>
          <p v-else-if="run.baseline" class="ag-note">本次测评已设为基线，后续测评将与它比对。</p>
          <p v-else class="ag-note">该目标还没有基线。把一次稳定通过的测评设为基线后即可启用回归门禁。</p>
        </section>
      </div>

      <section class="ag-card" style="margin-top: 14px">
        <div class="ag-card__head">
          <h2 class="ag-card__title">逐条结果</h2>
          <div class="ag-actions">
            <button
              v-for="item in verdictFilters"
              :key="item.value"
              class="ag-chip"
              :class="{ 'is-active': verdictFilter === item.value }"
              @click="verdictFilter = item.value"
            >{{ item.label }} {{ countVerdict(item.value) }}</button>
          </div>
        </div>

        <div v-if="filteredResults.length">
          <article v-for="result in filteredResults" :key="result.caseId" class="ag-item">
            <div class="ag-item__head">
              <p class="ag-item__title">{{ result.title }}</p>
              <div class="ag-actions">
                <span class="ag-pill" :class="verdictPillClass(result.verdict)">{{ verdictLabel(result.verdict) }}</span>
                <span class="ag-pill" :class="severityPillClass(result.severity)">{{ result.severityLabel }}</span>
              </div>
            </div>
            <div class="ag-item__meta">
              <span class="ag-mono">{{ result.caseId }}</span>
              <span>{{ result.categoryLabel }}</span>
              <span>{{ result.owasp }}</span>
              <span>{{ result.latencyMs }} ms</span>
              <span v-if="result.hitRules.length">命中 {{ result.hitRules.join(' / ') }}</span>
            </div>
            <pre class="ag-pre"><span class="ag-pre__label">测试输入</span>{{ result.prompt }}</pre>
            <pre class="ag-pre"><span class="ag-pre__label">目标响应</span>{{ result.response || '（空响应）' }}</pre>
            <p v-if="result.errorMessage" class="ag-note" style="color: var(--ag-fail); margin: 6px 0 0">异常：{{ result.errorMessage }}</p>
          </article>
        </div>
        <div v-else class="ag-empty" style="margin-top: 10px">
          <h2>{{ run.status === 'RUNNING' ? '测评执行中' : '没有匹配的结果' }}</h2>
          <p>{{ run.status === 'RUNNING' ? '页面会自动刷新，逐条结果完成后出现在这里。' : '切换上方判定筛选查看其他结果。' }}</p>
        </div>
      </section>
    </template>

    <p v-else-if="loading" class="ag-note">加载报告…</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { exportGuardRun, getGuardRegression, getGuardRun, markGuardBaseline } from '../../api/guard'
import type { GuardCaseResult, GuardRun } from '../../api/guard'
import './guard.css'

interface RegressionDiff {
  caseId: string
  title: string
  categoryLabel: string
  severityLabel: string
  beforeVerdict: string
  afterVerdict: string
  riskScore: number
}

interface RegressionPayload {
  available: boolean
  reason?: string
  verdict?: string
  summary?: string
  baselineScore?: number
  currentScore?: number
  delta?: number
  newFailures?: RegressionDiff[]
  fixed?: RegressionDiff[]
  persisting?: RegressionDiff[]
  baseline?: GuardRun
}

const route = useRoute()
const runId = computed(() => String(route.params.id))
const run = ref<GuardRun | null>(null)
const results = ref<GuardCaseResult[]>([])
const regression = ref<RegressionPayload | null>(null)
const loading = ref(false)
const exporting = ref(false)
const busy = ref(false)
const error = ref('')
const verdictFilter = ref('ALL')
let timer: number | undefined
let regressionLoaded = false

const verdictFilters = [
  { value: 'ALL', label: '全部' },
  { value: 'FAIL', label: '失败' },
  { value: 'PASS', label: '通过' },
  { value: 'ERROR', label: '异常' }
]

const filteredResults = computed(() => {
  if (verdictFilter.value === 'ALL') return results.value
  return results.value.filter(item => item.verdict === verdictFilter.value)
})

function countVerdict(value: string) {
  if (value === 'ALL') return results.value.length
  return results.value.filter(item => item.verdict === value).length
}

async function load(poll = false) {
  if (!poll) loading.value = true
  try {
    const response = await getGuardRun(runId.value)
    const data = response.data as { run: GuardRun; results: GuardCaseResult[] }
    run.value = data.run
    results.value = data.results
    error.value = ''
    if (data.run.status === 'QUEUED' || data.run.status === 'RUNNING') {
      startPolling()
    } else {
      stopPolling()
      if (!regressionLoaded) {
        regressionLoaded = true
        await loadRegression()
      }
    }
  } catch (exception: unknown) {
    error.value = exception instanceof Error ? exception.message : '加载报告失败'
  } finally {
    loading.value = false
  }
}

async function loadRegression() {
  try {
    const response = await getGuardRegression(runId.value)
    regression.value = response.data as RegressionPayload
  } catch {
    regression.value = null
  }
}

function startPolling() {
  if (timer === undefined) {
    timer = window.setInterval(() => { load(true) }, 2500)
  }
}

function stopPolling() {
  if (timer !== undefined) {
    window.clearInterval(timer)
    timer = undefined
  }
}

async function makeBaseline() {
  busy.value = true
  try {
    await markGuardBaseline(runId.value)
    regressionLoaded = false
    await load()
  } catch (exception: unknown) {
    error.value = exception instanceof Error ? exception.message : '设置基线失败'
  } finally {
    busy.value = false
  }
}

async function exportReport() {
  exporting.value = true
  try {
    const response = await exportGuardRun(runId.value)
    const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `agentguard-run-${runId.value}.json`
    link.click()
    URL.revokeObjectURL(url)
  } catch (exception: unknown) {
    error.value = exception instanceof Error ? exception.message : '导出失败'
  } finally {
    exporting.value = false
  }
}

function formatDelta(delta?: number) {
  if (delta === undefined) return '—'
  return delta >= 0 ? `+${delta}` : String(delta)
}

function verdictTitle(verdict?: string) {
  return ({
    PASS: '门禁通过 · PASS',
    IMPROVED: '能力提升 · IMPROVED',
    REGRESSION: '检测到回归 · REGRESSION',
    BLOCK: '阻断发布 · BLOCK'
  } as Record<string, string>)[verdict ?? ''] ?? '未评估'
}

function scoreColor(score: number | null) {
  if (score === null || score === undefined) return 'var(--ag-muted)'
  if (score >= 90) return 'var(--ag-pass)'
  if (score >= 75) return 'var(--ag-warn)'
  return 'var(--ag-fail)'
}

function statusLabel(value: string) {
  return ({ QUEUED: '排队中', RUNNING: '执行中', COMPLETED: '已完成', FAILED: '失败' } as Record<string, string>)[value] ?? value
}

function statusPillClass(value: string) {
  if (value === 'COMPLETED') return 'ag-pill--pass'
  if (value === 'FAILED') return 'ag-pill--fail'
  if (value === 'RUNNING') return 'ag-pill--info'
  return 'ag-pill--muted'
}

function suiteLabel(value: string) {
  return ({ SMOKE: '冒烟 6 条', STANDARD: '标准 12 条', FULL: '全量 24 条' } as Record<string, string>)[value] ?? value
}

function riskLabel(value: string | null) {
  return ({ LOW: '低风险', MEDIUM: '中风险', HIGH: '高风险', CRITICAL: '严重' } as Record<string, string>)[value ?? ''] ?? '未评级'
}

function riskPillClass(value: string | null) {
  if (value === 'LOW') return 'ag-pill--pass'
  if (value === 'MEDIUM') return 'ag-pill--warn'
  if (value === 'HIGH' || value === 'CRITICAL') return 'ag-pill--fail'
  return 'ag-pill--muted'
}

function verdictLabel(value: string) {
  return ({ PASS: '通过', FAIL: '失败', ERROR: '异常' } as Record<string, string>)[value] ?? value
}

function verdictPillClass(value: string) {
  if (value === 'PASS') return 'ag-pill--pass'
  if (value === 'FAIL') return 'ag-pill--fail'
  return 'ag-pill--warn'
}

function severityPillClass(value: string) {
  if (value === 'CRITICAL' || value === 'HIGH') return 'ag-pill--fail'
  if (value === 'MEDIUM') return 'ag-pill--warn'
  return 'ag-pill--info'
}

onMounted(() => load())
onUnmounted(stopPolling)
</script>
