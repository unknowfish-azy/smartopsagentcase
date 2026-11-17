<template>
  <section class="task-panel" aria-labelledby="robot-task-title">
    <div class="panel-head">
      <h2 id="robot-task-title">自主巡检任务</h2>
      <div class="head-actions">
        <button type="button" class="btn btn-primary" :disabled="!canStart" @click="startDefault">
          开始默认环形巡检
        </button>
        <button type="button" class="btn" :disabled="!tasks.length" @click="reload">刷新</button>
      </div>
    </div>

    <p v-if="!canStart && mode !== 'IDLE'" class="hint-text">
      仅 IDLE 且桥在线时可启动自主巡检（当前态 {{ mode }}）
    </p>
    <p v-else-if="!canStart && !bridgeConnected" class="hint-text">桥未连接，无法启动任务</p>

    <table v-if="tasks.length" class="task-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>状态</th>
          <th>进度</th>
          <th>路点数</th>
          <th>计划</th>
          <th>时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="task in tasks" :key="task.id">
          <td><code>{{ task.id }}</code></td>
          <td>
            <span class="pill" :class="statusPillClass(task.status)">{{ task.status }}</span>
          </td>
          <td class="progress-cell">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: progressPct(task) + '%' }"></div>
            </div>
            <span class="progress-text">{{ task.progress || 0 }}/{{ routeCount(task) }}</span>
          </td>
          <td>{{ routeCount(task) }}</td>
          <td class="mono">{{ task.plan_id || '—' }}</td>
          <td class="muted">{{ task.updated_at || task.created_at }}</td>
          <td>
            <div class="task-actions">
              <button
                v-if="task.status === 'RUNNING'"
                type="button"
                class="btn btn-sm"
                :disabled="busy"
                @click="pause(task.id)"
              >暂停</button>
              <button
                v-if="task.status === 'PAUSED'"
                type="button"
                class="btn btn-sm"
                :disabled="busy"
                @click="resume(task.id)"
              >续跑</button>
              <button
                v-if="task.status === 'RUNNING' || task.status === 'PAUSED'"
                type="button"
                class="btn btn-sm btn-danger"
                :disabled="busy"
                @click="cancel(task.id)"
              >取消</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="hint-text">暂无任务记录</p>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  cancelRobotTask,
  getRobotTasks,
  pauseRobotTask,
  resumeRobotTask,
  submitRobotTask
} from '../../api/robot'

const props = defineProps({
  deviceKey: { type: String, required: true },
  mode: { type: String, default: 'OFFLINE' },
  bridgeConnected: { type: Boolean, default: false }
})

const emit = defineEmits(['task-started'])

const tasks = ref([])
const busy = ref(false)

const canStart = computed(() => props.mode === 'IDLE' && props.bridgeConnected)

function reload() {
  if (!props.deviceKey) return
  getRobotTasks(props.deviceKey).then(r => { tasks.value = r?.data || [] }).catch(() => {})
}

function statusPillClass(status) {
  if (status === 'RUNNING') return 'pill-ok'
  if (status === 'PAUSED') return 'pill-warn'
  if (status === 'FAILED' || status === 'CANCELLED') return 'pill-danger'
  return 'pill-neutral'
}

function routeCount(task) {
  try {
    const r = task.route
    if (!r) return 0
    if (typeof r === 'string') return JSON.parse(r).length
    return Array.isArray(r) ? r.length : 0
  } catch { return 0 }
}

function progressPct(task) {
  const total = routeCount(task) || 1
  return Math.round(((task.progress || 0) / total) * 100)
}

async function startDefault() {
  busy.value = true
  try {
    await submitRobotTask(props.deviceKey, null, null)
    emit('task-started')
    reload()
  } catch (e) {
    const message = e?.message || '任务启动失败'
    alert(message)
  } finally {
    busy.value = false
  }
}

async function pause(id) {
  busy.value = true
  try { await pauseRobotTask(id); reload() }
  finally { busy.value = false }
}
async function resume(id) {
  busy.value = true
  try { await resumeRobotTask(id); reload() }
  finally { busy.value = false }
}
async function cancel(id) {
  busy.value = true
  try { await cancelRobotTask(id); reload() }
  finally { busy.value = false }
}

onMounted(reload)
watch(() => props.deviceKey, reload)
</script>

<style scoped>
.task-panel {
  padding: var(--ds-card-padding, var(--ds-space-4));
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
}

.panel-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-3);
  margin-bottom: var(--ds-space-3);
}

.panel-head h2 { margin: 0; font-size: var(--ds-font-lg); }
.head-actions { display: flex; gap: var(--ds-space-2); }

.btn {
  height: var(--ds-control-height, 36px);
  padding: 0 var(--ds-space-4);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-size: var(--ds-font-sm);
  cursor: pointer;
}
.btn:hover:not(:disabled) { border-color: var(--ds-color-primary); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-sm { height: 28px; padding: 0 var(--ds-space-3); font-size: var(--ds-font-xs); }
.btn-primary { border-color: var(--ds-color-primary); background: rgba(36, 150, 237, 0.14); }
.btn-danger { border-color: rgba(220, 132, 144, 0.5); color: var(--ds-color-danger); }

.task-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--ds-font-sm);
}
.task-table th, .task-table td {
  padding: var(--ds-space-2) var(--ds-space-3);
  text-align: left;
  border-bottom: 1px solid var(--ds-color-border);
  vertical-align: middle;
}
.task-table th { color: var(--ds-color-muted); font-size: var(--ds-font-xs); font-weight: 500; }

.progress-cell { display: flex; align-items: center; gap: var(--ds-space-2); min-width: 160px; }
.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--ds-color-surface-raised);
  border-radius: 3px;
  overflow: hidden;
}
.progress-fill { height: 100%; background: var(--ds-color-primary); transition: width .2s ease; }
.progress-text { color: var(--ds-color-muted); font-size: var(--ds-font-xs); font-variant-numeric: tabular-nums; }

.mono { font-family: var(--ds-font-mono, ui-monospace, monospace); font-size: var(--ds-font-xs); }
.muted { color: var(--ds-color-muted); font-size: var(--ds-font-xs); }

.task-actions { display: flex; gap: var(--ds-space-2); }

.pill {
  display: inline-flex;
  padding: 2px var(--ds-space-2);
  border-radius: var(--ds-radius-pill);
  font-size: var(--ds-font-xs);
  white-space: nowrap;
}
.pill-ok { background: rgba(139, 207, 180, 0.16); color: var(--ds-color-success); }
.pill-warn { background: rgba(217, 185, 109, 0.16); color: var(--ds-color-warning); }
.pill-danger { background: rgba(220, 132, 144, 0.16); color: var(--ds-color-danger); }
.pill-neutral { background: var(--ds-pill-neutral-bg, rgba(159, 190, 207, 0.12)); color: var(--ds-color-muted); }

.hint-text { margin: 0; color: var(--ds-color-muted); font-size: var(--ds-font-xs); line-height: var(--ds-line-base); }

@media (max-width: 960px) {
  .task-table th:nth-child(4), .task-table td:nth-child(4),
  .task-table th:nth-child(5), .task-table td:nth-child(5) { display: none; }
}
</style>
