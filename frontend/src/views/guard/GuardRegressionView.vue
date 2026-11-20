<template>
  <div class="ag-shell">
    <header class="ag-head">
      <div>
        <p class="ag-eyebrow">REGRESSION · 基线比对 · 发布门禁</p>
        <h1 class="ag-title">回归验证</h1>
        <p class="ag-lede">
          选择一个已完成的测评，与同目标基线逐条比对：新增失败、已修复、持续失败一目了然；
          新增高危失败或安全分显著下降时，门禁结论直接给出 BLOCK。
        </p>
      </div>
      <div class="ag-actions">
        <router-link class="ag-btn" to="/guard/runs">测评任务</router-link>
        <router-link class="ag-btn" to="/guard">返回总览</router-link>
      </div>
    </header>

    <div v-if="error" class="ag-error">{{ error }}</div>

    <section class="ag-card">
      <div class="ag-card__head">
        <h2 class="ag-card__title">选择要比对的测评</h2>
        <span class="ag-card__sub">仅列出已完成的测评</span>
      </div>
      <div v-if="completedRuns.length" class="ag-form">
        <div class="ag-field">
          <label for="regression-run">本次测评</label>
          <select id="regression-run" v-model="selectedId" @change="loadRegression">
            <option v-for="run in completedRuns" :key="run.id" :value="String(run.id)">
              #{{ run.id }} · {{ run.targetName }} · 安全分 {{ run.score ?? '—' }}{{ run.baseline ? ' · 基线' : '' }}
            </option>
          </select>
        </div>
        <button class="ag-btn" :disabled="loading || !selectedId" @click="loadRegression">
          {{ loading ? '比对中…' : '重新比对' }}
        </button>
      </div>
      <div v-else-if="!loading" class="ag-empty">
        <h2>还没有已完成的测评</h2>
        <p>先到「测评任务」跑一次完整测评，再把稳定结果设为基线，才能启用回归门禁。</p>
        <router-link class="ag-btn ag-btn--primary" to="/guard/runs">去发起测评</router-link>
      </div>
      <p v-else class="ag-note">加载中…</p>
    </section>

    <template v-if="regression">
      <div v-if="regression.available" class="ag-verdict" :class="`ag-verdict--${(regression.verdict || 'pass').toLowerCase()}`" style="margin-top: 14px">
        <h2 class="ag-verdict__title">{{ verdictTitle(regression.verdict) }}</h2>
        <p class="ag-verdict__text">{{ regression.summary }}</p>
      </div>
      <div v-else class="ag-verdict ag-verdict--regression" style="margin-top: 14px">
        <h2 class="ag-verdict__title">暂无可比对基线</h2>
        <p class="ag-verdict__text">{{ regression.reason }}</p>
        <p class="ag-verdict__text">
          <router-link class="ag-btn" :to="`/guard/runs/${selectedId}`">打开本次报告并设为基线</router-link>
        </p>
      </div>

      <section v-if="regression.available" class="ag-kpis" style="margin-top: 14px">
        <div class="ag-kpi">
          <div class="ag-kpi__label">基线安全分</div>
          <div class="ag-kpi__value">{{ regression.baselineScore }}</div>
          <div class="ag-kpi__hint">#{{ regression.baseline?.id }}</div>
        </div>
        <div class="ag-kpi">
          <div class="ag-kpi__label">本次安全分</div>
          <div class="ag-kpi__value">{{ regression.currentScore }}</div>
          <div class="ag-kpi__hint">#{{ regression.current?.id }}</div>
        </div>
        <div class="ag-kpi">
          <div class="ag-kpi__label">分数变化</div>
          <div class="ag-kpi__value" :style="{ color: (regression.delta ?? 0) < 0 ? 'var(--ag-fail)' : 'var(--ag-pass)' }">
            {{ formatDelta(regression.delta) }}
          </div>
          <div class="ag-kpi__hint">相对基线</div>
        </div>
        <div class="ag-kpi">
          <div class="ag-kpi__label">门禁结论</div>
          <div class="ag-kpi__value" style="font-size: 20px">{{ regression.verdict }}</div>
          <div class="ag-kpi__hint">{{ verdictTitle(regression.verdict) }}</div>
        </div>
      </section>

      <div v-if="regression.available" class="ag-cols" style="margin-top: 14px">
        <section class="ag-card">
          <div class="ag-card__head">
            <h2 class="ag-card__title">新增失败</h2>
            <span class="ag-pill ag-pill--fail">{{ regression.newFailures?.length ?? 0 }}</span>
          </div>
          <div v-if="regression.newFailures && regression.newFailures.length">
            <div v-for="item in regression.newFailures" :key="item.caseId" class="ag-item">
              <div class="ag-item__head">
                <p class="ag-item__title">{{ item.title }}</p>
                <span class="ag-pill ag-pill--fail">{{ item.severityLabel }}</span>
              </div>
              <div class="ag-item__meta">
                <span class="ag-mono">{{ item.caseId }}</span>
                <span>{{ item.categoryLabel }}</span>
                <span>{{ diffTransition(item) }}</span>
              </div>
            </div>
          </div>
          <p v-else class="ag-note">没有新增失败。</p>
        </section>

        <section class="ag-card">
          <div class="ag-card__head">
            <h2 class="ag-card__title">已修复</h2>
            <span class="ag-pill ag-pill--pass">{{ regression.fixed?.length ?? 0 }}</span>
          </div>
          <div v-if="regression.fixed && regression.fixed.length">
            <div v-for="item in regression.fixed" :key="item.caseId" class="ag-item">
              <div class="ag-item__head">
                <p class="ag-item__title">{{ item.title }}</p>
                <span class="ag-pill ag-pill--pass">{{ item.severityLabel }}</span>
              </div>
              <div class="ag-item__meta">
                <span class="ag-mono">{{ item.caseId }}</span>
                <span>{{ item.categoryLabel }}</span>
                <span>{{ diffTransition(item) }}</span>
              </div>
            </div>
          </div>
          <p v-else class="ag-note">本次没有已修复项。</p>
        </section>

        <section class="ag-card">
          <div class="ag-card__head">
            <h2 class="ag-card__title">持续失败</h2>
            <span class="ag-pill ag-pill--warn">{{ regression.persisting?.length ?? 0 }}</span>
          </div>
          <div v-if="regression.persisting && regression.persisting.length">
            <div v-for="item in regression.persisting" :key="item.caseId" class="ag-item">
              <div class="ag-item__head">
                <p class="ag-item__title">{{ item.title }}</p>
                <span class="ag-pill ag-pill--warn">{{ item.severityLabel }}</span>
              </div>
              <div class="ag-item__meta">
                <span class="ag-mono">{{ item.caseId }}</span>
                <span>{{ item.categoryLabel }}</span>
                <span>{{ diffTransition(item) }}</span>
              </div>
            </div>
          </div>
          <p v-else class="ag-note">没有持续失败项。</p>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getGuardRegression, getGuardRuns } from '../../api/guard'
import type { GuardRun } from '../../api/guard'
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
  current?: GuardRun
}

const runs = ref<GuardRun[]>([])
const selectedId = ref('')
const regression = ref<RegressionPayload | null>(null)
const loading = ref(false)
const error = ref('')

const completedRuns = computed(() => runs.value.filter(run => run.status === 'COMPLETED'))

async function loadRuns() {
  loading.value = true
  try {
    const response = await getGuardRuns(60)
    runs.value = response.data as GuardRun[]
    if (!selectedId.value && completedRuns.value.length) {
      selectedId.value = String(completedRuns.value[0].id)
    }
    if (selectedId.value) {
      await loadRegression()
    }
  } catch (exception: unknown) {
    error.value = exception instanceof Error ? exception.message : '加载测评记录失败'
  } finally {
    loading.value = false
  }
}

async function loadRegression() {
  if (!selectedId.value) return
  loading.value = true
  error.value = ''
  try {
    const response = await getGuardRegression(selectedId.value)
    regression.value = response.data as RegressionPayload
  } catch (exception: unknown) {
    error.value = exception instanceof Error ? exception.message : '回归比对失败'
    regression.value = null
  } finally {
    loading.value = false
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

function diffTransition(item: RegressionDiff) {
  return `${item.beforeVerdict} → ${item.afterVerdict}`
}

onMounted(loadRuns)
</script>
