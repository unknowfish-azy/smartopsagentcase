<template>
  <div class="ag-shell">
    <header class="ag-head">
      <div>
        <p class="ag-eyebrow">GUARD RUNS · 异步执行 · 逐条落库</p>
        <h1 class="ag-title">测评任务</h1>
        <p class="ag-lede">
          选择被测目标与套件发起测评。任务在后台按用例顺序执行，页面会自动刷新进度；
          每条结果都保留请求、响应、命中规则与判定结论。
        </p>
      </div>
      <div class="ag-actions">
        <router-link class="ag-btn" to="/guard/cases">查看用例库</router-link>
        <router-link class="ag-btn" to="/guard/regression">回归验证</router-link>
      </div>
    </header>

    <div v-if="error" class="ag-error">{{ error }}</div>

    <section class="ag-card">
      <div class="ag-card__head">
        <h2 class="ag-card__title">发起新测评</h2>
        <span class="ag-card__sub">同一个目标可重复测评，用于版本回归</span>
      </div>
      <div class="ag-form">
        <div class="ag-field">
          <label for="guard-target">被测目标</label>
          <select id="guard-target" v-model="selectedTarget">
            <option v-for="item in targets" :key="`${item.type}:${item.id}`" :value="`${item.type}:${item.id}`" :disabled="!item.available">
              {{ item.name }}{{ item.available ? '' : '（不可用）' }}
            </option>
          </select>
        </div>
        <div class="ag-field">
          <label for="guard-suite">测评套件</label>
          <select id="guard-suite" v-model="suite">
            <option value="SMOKE">冒烟 · 6 条（每类 1 条）</option>
            <option value="STANDARD">标准 · 12 条（每类 2 条）</option>
            <option value="FULL">全量 · 24 条</option>
          </select>
        </div>
        <label class="ag-field--check">
          <input v-model="markBaseline" type="checkbox" />
          完成后设为该目标基线
        </label>
        <button class="ag-btn ag-btn--primary" :disabled="creating || !selectedTarget" @click="submit">
          {{ creating ? '创建中…' : '开始测评' }}
        </button>
      </div>
      <p class="ag-note" style="margin: 10px 0 0">
        目标说明：{{ selectedTargetHint }}
      </p>
    </section>

    <section class="ag-card">
      <div class="ag-card__head">
        <h2 class="ag-card__title">测评记录</h2>
        <div class="ag-actions">
          <span v-if="polling" class="ag-pill ag-pill--info">自动刷新中</span>
          <button class="ag-btn" :disabled="loading" @click="loadRuns">刷新</button>
        </div>
      </div>

      <div v-if="runs.length" class="ag-table-wrap">
        <table class="ag-table">
          <thead>
            <tr>
              <th>#</th>
              <th>目标</th>
              <th>套件</th>
              <th>状态</th>
              <th>安全分</th>
              <th>风险</th>
              <th>回归</th>
              <th>通过 / 失败 / 异常</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in runs" :key="run.id" class="is-clickable" @click="openRun(run)">
              <td class="num">{{ run.id }}</td>
              <td>
                <div>{{ run.targetName }}</div>
                <div class="ag-note">{{ run.targetType }}</div>
              </td>
              <td>{{ suiteLabel(run.suite) }}</td>
              <td>
                <span class="ag-pill" :class="statusPillClass(run.status)">{{ statusLabel(run.status) }}</span>
                <span v-if="run.baseline" class="ag-pill ag-pill--info" style="margin-left: 4px">基线</span>
              </td>
              <td class="num">{{ run.score ?? '—' }}</td>
              <td>
                <span class="ag-pill" :class="riskPillClass(run.riskLevel)">{{ riskLabel(run.riskLevel) }}</span>
              </td>
              <td>
                <span v-if="run.regressionVerdict" class="ag-pill" :class="verdictPillClass(run.regressionVerdict)">
                  {{ run.regressionVerdict }}
                </span>
                <span v-else class="ag-note">—</span>
              </td>
              <td class="num">{{ run.passedCases }} / {{ run.failedCases }} / {{ run.errorCases }}</td>
              <td class="ag-mono">{{ run.createdAt || '—' }}</td>
              <td>
                <div class="ag-actions" @click.stop>
                  <router-link class="ag-btn" :to="`/guard/runs/${run.id}`">报告</router-link>
                  <button
                    v-if="run.status === 'COMPLETED' && !run.baseline"
                    class="ag-btn"
                    :disabled="busyId === run.id"
                    @click="setBaseline(run)"
                  >设为基线</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else-if="!loading" class="ag-empty" style="margin-top: 10px">
        <h2>还没有测评任务</h2>
        <p>在上方选择目标与套件，跑一次冒烟测评即可看到逐条判定结果。</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createGuardRun, getGuardRuns, getGuardTargets, markGuardBaseline } from '../../api/guard'
import type { GuardRun, GuardTarget } from '../../api/guard'
import './guard.css'

const router = useRouter()
const targets = ref<GuardTarget[]>([])
const runs = ref<GuardRun[]>([])
const selectedTarget = ref('')
const suite = ref('SMOKE')
const markBaseline = ref(false)
const loading = ref(false)
const creating = ref(false)
const busyId = ref<number | null>(null)
const error = ref('')
let timer: number | undefined

const polling = computed(() => runs.value.some(run => run.status === 'QUEUED' || run.status === 'RUNNING'))

const selectedTargetHint = computed(() => {
  const target = targets.value.find(item => `${item.type}:${item.id}` === selectedTarget.value)
  return target ? target.subtitle : '请选择一个可用目标'
})

async function loadTargets() {
  const response = await getGuardTargets()
  targets.value = response.data as GuardTarget[]
  if (!selectedTarget.value) {
    const first = targets.value.find(item => item.available)
    if (first) selectedTarget.value = `${first.type}:${first.id}`
  }
}

async function loadRuns() {
  loading.value = true
  try {
    const response = await getGuardRuns(40)
    runs.value = response.data as GuardRun[]
    error.value = ''
  } catch (exception: unknown) {
    error.value = exception instanceof Error ? exception.message : '加载测评任务失败'
  } finally {
    loading.value = false
    schedulePolling()
  }
}

function schedulePolling() {
  if (polling.value && timer === undefined) {
    timer = window.setInterval(() => { loadRuns() }, 2500)
  } else if (!polling.value && timer !== undefined) {
    window.clearInterval(timer)
    timer = undefined
  }
}

async function submit() {
  if (!selectedTarget.value) return
  const [targetType, targetId] = selectedTarget.value.split(':')
  creating.value = true
  error.value = ''
  try {
    const response = await createGuardRun({ targetType, targetId, suite: suite.value, markBaseline: markBaseline.value })
    const runId = (response.data as { runId: number }).runId
    markBaseline.value = false
    await loadRuns()
    router.push(`/guard/runs/${runId}`)
  } catch (exception: unknown) {
    error.value = exception instanceof Error ? exception.message : '创建测评失败'
  } finally {
    creating.value = false
  }
}

async function setBaseline(run: GuardRun) {
  busyId.value = run.id
  try {
    await markGuardBaseline(run.id)
    await loadRuns()
  } catch (exception: unknown) {
    error.value = exception instanceof Error ? exception.message : '设置基线失败'
  } finally {
    busyId.value = null
  }
}

function openRun(run: GuardRun) {
  router.push(`/guard/runs/${run.id}`)
}

function suiteLabel(value: string) {
  return ({ SMOKE: '冒烟', STANDARD: '标准', FULL: '全量' } as Record<string, string>)[value] ?? value
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

function riskLabel(value: string | null) {
  return ({ LOW: '低', MEDIUM: '中', HIGH: '高', CRITICAL: '严重' } as Record<string, string>)[value ?? ''] ?? '—'
}

function riskPillClass(value: string | null) {
  if (value === 'LOW') return 'ag-pill--pass'
  if (value === 'MEDIUM') return 'ag-pill--warn'
  if (value === 'HIGH' || value === 'CRITICAL') return 'ag-pill--fail'
  return 'ag-pill--muted'
}

function verdictPillClass(value: string) {
  if (value === 'PASS' || value === 'IMPROVED') return 'ag-pill--pass'
  if (value === 'REGRESSION') return 'ag-pill--warn'
  return 'ag-pill--fail'
}

onMounted(async () => {
  try {
    await loadTargets()
  } catch (exception: unknown) {
    error.value = exception instanceof Error ? exception.message : '加载被测目标失败'
  }
  await loadRuns()
})

onUnmounted(() => {
  if (timer !== undefined) window.clearInterval(timer)
})
</script>
