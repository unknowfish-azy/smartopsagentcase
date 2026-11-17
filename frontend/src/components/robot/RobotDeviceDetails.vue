<template>
  <Teleport to="body">
    <div v-if="open" class="rdd-mask" @click.self="emit('close')">
      <section class="rdd-panel" role="dialog" aria-modal="true" aria-labelledby="rdd-title">
        <header class="rdd-head">
          <h2 id="rdd-title">设备详情</h2>
          <button type="button" class="rdd-close" aria-label="关闭设备详情" @click="emit('close')">✕</button>
        </header>
        <div class="rdd-body">
      <!-- 台账信息：真实接口 GET /api/robot/devices，失败如实标注 -->
      <h3>台账信息</h3>
      <p v-if="ledger.state === 'loading'" class="rdd-note">正在加载设备台账…</p>
      <p v-else-if="ledger.state === 'error'" class="rdd-error" role="alert">台账不可用：{{ ledger.error }}</p>
      <p v-else-if="!ledger.device" class="rdd-note">台账中未找到该设备的登记记录</p>
      <dl v-else class="rdd-facts">
        <div><dt>名称</dt><dd>{{ ledger.device.name || '—' }}</dd></div>
        <div><dt>设备标识</dt><dd class="mono">{{ deviceKey || '—' }}</dd></div>
        <div><dt>形态</dt><dd>{{ formFactorLabel }}</dd></div>
        <div>
          <dt>登记状态</dt>
          <dd>
            <span class="pill" :class="ledger.device.enabled ? 'pill-ok' : 'pill-neutral'">
              {{ ledger.device.enabled ? '已启用' : '未启用' }}
            </span>
          </dd>
        </div>
        <div><dt>设备状态</dt><dd>{{ ledger.device.status || '—' }}</dd></div>
        <div><dt>最近上报</dt><dd>{{ ledger.device.lastSeenAt || '—' }}</dd></div>
      </dl>

      <!-- 实时遥测：父级实时流优先（控制台 WS / 台账轮询），无流时自拉 REST 快照兜底 -->
      <h3>实时遥测</h3>
      <dl class="rdd-facts">
        <div><dt>运行态</dt><dd>{{ modeLabel }}</dd></div>
        <div>
          <dt>心跳</dt>
          <dd>
            <span class="pill" :class="heartbeatClass">{{ heartbeatLabel }}</span>
          </dd>
        </div>
        <div><dt>电量</dt><dd>{{ batteryText }}</dd></div>
        <div><dt>位姿 X / Y</dt><dd>{{ poseText }}</dd></div>
        <div><dt>朝向</dt><dd>{{ headingText }}</dd></div>
        <div><dt>障碍距离</dt><dd>{{ obstacleText }}</dd></div>
      </dl>

      <!-- 任务路线：RobotScene3D 内部已加载的最新任务 route 汇总 -->
      <h3>任务路线</h3>
      <p v-if="!waypoints.length" class="rdd-note">暂无巡检路线。提交自主巡检任务后此处会显示路线汇总。</p>
      <p v-else class="rdd-note">
        共 {{ waypoints.length }} 个路点 · 已执行 {{ doneCount }} 个<template v-if="detourCount"> · {{ detourCount }} 个绕行点来自连续异常重规划</template>
      </p>

      <!-- 实时画面：GET /api/robot/.../frame 最新关键帧；弹窗打开期间轮询刷新，无帧/模拟画面均如实标注 -->
      <div class="rdd-frame-head">
        <h3>实时画面</h3>
        <div class="rdd-frame-bar">
          <label class="rdd-frame-toggle">
            <input v-model="frameAutoRefresh" type="checkbox">
            每 2s 自动刷新
          </label>
          <span v-if="frameAt" class="rdd-frame-time">刷新于 {{ frameAt }}</span>
          <button type="button" class="rdd-frame-refresh" :disabled="frame.state === 'loading'" @click="loadFrame">
            手动刷新
          </button>
        </div>
      </div>
      <p v-if="frame.state === 'loading'" class="rdd-note">正在获取最新关键帧…</p>
      <div v-else-if="frame.data?.imageBase64" class="rdd-frame">
        <img :src="frameSrc" alt="机器人最新关键帧">
        <span v-if="frame.data.simulated" class="pill pill-warning rdd-frame-tag">模拟画面</span>
      </div>
      <p v-else-if="frame.state === 'error'" class="rdd-error" role="alert">画面不可用：{{ frame.error }}</p>
      <p v-else class="rdd-note">暂无关键帧。设备回传画面后此处会显示最新一帧。</p>
      <p v-if="frame.data?.lastAnalysis?.summary" class="rdd-note">最近视觉结论：{{ frame.data.lastAnalysis.summary }}</p>

      <!-- 最近任务：GET /api/robot/.../tasks 真实任务记录（事件流仅存在于控制台 WS，弹窗不伪造） -->
      <h3>最近任务</h3>
      <p v-if="tasks.state === 'loading'" class="rdd-note">正在加载任务记录…</p>
      <p v-else-if="tasks.state === 'error'" class="rdd-error" role="alert">任务记录不可用：{{ tasks.error }}</p>
      <ul v-else-if="tasks.list.length" class="rdd-tasks">
        <li v-for="(task, index) in tasks.list" :key="task.id ?? index">
          <span class="pill" :class="taskPillClass(task.status)">{{ task.status || '未知' }}</span>
          <span class="rdd-task-progress">进度 {{ task.progress || 0 }}/{{ routeCount(task) }}</span>
          <span class="rdd-task-time">{{ task.updated_at || task.created_at || '—' }}</span>
        </li>
      </ul>
      <p v-else class="rdd-note">暂无巡检任务记录。</p>
        </div>
        <footer class="rdd-foot">
          <button type="button" class="rdd-action" @click="emit('close')">关闭</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup>
/**
 * 机器人设备详情弹窗（3D 面板配套）。
 *
 * 数据全部来自真实链路：台账/关键帧/任务记录在打开时请求真实 REST 接口；
 * 遥测/路线由父级（RobotScene3D）传入，无数据即如实显示「—」，不伪造。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getRobotDevices, getRobotFrame, getRobotLive, getRobotTasks } from '../../api/robot'

const props = defineProps({
  open: { type: Boolean, default: false },
  deviceKey: { type: String, default: '' },
  formFactor: { type: String, default: 'CAR' },
  mode: { type: String, default: 'OFFLINE' },
  telemetry: { type: Object, default: null },
  stale: { type: Boolean, default: true },
  waypoints: { type: Array, default: () => [] }
})

const emit = defineEmits(['close'])

const MODE_LABELS = {
  OFFLINE: '离线',
  IDLE: '空闲',
  AUTONOMOUS: '自主态',
  HUMAN_CONTROL: '人工态',
  E_STOP: '急停',
  FAULT: '故障'
}

const FORM_FACTOR_LABELS = {
  CAR: '巡检车',
  SPIDER: '巡检蜘蛛',
  DOG: '机器狗',
  ROBOT: '巡检机器人'
}

const ledger = ref({ state: 'loading', device: null, error: '' })
const frame = ref({ state: 'idle', data: null, error: '' })
const tasks = ref({ state: 'idle', list: [], error: '' })
/* REST 快照兜底：父级未传实时遥测（如台账页直接点行内详情）时，打开弹窗自拉一次 live 快照 */
const liveSnapshot = ref(null)

async function loadLedger() {
  if (!props.deviceKey) {
    ledger.value = { state: 'error', device: null, error: '未指定设备标识' }
    return
  }
  ledger.value = { state: 'loading', device: null, error: '' }
  try {
    const result = await getRobotDevices()
    const devices = Array.isArray(result?.data) ? result.data : []
    ledger.value = {
      state: 'ok',
      device: devices.find((d) => d?.deviceKey === props.deviceKey) || null,
      error: ''
    }
  } catch (error) {
    ledger.value = { state: 'error', device: null, error: error?.message || '接口请求失败' }
  }
}

async function loadFrame() {
  if (!props.deviceKey) return
  frame.value = { state: 'loading', data: frame.value.data, error: '' } /* 轮询时保留旧帧，避免闪烁 */
  try {
    const response = await getRobotFrame(props.deviceKey)
    frame.value = { state: 'ok', data: response?.data || null, error: '' }
    /* 只要查询成功就更新时间戳：无帧设备也能如实反映轮询活性 */
    frameAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (error) {
    frame.value = { state: 'error', data: null, error: error?.message || '接口请求失败' }
  }
}

/* ---- 画面轮询刷新：弹窗打开期间每 2s 拉一次关键帧，可暂停/手动 ---- */

const FRAME_POLL_MS = 2000
const frameAutoRefresh = ref(true)
const frameAt = ref('')
let framePollTimer = null

function startFramePoll() {
  stopFramePoll()
  if (!frameAutoRefresh.value || !props.open) return
  framePollTimer = window.setInterval(loadFrame, FRAME_POLL_MS)
}

function stopFramePoll() {
  if (framePollTimer) {
    window.clearInterval(framePollTimer)
    framePollTimer = null
  }
}

watch(frameAutoRefresh, () => startFramePoll())

async function loadTasks() {
  if (!props.deviceKey) return
  tasks.value = { state: 'loading', list: [], error: '' }
  try {
    const response = await getRobotTasks(props.deviceKey)
    const list = Array.isArray(response?.data) ? response.data : []
    tasks.value = { state: 'ok', list: list.slice(0, 5), error: '' }
  } catch (error) {
    tasks.value = { state: 'error', list: [], error: error?.message || '接口请求失败' }
  }
}

async function loadLiveSnapshot() {
  if (props.telemetry || !props.deviceKey) return /* 父级已有实时流（WS/轮询），不重复拉取 */
  try {
    const response = await getRobotLive(props.deviceKey)
    liveSnapshot.value = response?.data || null
  } catch {
    liveSnapshot.value = null /* 快照失败如实显示「无遥测」 */
  }
}

/* Esc 关闭：只在弹窗打开期间挂监听，避免常驻全局热键 */
function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
}

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    loadLedger()
    loadFrame()
    loadTasks()
    loadLiveSnapshot()
    startFramePoll()
    window.addEventListener('keydown', onKeydown)
  } else {
    stopFramePoll() /* 关闭即停轮询（组件随关随毁，此处双保险） */
    window.removeEventListener('keydown', onKeydown)
  }
})

onBeforeUnmount(() => {
  stopFramePoll()
  window.removeEventListener('keydown', onKeydown)
})

/* 遥测来源统一收敛：父级实时流优先，REST 快照兜底（快照的桥连接状态如实映射心跳） */
const effectiveTelemetry = computed(() => props.telemetry || liveSnapshot.value?.telemetry || null)
const effectiveMode = computed(() =>
  props.mode && props.mode !== 'OFFLINE' ? props.mode : (liveSnapshot.value?.mode || props.mode || 'OFFLINE')
)
const effectiveStale = computed(() =>
  props.telemetry ? props.stale : !liveSnapshot.value?.bridgeConnected
)
const heartbeatLabel = computed(() => {
  if (props.telemetry) return effectiveStale.value ? '心跳超时' : '心跳正常'
  if (liveSnapshot.value) return effectiveStale.value ? '桥离线（快照）' : '桥在线（快照）'
  return '无遥测'
})

const formFactorLabel = computed(() =>
  FORM_FACTOR_LABELS[props.formFactor] || (props.formFactor || '未知形态')
)

const modeLabel = computed(() => MODE_LABELS[effectiveMode.value] || effectiveMode.value)

const heartbeatClass = computed(() => {
  if (!effectiveTelemetry.value && !liveSnapshot.value) return 'pill-neutral'
  return effectiveStale.value ? 'pill-warning' : 'pill-ok'
})

const batteryText = computed(() => {
  const raw = effectiveTelemetry.value?.battery
  if (raw === undefined || raw === null) return '—'
  const ratio = Number(raw)
  if (!Number.isFinite(ratio)) return '—'
  const percent = ratio <= 1 ? ratio * 100 : ratio
  return `${Math.round(percent)}%`
})

const poseText = computed(() => {
  const pose = effectiveTelemetry.value?.pose
  if (!pose) return '—'
  const x = Number(pose.x)
  const y = Number(pose.y)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return '—'
  return `${x.toFixed(1)} / ${y.toFixed(1)}`
})

const headingText = computed(() => {
  const theta = Number(effectiveTelemetry.value?.pose?.theta)
  if (!Number.isFinite(theta)) return '—'
  return `${theta.toFixed(0)}°`
})

const obstacleText = computed(() => {
  const raw = effectiveTelemetry.value?.obstacleDistance
  if (raw === undefined || raw === null) return '—'
  const value = Number(raw)
  if (!Number.isFinite(value)) return '—'
  return `${value.toFixed(2)} m`
})

const doneCount = computed(() => props.waypoints.filter((p) => p?.done).length)
const detourCount = computed(() => props.waypoints.filter((p) => p?.detour).length)

const frameSrc = computed(() => {
  const data = frame.value.data
  if (!data?.imageBase64) return ''
  return `data:${data.mime || 'image/jpeg'};base64,${data.imageBase64}`
})

function taskPillClass(status) {
  if (status === 'RUNNING') return 'pill-ok'
  if (status === 'PAUSED') return 'pill-warning'
  if (status === 'FAILED') return 'pill-danger'
  return 'pill-neutral'
}

function routeCount(task) {
  try {
    const route = typeof task?.route === 'string' ? JSON.parse(task.route) : task?.route
    return Array.isArray(route) ? route.length : 0
  } catch {
    return 0
  }
}
</script>

<style scoped>
/* 自绘弹窗：不依赖 Element Plus 的样式装配，避免遮罩层盖住内容导致“点了没反应” */
.rdd-mask {
  position: fixed; inset: 0; z-index: 2400;
  display: flex; align-items: center; justify-content: center;
  padding: 16px; overflow: auto;
  background: rgba(8, 10, 14, .62); backdrop-filter: blur(2px);
}
.rdd-panel {
  width: min(560px, 100%); max-height: calc(100vh - 32px);
  display: flex; flex-direction: column;
  background: var(--smart-surface, var(--ds-color-surface, #15181d));
  color: var(--smart-text, var(--ds-color-text, #e8eaed));
  border: 1px solid var(--smart-border, var(--ds-color-border, #2a2f37));
  border-radius: 12px; box-shadow: 0 24px 60px rgba(0, 0, 0, .45);
  animation: rdd-in 160ms ease-out;
}
@keyframes rdd-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.rdd-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 16px; border-bottom: 1px solid var(--smart-border, var(--ds-color-border, #2a2f37));
}
.rdd-head h2 { margin: 0; font-size: 15px; font-weight: 600; }
.rdd-close {
  border: none; background: none; cursor: pointer; padding: 2px 8px; border-radius: 6px;
  color: var(--smart-muted, var(--ds-color-muted, #9aa0a6)); font-size: 13px; line-height: 1.4;
}
.rdd-close:hover, .rdd-close:focus-visible { color: var(--smart-text, #e8eaed); background: rgba(255, 255, 255, .08); }
.rdd-foot {
  display: flex; justify-content: flex-end; padding: 10px 16px;
  border-top: 1px solid var(--smart-border, var(--ds-color-border, #2a2f37));
}
.rdd-action {
  border: 1px solid var(--smart-border, var(--ds-color-border, #2a2f37));
  background: rgba(255, 255, 255, .04); color: inherit;
  padding: 6px 16px; border-radius: 8px; font-size: 13px; cursor: pointer;
}
.rdd-action:hover { border-color: var(--smart-primary-strong, var(--ds-color-primary, #2563eb)); }
.rdd-body { padding: 14px 16px; overflow: auto; display: grid; gap: 10px; color: var(--smart-text, var(--ds-color-text)); overflow-wrap: anywhere; }
.rdd-body h3 { margin: 6px 0 0; font-size: 14px; font-weight: 600; }
.rdd-facts { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 0; }
.rdd-facts dt { color: var(--smart-muted, var(--ds-color-muted)); font-size: 12px; }
.rdd-facts dd { margin: 6px 0 0; font-size: 13px; }
.rdd-note { margin: 0; color: var(--smart-muted, var(--ds-color-muted)); font-size: 12px; line-height: 1.7; }
.rdd-error { margin: 0; color: var(--smart-danger, #e5484d); font-size: 12px; }
.mono { font-family: Consolas, monospace; }
.pill { display: inline-flex; align-items: center; padding: 1px 10px; border-radius: 999px; font-size: 11px; white-space: nowrap; }
.pill-ok { background: var(--ds-pill-success-bg, rgba(92, 200, 133, .16)); color: var(--ds-pill-success-fg, #5cc885); }
.pill-warning { background: var(--ds-pill-warning-bg, rgba(227, 160, 8, .16)); color: var(--ds-pill-warning-fg, #e3a008); }
.pill-neutral { background: var(--ds-pill-neutral-bg, rgba(128, 134, 146, .16)); color: var(--smart-muted, var(--ds-color-muted)); }
.pill-danger { background: var(--ds-pill-danger-bg, rgba(229, 72, 77, .16)); color: var(--ds-pill-danger-fg, #e5484d); }

/* 实时画面缩略图 */
.rdd-frame-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 4px 12px; }
.rdd-frame-head h3 { margin: 6px 0 0; }
.rdd-frame-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.rdd-frame-toggle { display: inline-flex; align-items: center; gap: 5px; color: var(--smart-muted, var(--ds-color-muted)); font-size: 11px; cursor: pointer; }
.rdd-frame-time { color: var(--smart-muted, var(--ds-color-muted)); font-size: 11px; font-variant-numeric: tabular-nums; }
.rdd-frame-refresh {
  padding: 1px 10px;
  border: 1px solid var(--ds-color-border-strong, var(--smart-border-strong, #3a3f4a));
  border-radius: var(--ds-radius-pill, 999px);
  background: transparent;
  color: var(--ds-color-muted, var(--smart-muted));
  font-size: 11px;
  cursor: pointer;
  transition: color var(--ds-duration-fast, 150ms) var(--ds-ease-out, ease-out),
              border-color var(--ds-duration-fast, 150ms) var(--ds-ease-out, ease-out);
}
.rdd-frame-refresh:hover:not(:disabled),
.rdd-frame-refresh:focus-visible {
  color: var(--ds-color-primary, var(--smart-primary));
  border-color: var(--ds-color-primary, var(--smart-primary));
}
.rdd-frame-refresh:disabled { opacity: 0.55; cursor: not-allowed; }
.rdd-frame-refresh:focus-visible {
  outline: 2px solid var(--ds-focus-ring-color, var(--smart-primary));
  outline-offset: 2px;
}
.rdd-frame { position: relative; display: inline-block; }
.rdd-frame img {
  display: block;
  max-width: 100%;
  max-height: 180px;
  border: 1px solid var(--smart-border, var(--ds-color-border));
  border-radius: 8px;
}
.rdd-frame-tag { position: absolute; top: 8px; right: 8px; }

/* 最近任务列表 */
.rdd-tasks { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.rdd-tasks li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 6px 10px;
  border: 1px solid var(--smart-border, var(--ds-color-border));
  border-radius: 6px;
  font-size: 12px;
}
.rdd-task-progress { color: var(--smart-text, var(--ds-color-text)); }
.rdd-task-time { margin-left: auto; color: var(--smart-muted, var(--ds-color-muted)); font-size: 11px; }
@media (max-width: 500px) { .rdd-facts { grid-template-columns: 1fr; } }
</style>
