<template>
  <div class="ag-shell">
    <header class="ag-head">
      <div>
        <p class="ag-eyebrow">AGENTGUARD · 安全测评 · 回归门禁</p>
        <h1 class="ag-title">智测盾 · 测评总览</h1>
        <p class="ag-lede">
          用确定性攻击用例集给 AI Agent 做上线前安全体检：逐条判定提示注入、数据外泄、工具滥用与越权，
          再把结果折算成安全分，并与基线版本做回归比对。
        </p>
      </div>
      <div class="ag-actions">
        <button class="ag-btn" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新数据' }}</button>
        <router-link class="ag-btn" to="/guard/cases">用例库</router-link>
        <router-link class="ag-btn ag-btn--primary" to="/guard/runs">发起测评</router-link>
      </div>
    </header>

    <div v-if="error" class="ag-error">{{ error }}</div>

    <div v-if="!loading && overview && overview.totalRuns === 0" class="ag-empty">
      <h2>还没有测评记录</h2>
      <p>
        选择一个被测目标，先用「冒烟」套件跑 6 条关键用例。若还没有模型连接，可先用内置严格策略 Agent
        验证平台判定链路，或用弱策略靶标验证检测器命中。
      </p>
      <router-link class="ag-btn ag-btn--primary" to="/guard/runs">去发起第一次测评</router-link>
    </div>

    <template v-else-if="overview">
      <section class="ag-kpis">
        <div class="ag-kpi">
          <div class="ag-kpi__label">累计测评</div>
          <div class="ag-kpi__value">{{ overview.totalRuns }}</div>
          <div class="ag-kpi__hint">按当前账号统计</div>
        </div>
        <div class="ag-kpi">
          <div class="ag-kpi__label">平均安全分</div>
          <div class="ag-kpi__value">{{ overview.averageScore ?? '—' }}</div>
          <div class="ag-kpi__hint">仅统计已完成测评</div>
        </div>
        <div class="ag-kpi">
          <div class="ag-kpi__label">阻断次数</div>
          <div class="ag-kpi__value">{{ overview.blockedRuns }}</div>
          <div class="ag-kpi__hint">回归结论为 BLOCK</div>
        </div>
        <div class="ag-kpi">
          <div class="ag-kpi__label">当前基线</div>
          <div class="ag-kpi__value" style="font-size: 18px">{{ overview.baseline ? `#${overview.baseline.id}` : '未设置' }}</div>
          <div class="ag-kpi__hint">{{ overview.baseline ? overview.baseline.targetName : '在报告页把一次测评设为基线' }}</div>
        </div>
      </section>

      <div class="ag-grid">
        <section class="ag-card">
          <div class="ag-card__head">
            <h2 class="ag-card__title">最近一次测评</h2>
            <router-link
              v-if="overview.latestRun"
              class="ag-btn"
              :to="`/guard/runs/${overview.latestRun.id}`"
            >查看报告</router-link>
          </div>

          <div v-if="overview.latestRun" class="ag-score">
            <div
              class="ag-ring"
              :style="{ '--ag-ring-value': overview.latestRun.score ?? 0, '--ag-ring-color': scoreColor(overview.latestRun.score) }"
            >
              <div class="ag-ring__inner">
                <div class="ag-ring__value">{{ overview.latestRun.score ?? '—' }}</div>
                <div class="ag-ring__unit">安全分 / 100</div>
              </div>
            </div>
            <div class="ag-meta" style="flex: 1">
              <div class="ag-meta__row">
                <span>目标</span>
                <span>{{ overview.latestRun.targetName }}</span>
              </div>
              <div class="ag-meta__row">
                <span>套件 / 状态</span>
                <span>{{ suiteLabel(overview.latestRun.suite) }} · {{ statusLabel(overview.latestRun.status) }}</span>
              </div>
              <div class="ag-meta__row">
                <span>风险等级</span>
                <span class="ag-pill" :class="riskPillClass(overview.latestRun.riskLevel)">
                  {{ riskLabel(overview.latestRun.riskLevel) }}
                </span>
              </div>
              <div class="ag-meta__row">
                <span>通过 / 失败 / 异常</span>
                <span>{{ overview.latestRun.passedCases }} / {{ overview.latestRun.failedCases }} / {{ overview.latestRun.errorCases }}</span>
              </div>
              <div class="ag-meta__row">
                <span>完成时间</span>
                <span>{{ overview.latestRun.finishedAt || overview.latestRun.createdAt || '—' }}</span>
              </div>
            </div>
          </div>
          <p v-else class="ag-note">暂无测评记录。</p>
        </section>

        <section class="ag-card">
          <div class="ag-card__head">
            <h2 class="ag-card__title">类别安全分</h2>
            <span class="ag-card__sub">最近一次已完成测评</span>
          </div>
          <div v-if="overview.categoryScores.length" class="ag-bars">
            <div v-for="item in overview.categoryScores" :key="item.category">
              <div class="ag-bar__head">
                <span>{{ item.label }}</span>
                <span class="ag-mono">{{ item.score }} · {{ item.total - item.failed - item.error }}/{{ item.total }} 通过</span>
              </div>
              <div class="ag-bar__track">
                <div
                  class="ag-bar__fill"
                  :class="{ 'is-low': item.score < 60, 'is-mid': item.score >= 60 && item.score < 85 }"
                  :style="{ width: `${item.score}%` }"
                ></div>
              </div>
            </div>
          </div>
          <p v-else class="ag-note">完成一次测评后展示各类别得分。</p>
        </section>
      </div>

      <div class="ag-grid" style="margin-top: 14px">
        <section class="ag-card">
          <div class="ag-card__head">
            <h2 class="ag-card__title">安全分趋势</h2>
            <span class="ag-card__sub">最近 {{ overview.trend.length }} 次已完成测评</span>
          </div>
          <div v-if="overview.trend.length">
            <svg viewBox="0 0 260 64" width="100%" height="74" role="img" aria-label="安全分趋势">
              <polyline
                :points="trendPoints"
                fill="none"
                stroke="var(--ag-primary)"
                stroke-width="2"
                stroke-linejoin="round"
                stroke-linecap="round"
              />
              <circle
                v-for="point in trendDots"
                :key="point.id"
                :cx="point.x"
                :cy="point.y"
                r="2.6"
                fill="var(--ag-primary)"
              />
            </svg>
            <div class="ag-note" style="display: flex; justify-content: space-between">
              <span>最低 {{ trendMin }}</span>
              <span>最高 {{ trendMax }}</span>
            </div>
          </div>
          <p v-else class="ag-note">暂无已完成测评。</p>
        </section>

        <section class="ag-card">
          <div class="ag-card__head">
            <h2 class="ag-card__title">高风险发现</h2>
            <span class="ag-card__sub">最近一次测评</span>
          </div>
          <div v-if="overview.riskFindings.length">
            <div v-for="item in overview.riskFindings" :key="item.caseId" class="ag-item">
              <div class="ag-item__head">
                <p class="ag-item__title">{{ item.title }}</p>
                <span class="ag-pill" :class="severityPillClass(item.severity)">{{ item.severityLabel }}</span>
              </div>
              <div class="ag-item__meta">
                <span>{{ item.categoryLabel }}</span>
                <span class="ag-mono">{{ item.caseId }}</span>
                <span>风险值 {{ item.riskScore }}</span>
              </div>
            </div>
          </div>
          <p v-else class="ag-note">
            {{ overview.latestSummary ? '最近一次测评没有失败用例。' : '完成一次测评后展示失败用例。' }}
          </p>
        </section>
      </div>
    </template>

    <p v-else-if="loading" class="ag-note">加载中…</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getGuardOverview } from '../../api/guard'
import type { GuardOverview } from '../../api/guard'
import './guard.css'

const overview = ref<GuardOverview | null>(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await getGuardOverview()
    overview.value = response.data as GuardOverview
  } catch (exception: unknown) {
    error.value = exception instanceof Error ? exception.message : '加载测评总览失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const trendValues = computed(() => (overview.value?.trend ?? []).map(item => item.score ?? 0))
const trendMin = computed(() => (trendValues.value.length ? Math.min(...trendValues.value) : 0))
const trendMax = computed(() => (trendValues.value.length ? Math.max(...trendValues.value) : 0))

function pointAt(index: number, score: number, total: number) {
  const x = total <= 1 ? 130 : 10 + (index / (total - 1)) * 240
  const y = 54 - (Math.max(0, Math.min(100, score)) / 100) * 44
  return { x, y }
}

const trendDots = computed(() => trendValues.value.map((score, index) => ({
  id: index,
  ...pointAt(index, score, trendValues.value.length)
})))

const trendPoints = computed(() => trendDots.value.map(point => `${point.x},${point.y}`).join(' '))

function scoreColor(score: number | null) {
  if (score === null || score === undefined) return 'var(--ag-muted)'
  if (score >= 90) return 'var(--ag-pass)'
  if (score >= 75) return 'var(--ag-warn)'
  return 'var(--ag-fail)'
}

function riskLabel(level: string | null) {
  return ({ LOW: '低风险', MEDIUM: '中风险', HIGH: '高风险', CRITICAL: '严重' } as Record<string, string>)[level ?? ''] ?? '未评级'
}

function riskPillClass(level: string | null) {
  if (level === 'LOW') return 'ag-pill--pass'
  if (level === 'MEDIUM') return 'ag-pill--warn'
  if (level === 'HIGH' || level === 'CRITICAL') return 'ag-pill--fail'
  return 'ag-pill--muted'
}

function severityPillClass(severity: string) {
  if (severity === 'CRITICAL' || severity === 'HIGH') return 'ag-pill--fail'
  if (severity === 'MEDIUM') return 'ag-pill--warn'
  return 'ag-pill--info'
}

function suiteLabel(suite: string) {
  return ({ SMOKE: '冒烟 6 条', STANDARD: '标准 12 条', FULL: '全量 24 条' } as Record<string, string>)[suite] ?? suite
}

function statusLabel(status: string) {
  return ({ QUEUED: '排队中', RUNNING: '执行中', COMPLETED: '已完成', FAILED: '失败' } as Record<string, string>)[status] ?? status
}
</script>
