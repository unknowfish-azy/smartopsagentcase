<template>
  <el-dialog
    :model-value="open"
    title="设备详情"
    width="min(560px, calc(100vw - 32px))"
    class="rdd-dialog"
    append-to-body
    destroy-on-close
    @update:model-value="!$event && emit('close')"
  >
    <section class="rdd-body">
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

      <!-- 实时遥测：父级传入的真实数据（控制台 WS / 台账 REST 轮询），无遥测即如实标注 -->
      <h3>实时遥测</h3>
      <dl class="rdd-facts">
        <div><dt>运行态</dt><dd>{{ modeLabel }}</dd></div>
        <div>
          <dt>心跳</dt>
          <dd>
            <span class="pill" :class="heartbeatClass">
              {{ telemetry ? (stale ? '心跳超时' : '心跳正常') : '无遥测' }}
            </span>
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
    </section>
    <template #footer>
      <el-button @click="emit('close')">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 机器人设备详情弹窗（3D 面板配套）。
 *
 * 数据全部来自真实链路：台账信息在打开时请求 GET /api/robot/devices 并按 deviceKey 匹配；
 * 遥测/路线由父级（RobotScene3D）传入，无数据即如实显示「—」，不伪造。
 */
import { computed, ref, watch } from 'vue'
import { getRobotDevices } from '../../api/robot'

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

watch(() => props.open, (isOpen) => {
  if (isOpen) loadLedger()
})

const formFactorLabel = computed(() =>
  FORM_FACTOR_LABELS[props.formFactor] || (props.formFactor || '未知形态')
)

const modeLabel = computed(() => MODE_LABELS[props.mode] || props.mode)

const heartbeatClass = computed(() => {
  if (!props.telemetry) return 'pill-neutral'
  return props.stale ? 'pill-warning' : 'pill-ok'
})

const batteryText = computed(() => {
  const raw = props.telemetry?.battery
  if (raw === undefined || raw === null) return '—'
  const ratio = Number(raw)
  if (!Number.isFinite(ratio)) return '—'
  const percent = ratio <= 1 ? ratio * 100 : ratio
  return `${Math.round(percent)}%`
})

const poseText = computed(() => {
  const pose = props.telemetry?.pose
  if (!pose) return '—'
  const x = Number(pose.x)
  const y = Number(pose.y)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return '—'
  return `${x.toFixed(1)} / ${y.toFixed(1)}`
})

const headingText = computed(() => {
  const theta = Number(props.telemetry?.pose?.theta)
  if (!Number.isFinite(theta)) return '—'
  return `${theta.toFixed(0)}°`
})

const obstacleText = computed(() => {
  const raw = props.telemetry?.obstacleDistance
  if (raw === undefined || raw === null) return '—'
  const value = Number(raw)
  if (!Number.isFinite(value)) return '—'
  return `${value.toFixed(2)} m`
})

const doneCount = computed(() => props.waypoints.filter((p) => p?.done).length)
const detourCount = computed(() => props.waypoints.filter((p) => p?.detour).length)
</script>

<style scoped>
.rdd-body { display: grid; gap: 10px; color: var(--smart-text, var(--ds-color-text)); overflow-wrap: anywhere; }
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
@media (max-width: 500px) { .rdd-facts { grid-template-columns: 1fr; } }
</style>
