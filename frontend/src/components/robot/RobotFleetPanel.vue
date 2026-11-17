<template>
  <section class="fleet-panel" aria-labelledby="robot-fleet-title">
    <div class="panel-head">
      <h2 id="robot-fleet-title">机队调度</h2>
      <div class="head-actions">
        <button type="button" class="btn btn-primary" :disabled="!canSubmit" @click="submit">
          提交机队（{{ selectedKeys.length }} 台）
        </button>
        <button type="button" class="btn" @click="reload">刷新</button>
      </div>
    </div>

    <div class="device-picker">
      <div v-for="d in availableDevices" :key="d.deviceKey" class="device-chip"
           :class="{ selected: selectedKeys.includes(d.deviceKey), offline: !d.bridgeConnected }"
           @click="toggle(d.deviceKey)">
        <span class="chip-key">{{ d.deviceKey }}</span>
        <span class="chip-form-factor">{{ d.formFactor || 'ROBOT' }}</span>
        <span class="chip-bridge" :class="d.bridgeConnected ? 'bridge-on' : 'bridge-off'">
          {{ d.bridgeConnected ? '在线' : '离线' }}
        </span>
      </div>
      <p v-if="!availableDevices.length" class="hint-text">当前无可调度设备（请先启用并连接）</p>
    </div>

    <p class="hint-text">
      机队并发默认 {{ concurrency }}（smartops.robot.fleet-concurrency）。
      所有被选设备将归并到同一个 planId，全局 CANCEL 会同时 STOP 所有子任务。
    </p>

    <div v-if="lastPlan" class="plan-card">
      <div class="plan-head">
        <span class="plan-id mono">{{ lastPlan.planId }}</span>
        <span class="plan-summary">
          <span class="summary-ok">accept={{ lastPlan.acceptedCount }}</span>
          <span class="summary-fail">reject={{ lastPlan.rejectedCount }}</span>
        </span>
        <div class="plan-actions">
          <button v-if="hasRunning" type="button" class="btn btn-sm" :disabled="busy" @click="pause">全局暂停</button>
          <button v-if="hasRunning || hasPaused" type="button" class="btn btn-sm btn-danger" :disabled="busy" @click="cancel">全局取消</button>
        </div>
      </div>
      <table class="task-table">
        <thead>
          <tr><th>设备</th><th>状态</th><th>进度</th><th>信息</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in lastPlan.results" :key="r.deviceKey">
            <td class="mono">{{ r.deviceKey }}</td>
            <td>
              <span class="pill" v-if="r.accepted" :class="taskPillClass(r)">{{ taskStatus(r) }}</span>
              <span v-else class="pill pill-danger">REJECTED</span>
            </td>
            <td>{{ r.accepted && lastPlan.planSummary ? taskProgress(r.deviceKey) : '—' }}</td>
            <td class="muted">{{ r.message || (r.accepted ? `taskId=${r.taskId}` : '') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="historyPlans.length" class="history">
      <h3 class="history-title">最近 20 个 plan</h3>
      <table class="task-table">
        <thead><tr><th>planId</th><th>总数</th><th>RUNNING</th><th>PAUSED</th><th>DONE</th><th>FAILED</th><th>更新</th></tr></thead>
        <tbody>
          <tr v-for="p in historyPlans" :key="p.plan_id">
            <td class="mono">{{ p.plan_id }}</td>
            <td>{{ p.total }}</td>
            <td class="running-cell">{{ p.running || 0 }}</td>
            <td class="paused-cell">{{ p.paused || 0 }}</td>
            <td class="done-cell">{{ p.done || 0 }}</td>
            <td class="failed-cell">{{ p.failed || 0 }}</td>
            <td class="muted">{{ p.updated_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  cancelRobotFleet,
  getRobotDevices,
  getRobotFleetPlanStatus,
  pauseRobotFleet,
  submitRobotFleet
} from '../../api/robot'

const devices = ref([])
const selectedKeys = ref([])
const lastPlan = ref(null)
const historyPlans = ref([])
const concurrency = ref(3)
const busy = ref(false)

const availableDevices = computed(() => devices.value.filter(d => d.enabled !== false))
const canSubmit = computed(() => selectedKeys.value.length >= 2 && !busy.value)

function toggle(key) {
  const idx = selectedKeys.value.indexOf(key)
  if (idx >= 0) selectedKeys.value.splice(idx, 1)
  else selectedKeys.value.push(key)
}

async function loadDevices() {
  try {
    const r = await getRobotDevices()
    devices.value = r?.data || []
  } catch {}
}

async function reload() {
  await loadDevices()
  try {
    const r = await getRobotFleetPlanStatus()
    historyPlans.value = r?.data?.plans || []
    concurrency.value = r?.data?.concurrency || 3
  } catch {}
}

const hasRunning = computed(() =>
  lastPlan.value?.results?.some(r => r.accepted && lastPlan.value?.planSummary?.running > 0) ?? false)
const hasPaused = computed(() =>
  lastPlan.value?.results?.some(r => r.accepted && lastPlan.value?.planSummary?.paused > 0) ?? false)

function taskStatus(r) {
  if (!r.accepted) return 'REJECTED'
  const summary = lastPlan.value?.planSummary?.tasks
  if (!summary) return 'ACCEPTED'
  const t = summary.find(x => x.device_key === r.deviceKey)
  return t?.status || 'RUNNING'
}

function taskPillClass(r) {
  const s = taskStatus(r)
  if (s === 'DONE') return 'pill-ok'
  if (s === 'PAUSED') return 'pill-warn'
  if (s === 'FAILED' || s === 'CANCELLED') return 'pill-danger'
  return 'pill-neutral'
}

function taskProgress(deviceKey) {
  const tasks = lastPlan.value?.planSummary?.tasks || []
  const t = tasks.find(x => x.device_key === deviceKey)
  if (!t) return '—'
  const route = t.route ? JSON.parse(t.route) : []
  return `${t.progress || 0}/${route.length}`
}

async function submit() {
  busy.value = true
  try {
    const r = await submitRobotFleet(selectedKeys.value, null)
    lastPlan.value = r?.data
    reload()
  } catch (e) { alert(e?.message || '提交失败') }
  finally { busy.value = false }
}
async function pause() {
  if (!lastPlan.value) return
  busy.value = true
  try { await pauseRobotFleet(lastPlan.value.planId); reload() }
  finally { busy.value = false }
}
async function cancel() {
  if (!lastPlan.value) return
  busy.value = true
  try { await cancelRobotFleet(lastPlan.value.planId); reload() }
  finally { busy.value = false }
}

onMounted(reload)
</script>

<style scoped>
.fleet-panel { padding: var(--ds-card-padding, var(--ds-space-4)); border: 1px solid var(--ds-color-border); border-radius: var(--ds-radius-lg); background: var(--ds-color-surface); }
.panel-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--ds-space-3); margin-bottom: var(--ds-space-3); }
.panel-head h2 { margin: 0; font-size: var(--ds-font-lg); }
.head-actions { display: flex; gap: var(--ds-space-2); }
.device-picker { display: flex; flex-wrap: wrap; gap: var(--ds-space-2); margin-bottom: var(--ds-space-3); }
.device-chip {
  display: inline-flex; align-items: center; gap: var(--ds-space-2);
  padding: 6px var(--ds-space-3); border-radius: var(--ds-radius-md);
  border: 1px solid var(--ds-color-border-strong); background: var(--ds-color-surface-raised);
  font-size: var(--ds-font-xs); cursor: pointer; user-select: none;
  transition: border-color var(--ds-duration-fast) ease;
}
.device-chip:hover { border-color: var(--ds-color-primary); }
.device-chip.selected { border-color: var(--ds-color-primary); background: rgba(36,150,237,.12); }
.device-chip.offline { opacity: 0.55; }
.chip-form-factor { color: var(--ds-color-muted); font-size: 10px; }
.chip-bridge { font-size: 10px; padding: 1px 6px; border-radius: 10px; }
.chip-bridge.bridge-on { background: rgba(139,207,180,.16); color: var(--ds-color-success); }
.chip-bridge.bridge-off { background: rgba(159,190,207,.12); color: var(--ds-color-muted); }
.plan-card { border: 1px solid var(--ds-color-border); border-radius: var(--ds-radius-md); padding: var(--ds-space-3); margin-top: var(--ds-space-3); }
.plan-head { display: flex; flex-wrap: wrap; align-items: center; gap: var(--ds-space-3); margin-bottom: var(--ds-space-2); }
.plan-id { font-size: var(--ds-font-sm); font-weight: 500; }
.plan-summary { display: inline-flex; gap: var(--ds-space-3); font-size: var(--ds-font-xs); }
.summary-ok { color: var(--ds-color-success); }
.summary-fail { color: var(--ds-color-danger); }
.plan-actions { margin-left: auto; display: flex; gap: var(--ds-space-2); }

.task-table { width: 100%; border-collapse: collapse; font-size: var(--ds-font-sm); }
.task-table th, .task-table td { padding: var(--ds-space-2) var(--ds-space-3); text-align: left; border-bottom: 1px solid var(--ds-color-border); }
.task-table th { color: var(--ds-color-muted); font-size: var(--ds-font-xs); font-weight: 500; }
.mono { font-family: var(--ds-font-mono, ui-monospace, monospace); font-size: var(--ds-font-xs); }
.muted { color: var(--ds-color-muted); font-size: var(--ds-font-xs); }

.history { margin-top: var(--ds-space-4); }
.history-title { margin: 0 0 var(--ds-space-2); font-size: var(--ds-font-sm); color: var(--ds-color-muted); }
.running-cell { color: var(--ds-color-primary); font-variant-numeric: tabular-nums; }
.paused-cell { color: var(--ds-color-warning); font-variant-numeric: tabular-nums; }
.done-cell { color: var(--ds-color-success); font-variant-numeric: tabular-nums; }
.failed-cell { color: var(--ds-color-danger); font-variant-numeric: tabular-nums; }

.btn { height: var(--ds-control-height, 36px); padding: 0 var(--ds-space-4); border: 1px solid var(--ds-color-border-strong); border-radius: var(--ds-radius-md); background: var(--ds-color-surface-raised); color: var(--ds-color-text); font-size: var(--ds-font-sm); cursor: pointer; }
.btn:hover:not(:disabled) { border-color: var(--ds-color-primary); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-sm { height: 28px; padding: 0 var(--ds-space-3); font-size: var(--ds-font-xs); }
.btn-primary { border-color: var(--ds-color-primary); background: rgba(36,150,237,.14); }
.btn-danger { border-color: rgba(220,132,144,.5); color: var(--ds-color-danger); }

.pill { display: inline-flex; padding: 2px var(--ds-space-2); border-radius: var(--ds-radius-pill); font-size: var(--ds-font-xs); white-space: nowrap; }
.pill-ok { background: rgba(139,207,180,.16); color: var(--ds-color-success); }
.pill-warn { background: rgba(217,185,109,.16); color: var(--ds-color-warning); }
.pill-danger { background: rgba(220,132,144,.16); color: var(--ds-color-danger); }
.pill-neutral { background: var(--ds-pill-neutral-bg, rgba(159,190,207,.12)); color: var(--ds-color-muted); }
.hint-text { margin: var(--ds-space-2) 0 0; color: var(--ds-color-muted); font-size: var(--ds-font-xs); line-height: var(--ds-line-base); }

@media (max-width: 960px) {
  .task-table th:nth-child(4), .task-table td:nth-child(4) { display: none; }
}
</style>
