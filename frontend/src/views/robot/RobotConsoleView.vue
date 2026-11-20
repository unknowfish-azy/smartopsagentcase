<template>
  <section class="robot-console" aria-labelledby="robot-console-title">
    <header class="console-head">
      <div>
        <h1 id="robot-console-title" class="console-title">机器人控制台</h1>
        <p class="console-sub">
          人工态＝遥控（零模型调用）；自主态＝模型大脑（巡检＋拍照＋上报，运动决策后置）
        </p>
      </div>
      <div class="head-controls">
        <label class="field">
          <span class="field-label">设备</span>
          <select v-model="selectedKey" :disabled="!devices.length" @change="onDeviceChange">
            <option v-for="device in devices" :key="device.deviceKey" :value="device.deviceKey">
              {{ device.name }}（{{ formFactorLabel(device.formFactor) }}{{ device.enabled ? '' : '·未启用' }}）
            </option>
          </select>
        </label>
        <span class="pill" :class="wsState === 'open' ? 'pill-ok' : 'pill-warn'">
          {{ wsState === 'open' ? '控制通道已连接' : '控制通道未连接' }}
        </span>
        <button type="button" class="head-action" @click="activeTab = 'alerts'">
          预警
          <span v-if="fleetKpis.activeAlerts" class="head-badge">{{ fleetKpis.activeAlerts }}</span>
        </button>
        <button type="button" class="head-action primary" @click="assistantOpen = true">AI 助手</button>
        <button type="button" class="btn btn-ghost" @click="reload">刷新</button>
      </div>
    </header>

    <p v-if="errorMessage" class="banner banner-error" role="alert">{{ errorMessage }}</p>
    <p v-if="noticeMessage" class="banner banner-info" role="status">{{ noticeMessage }}</p>

    <div v-if="!devices.length" class="empty-state">
      暂无已登记的巡检机器人。请先在
      <RouterLink to="/devices">设备接入台账</RouterLink>
      登记设备并启用（需 admin.config 能力）。
    </div>

    <template v-else>
      <nav class="console-tabs" role="tablist" aria-label="机器人控制台分区">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === tab.key }"
          role="tab"
          :aria-selected="activeTab === tab.key"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span v-if="tab.key === 'alerts' && fleetKpis.activeAlerts" class="tab-badge">{{ fleetKpis.activeAlerts }}</span>
        </button>
      </nav>

      <!-- 总览：多设备孪生 + 态势卡 + 预警摘要 + 指标 -->
      <div v-if="activeTab === 'overview'" class="tab-panel overview-grid">
        <RobotTwinMap
          :devices="devices"
          :states="fleetStates"
          :selected-key="selectedKey"
          :trails="trails"
          :alerts="alerts"
          :route="activeRoute"
          :route-progress="activeRouteProgress"
          :draft="draftRoute"
          :running-tasks="fleetKpis.runningTasks"
          :active-alert-count="fleetKpis.activeAlerts"
          @select="selectDevice"
        />
        <div class="overview-side">
          <RobotFleetCards
            :devices="devices"
            :states="fleetStates"
            :selected-key="selectedKey"
            @select="selectDevice"
            @estop="quickEstop"
          />
          <RobotAlertCenter
            compact
            :alerts="alerts"
            :limit="6"
            @acknowledge="acknowledgeAlert"
            @restore="restoreAlert"
            @refresh="refreshAlerts"
            @select-device="selectDevice"
          />
        </div>
        <RobotMetricsPanel
          class="overview-metrics"
          :devices="devices"
          :states="fleetStates"
          :history="history"
          :alerts="alerts"
          :task-summary="taskSummary"
          :tasks="fleetTasks"
          :selected-key="selectedKey"
          @select="selectDevice"
        />
      </div>

      <!-- 操控：视觉 + 遥测 + 3D + 双态 + 遥控 -->
      <div v-else-if="activeTab === 'control'" class="console-grid">
      <!-- 左：视觉回传 + 遥测 -->
      <div class="panel-stack">
        <RobotVideoPanel
          :frame-src="frameSrc"
          :frame-at="lastFrameAt"
          :simulated="frameSimulated"
          :vision-configured="visionConfigured"
          :analysis="visionResult"
          :capture-disabled="!controllable"
          @capture="captureOnce"
        />

        <section class="panel" aria-labelledby="robot-hud-title">
          <div class="panel-head">
            <h2 id="robot-hud-title">遥测</h2>
            <span class="pill" :class="telemetryStale ? 'pill-warn' : 'pill-ok'">
              {{ telemetry ? (telemetryStale ? '心跳超时' : '心跳正常') : '无遥测' }}
            </span>
          </div>
          <dl class="hud-grid">
            <div class="hud-item">
              <dt>电量</dt>
              <dd :class="batteryClass">{{ batteryText }}</dd>
            </div>
            <div class="hud-item">
              <dt>位姿 X / Y</dt>
              <dd>{{ poseText }}</dd>
            </div>
            <div class="hud-item">
              <dt>朝向</dt>
              <dd>{{ headingText }}</dd>
            </div>
            <div class="hud-item">
              <dt>障碍距离</dt>
              <dd>{{ obstacleText }}</dd>
            </div>
          </dl>

          <!-- 形态专属遥测：巡检车轮速仪表 / 蜘蛛 8 足触地（字段来自模拟器或真机桥，缺失如实显示“—”） -->
          <section v-if="isCarForm" class="hud-extra" aria-label="巡检车轮速仪表">
            <div class="hud-extra-head">
              <h3>轮速仪表</h3>
              <span class="hud-extra-meta">
                轮径 {{ carWheelRadiusText }} · 轮距 {{ carTrackWidthText }}
              </span>
            </div>
            <div class="wheel-gauges">
              <WheelSpeedDial
                v-for="gauge in wheelGauges"
                :key="gauge.side"
                :label="gauge.label"
                :speed="gauge.speed"
                :angular="gauge.angular"
              />
            </div>
            <p class="hud-extra-meta">
              里程 {{ odometerText }} · LiDAR {{ lidarRpmText }}
            </p>
          </section>

          <section v-else-if="isSpiderForm" class="hud-extra" aria-label="蜘蛛 8 足触地状态">
            <div class="hud-extra-head">
              <h3>8 足触地</h3>
              <span class="hud-extra-meta">{{ spiderContactText }}</span>
            </div>
            <FootContactGrid :contacts="spiderFeet" />
            <p class="hud-extra-meta">
              步频 {{ spiderStrideText }} · 机身高度 {{ spiderBodyHeightText }} · 相位 {{ spiderPhaseText }}
            </p>
          </section>
        </section>

        <RobotScene3D
          :telemetry="telemetry"
          :stale="telemetryStale"
          :device-key="selectedKey"
          :form-factor="selectedDevice?.formFactor || 'CAR'"
          :mode="mode"
          :effects="effectConfig"
          :trail="trails[selectedKey] || []"
        />

        <RobotEffectTuner v-model="effectConfig" />
      </div>

      <!-- 右：双态 + 遥控 -->
      <div class="panel-stack">
        <section class="panel" aria-labelledby="robot-mode-title">
          <div class="panel-head">
            <h2 id="robot-mode-title">运行态</h2>
            <span class="pill" :class="modePillClass">{{ modeLabel }}</span>
          </div>
          <div class="mode-actions">
            <button
              type="button"
              class="btn"
              :class="mode === 'HUMAN_CONTROL' ? 'btn-active' : ''"
              :disabled="!canSwitchMode('HUMAN_CONTROL')"
              @click="changeMode('HUMAN_CONTROL')"
            >
              进入人工态
            </button>
            <button
              type="button"
              class="btn"
              :class="mode === 'AUTONOMOUS' ? 'btn-active' : ''"
              :disabled="!canSwitchMode('AUTONOMOUS')"
              @click="changeMode('AUTONOMOUS')"
            >
              进入自主态
            </button>
            <button
              type="button"
              class="btn btn-ghost"
              :disabled="mode !== 'E_STOP' && mode !== 'FAULT'"
              @click="resetDevice"
            >
              人工复位
            </button>
          </div>
          <p class="hint-text">
            双态互斥：进入人工态会自动暂停进行中的自主任务并先发一次 STOP，避免切态后仍按旧任务运动。
          </p>
        </section>

        <section class="panel" aria-labelledby="robot-drive-title">
          <div class="panel-head">
            <h2 id="robot-drive-title">遥控</h2>
            <span class="pill pill-neutral">{{ controllable ? '可操作' : '需先进入人工态' }}</span>
          </div>
          <div class="drive-area">
            <DeviceTeleopPanel
              class="drive-panel"
              :device="selectedDevice"
              :disabled="!controllable"
              @command="onTeleopCommand"
              @release="onTeleopRelease"
            />
            <div class="drive-side">
              <button type="button" class="estop" @click="emergencyStop" aria-label="急停">
                <span class="estop-label">E-STOP</span>
                <span class="estop-sub">立即停止</span>
              </button>
              <button type="button" class="btn" :disabled="!controllable" @click="speak">
                喊话
              </button>
              <button type="button" class="btn" :disabled="!controllable" @click="centerPtz">
                PTZ 回中
              </button>
            </div>
          </div>
          <p class="hint-text">
            各形态按自己的能力清单渲染：差速车只有前进+自转，四足/全向才有横移与步态。
            命令经白名单与参数钳位校验，超速/越界直接拒绝；每 200ms 需续传，断连即自动停止。
          </p>
        </section>

        <RobotTaskPanel
          v-if="selectedKey"
          :device-key="selectedKey"
          :mode="mode"
          :bridge-connected="bridgeConnected"
          @task-started="onTaskStarted"
        />

        <RobotVoiceBar v-if="selectedKey" :device-key="selectedKey" />

        <RobotFleetPanel v-if="devices.length" />
      </div>
    </div>

      <!-- 协同：多子智能体分工（巡检调度 / 设备诊断 / 合规审计） -->
      <div v-else-if="activeTab === 'orchestration'" class="tab-panel">
        <div class="panel">
          <div class="panel-head">
            <h2>多智能体协同</h2>
            <span class="pill">主管拆解 · 专家并行 · 汇总审计</span>
          </div>
          <AgentOrchestrationPanel
            :device-key="selectedKey"
            :device-keys="devices.map(device => device.deviceKey)"
          />
        </div>
      </div>

      <!-- 巡检：地图点选规划 + 任务跟踪 -->
      <div v-else-if="activeTab === 'patrol'" class="tab-panel">
        <div class="patrol-grid">
          <RobotTwinMap
            editable
            :devices="devices"
            :states="fleetStates"
            :selected-key="selectedKey"
            :trails="trails"
            :alerts="alerts"
            :route="activeRoute"
            :route-progress="activeRouteProgress"
            :draft="draftRoute"
            :running-tasks="fleetKpis.runningTasks"
            :active-alert-count="fleetKpis.activeAlerts"
            @select="selectDevice"
            @pick="addWaypoint"
            @remove-draft="removeWaypoint"
          />
          <RobotRoutePlanner
            :device-key="selectedKey"
            :mode="mode"
            :bridge-connected="bridgeConnected"
            :points="draftRoute"
            :editable="plannerEditable"
            @update:points="draftRoute = $event"
            @update:editable="plannerEditable = $event"
            @submitted="onRouteSubmitted"
          />
        </div>
        <div class="patrol-lower">
          <RobotTaskPanel
            v-if="selectedKey"
            :device-key="selectedKey"
            :mode="mode"
            :bridge-connected="bridgeConnected"
            @task-started="onTaskStarted"
          />
          <RobotFleetPanel v-if="devices.length" />
        </div>
      </div>

      <!-- 预警：统一预警流 -->
      <div v-else-if="activeTab === 'alerts'" class="tab-panel">
        <RobotAlertCenter
          :alerts="alerts"
          @acknowledge="acknowledgeAlert"
          @restore="restoreAlert"
          @refresh="refreshAlerts"
          @select-device="selectDevice"
        />
      </div>

      <!-- 分析：真实遥测指标 + 助手入口 -->
      <div v-else class="tab-panel analysis-grid">
        <RobotMetricsPanel
          :devices="devices"
          :states="fleetStates"
          :history="history"
          :alerts="alerts"
          :task-summary="taskSummary"
          :tasks="fleetTasks"
          :selected-key="selectedKey"
          @select="selectDevice"
        />
        <section class="panel assistant-cta" aria-labelledby="assistant-cta-title">
          <div class="panel-head">
            <h2 id="assistant-cta-title">平台助手</h2>
            <span class="pill pill-neutral">只读建议</span>
          </div>
          <p class="hint-text">
            把当前设备遥测、任务进度与未确认预警交给平台助手，快速获得排查路径与操作引导；不会直接下发控制指令。
          </p>
          <dl class="assistant-facts">
            <div><dt>当前设备</dt><dd>{{ selectedDevice?.name || '未选择' }}</dd></div>
            <div><dt>运行态</dt><dd>{{ modeLabel }}</dd></div>
            <div><dt>控制桥</dt><dd>{{ bridgeConnected ? '已连接' : '未连接' }}</dd></div>
            <div><dt>未确认预警</dt><dd>{{ fleetKpis.activeAlerts }}</dd></div>
          </dl>
          <div class="assistant-cta-actions">
            <button type="button" class="btn btn-active" @click="assistantOpen = true">打开平台助手</button>
            <RouterLink to="/log-diagnosis" class="btn btn-ghost link-btn">日志诊断</RouterLink>
          </div>
        </section>
      </div>
    </template>

    <!-- 底部：事件流 -->
    <section v-if="devices.length" class="panel" aria-labelledby="robot-events-title">
      <div class="panel-head">
        <h2 id="robot-events-title">事件流</h2>
        <span class="pill pill-neutral">最近 {{ events.length }} 条</span>
      </div>
      <ul v-if="events.length" class="event-list">
        <li v-for="(item, index) in events" :key="index" class="event-item">
          <span class="event-time">{{ item.time }}</span>
          <span class="pill" :class="item.level === 'error' ? 'pill-danger' : 'pill-neutral'">{{ item.tag }}</span>
          <span class="event-text">{{ item.text }}</span>
        </li>
      </ul>
      <p v-else class="hint-text">暂无事件。桥连接、模式切换、命令拒绝与设备上报都会记录在此。</p>
    </section>

    <RobotAssistantPanel
      :open="assistantOpen"
      :context-summary="assistantSummary"
      :context-payload="assistantContextPayload"
      :device-name="selectedDevice?.name || ''"
      @close="assistantOpen = false"
    />
  <AgentCopilotDock
    section="机器人控制台"
    :entity="{ type: 'device', id: selectedKey || devices?.[0]?.deviceKey }"
  />
  </section>
</template>

<script setup>
import AgentCopilotDock from '../../components/agent/AgentCopilotDock.vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import DeviceTeleopPanel from '../../components/robot/DeviceTeleopPanel.vue'
import RobotVideoPanel from '../../components/robot/RobotVideoPanel.vue'
import RobotScene3D from '../../components/robot/RobotScene3D.vue'
import RobotEffectTuner from '../../components/robot/RobotEffectTuner.vue'
import WheelSpeedDial from '../../components/robot/WheelSpeedDial.vue'
import FootContactGrid from '../../components/robot/FootContactGrid.vue'
import { DEFAULT_EFFECT_CONFIG, resolveEffectConfig } from '../../components/robot/rigs/effects.js'
import RobotTaskPanel from '../../components/robot/RobotTaskPanel.vue'
import RobotVoiceBar from '../../components/robot/RobotVoiceBar.vue'
import RobotFleetPanel from '../../components/robot/RobotFleetPanel.vue'
import RobotTwinMap from '../../components/robot/RobotTwinMap.vue'
import RobotFleetCards from '../../components/robot/RobotFleetCards.vue'
import RobotRoutePlanner from '../../components/robot/RobotRoutePlanner.vue'
import RobotAlertCenter from '../../components/robot/RobotAlertCenter.vue'
import RobotMetricsPanel from '../../components/robot/RobotMetricsPanel.vue'
import RobotAssistantPanel from '../../components/robot/RobotAssistantPanel.vue'
import AgentOrchestrationPanel from '../../components/robot/AgentOrchestrationPanel.vue'
import { useRobotFleet } from '../../composables/useRobotFleet'
import { getVisionStatus } from '../../api/inspector'
import {
  getRobotDevices,
  getRobotFrame,
  getRobotLive,
  robotConsoleEndpoint,
  robotEmergencyStop,
  resetRobot,
  switchRobotMode
} from '../../api/robot'

/**
 * 机器人控制台（M1 遥控 + M2 视觉巡检）。
 *
 * 数据来源全部为后端真实接口：设备台账、WebSocket 遥测/事件、命令结果。
 * 无桥连接时如实显示「未连接」，不使用占位数据伪造在线。
 */

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

const devices = ref([])
const selectedKey = ref('')
const mode = ref('OFFLINE')
const bridgeConnected = ref(false)
const telemetry = ref(null)
const telemetryAt = ref(0)
const nowTick = ref(Date.now())
const frameSrc = ref('')
const lastFrameAt = ref('')
const frameSimulated = ref(false)
const visionConfigured = ref(false)
const visionResult = ref(null)
const events = ref([])
const errorMessage = ref('')
const noticeMessage = ref('')
const wsState = ref('closed')

/* ---- 控制台分区：总览 / 操控 / 协同 / 巡检 / 预警 / 分析 ---- */
const TAB_STORAGE_KEY = 'smartops_robot_console_tab'
const TABS = [
  { key: 'overview', label: '总览' },
  { key: 'control', label: '操控' },
  { key: 'orchestration', label: '协同' },
  { key: 'patrol', label: '巡检' },
  { key: 'alerts', label: '预警' },
  { key: 'analysis', label: '分析' }
]

function loadTab() {
  try {
    const saved = window.localStorage.getItem(TAB_STORAGE_KEY)
    return TABS.some(tab => tab.key === saved) ? saved : 'overview'
  } catch {
    return 'overview'
  }
}

const activeTab = ref(loadTab())
watch(activeTab, (value) => {
  try {
    window.localStorage.setItem(TAB_STORAGE_KEY, value)
  } catch {
    /* 隐私模式：仅当次生效 */
  }
})

/* ---- 机队数据层：真实遥测 / 任务 / 预警聚合 ---- */
const {
  states: fleetStates,
  trails,
  history,
  tasks: fleetTasks,
  taskSummary,
  alerts,
  activeAlerts,
  fleetKpis,
  ingest: ingestFleet,
  pollFleet,
  loadTasks: loadFleetTasks,
  loadTaskSummary,
  loadInspectorEvents,
  acknowledge: acknowledgeAlert,
  restore: restoreAlert
} = useRobotFleet(devices)

/* ---- 点选式路线草稿（按设备分别持久化） ---- */
const DRAFT_KEY_PREFIX = 'smartops_robot_route_draft:'
const plannerEditable = ref(false)
const draftRoute = ref([])

function draftKey(deviceKey) {
  return `${DRAFT_KEY_PREFIX}${deviceKey || ''}`
}

function loadDraft(deviceKey) {
  if (!deviceKey) return []
  try {
    const raw = window.localStorage.getItem(draftKey(deviceKey))
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveDraft() {
  if (!selectedKey.value) return
  try {
    window.localStorage.setItem(draftKey(selectedKey.value), JSON.stringify(draftRoute.value))
  } catch {
    /* 存储不可用：草稿仅保留在内存 */
  }
}

watch(selectedKey, (key) => {
  draftRoute.value = loadDraft(key)
  plannerEditable.value = false
  if (key) loadFleetTasks(key)
})

watch(draftRoute, saveDraft, { deep: true })

function addWaypoint(point) {
  if (draftRoute.value.length >= 50) {
    setNotice('单个任务最多 50 个路点')
    return
  }
  draftRoute.value = [
    ...draftRoute.value,
    {
      label: `路点 ${draftRoute.value.length + 1}`,
      x: 0,
      y: 0,
      theta: 0,
      targetX: Number(point.x),
      targetY: Number(point.y),
      actions: ['CAPTURE'],
      speech: ''
    }
  ]
  plannerEditable.value = true
}

function removeWaypoint(index) {
  draftRoute.value = draftRoute.value.filter((_, itemIndex) => itemIndex !== index)
}

/* ---- 最新任务路线（兼容字符串/对象两种 route 存储） ---- */
function parseRoute(raw) {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const latestTask = computed(() => fleetTasks.value[0] || null)
const activeRoute = computed(() => parseRoute(latestTask.value?.route))
const activeRouteProgress = computed(() => Number(latestTask.value?.progress) || 0)

/* ---- 平台助手上下文：只读、真实状态 ---- */
const assistantOpen = ref(false)

const assistantSummary = computed(() => {
  if (!selectedDevice.value) return '尚未选择设备'
  return `${selectedDevice.value.name}（${selectedDevice.value.deviceKey}）· ${modeLabel.value} · 电量 ${batteryText.value} · 位姿 ${poseText.value}`
})

const assistantContextPayload = computed(() => {
  const device = selectedDevice.value
  const lines = []
  lines.push(`设备：${device ? `${device.name}（${device.deviceKey}，${formFactorLabel(device.formFactor)}）` : '未选择'}`)
  lines.push(`运行态：${modeLabel.value}；控制通道：${wsState.value === 'open' ? '已连接' : '未连接'}；控制桥：${bridgeConnected.value ? '已连接' : '未连接'}`)
  lines.push(`遥测：电量 ${batteryText.value}，位姿 (${poseText.value})，朝向 ${headingText.value}，障碍距离 ${obstacleText.value}${telemetryStale.value ? '（心跳超时）' : ''}`)
  if (latestTask.value) {
    const status = latestTask.value.status || 'UNKNOWN'
    const total = activeRoute.value.length
    lines.push(`最新巡检任务：#${latestTask.value.id ?? '—'} 状态 ${status}，进度 ${activeRouteProgress.value}/${total}`)
  } else {
    lines.push('最新巡检任务：无记录')
  }
  const pending = activeAlerts.value.slice(0, 4).map(item => `${item.severity} ${item.title}`)
  lines.push(`未确认预警 ${activeAlerts.value.length} 条${pending.length ? `：${pending.join('；')}` : ''}`)
  lines.push(`机队：在线 ${fleetKpis.value.online}/${fleetKpis.value.total}，执行中 ${fleetKpis.value.runningTasks}，失败 ${fleetKpis.value.failedTasks}`)
  return lines.join('\n')
})

/** 3D 动效参数：本地持久化，刷新后保持上次调节结果。 */
const EFFECT_STORAGE_KEY = 'smartops_robot_effect_config'
function loadEffectConfig() {
  try {
    const raw = window.localStorage.getItem(EFFECT_STORAGE_KEY)
    return raw ? resolveEffectConfig(JSON.parse(raw)) : { ...DEFAULT_EFFECT_CONFIG }
  } catch {
    /* 存储不可用或内容损坏 → 回落默认值 */
    return { ...DEFAULT_EFFECT_CONFIG }
  }
}
const effectConfig = ref(loadEffectConfig())
watch(effectConfig, (value) => {
  try {
    window.localStorage.setItem(EFFECT_STORAGE_KEY, JSON.stringify(value))
  } catch {
    /* 隐私模式 / 配额不足：仅当次生效 */
  }
}, { deep: true })

/** 续传节奏：面板内部按 80ms 节流发命令，这里只负责按住期间按 ttl 续传 */
const RENEW_INTERVAL_MS = 150
const lastCommandAt = ref(0)
const holding = ref(false)
const lastVector = ref({})

let socket = null
let clockTimer = null
let reconnectTimer = null
let disposed = false

const selectedDevice = computed(() =>
  devices.value.find((device) => device.deviceKey === selectedKey.value) || null
)

const controllable = computed(() => mode.value === 'HUMAN_CONTROL' && bridgeConnected.value)

const telemetryStale = computed(() => {
  if (!telemetry.value) return true
  return nowTick.value - telemetryAt.value > 1500
})

const modeLabel = computed(() => MODE_LABELS[mode.value] || mode.value)

const modePillClass = computed(() => {
  if (mode.value === 'E_STOP' || mode.value === 'FAULT') return 'pill-danger'
  if (mode.value === 'HUMAN_CONTROL' || mode.value === 'AUTONOMOUS') return 'pill-ok'
  return 'pill-neutral'
})

const batteryText = computed(() => {
  const raw = telemetry.value?.battery
  if (raw === undefined || raw === null) return '—'
  const ratio = Number(raw)
  if (!Number.isFinite(ratio)) return '—'
  const percent = ratio <= 1 ? ratio * 100 : ratio
  return `${Math.round(percent)}%`
})

const batteryClass = computed(() => {
  const raw = telemetry.value?.battery
  if (raw === undefined || raw === null) return ''
  const ratio = Number(raw)
  const percent = ratio <= 1 ? ratio * 100 : ratio
  if (!Number.isFinite(percent)) return ''
  if (percent < 15) return 'hud-danger'
  if (percent < 30) return 'hud-warn'
  return ''
})

const poseText = computed(() => {
  const pose = telemetry.value?.pose
  if (!pose) return '—'
  const x = Number(pose.x)
  const y = Number(pose.y)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return '—'
  return `${x.toFixed(2)} / ${y.toFixed(2)}`
})

const headingText = computed(() => {
  const theta = telemetry.value?.pose?.theta
  if (theta === undefined || theta === null) return '—'
  const value = Number(theta)
  return Number.isFinite(value) ? `${Math.round(value)}°` : '—'
})

const obstacleText = computed(() => {
  const distance = telemetry.value?.obstacleDistance
  if (distance === undefined || distance === null) return '—'
  const value = Number(distance)
  return Number.isFinite(value) ? `${value.toFixed(2)} m` : '—'
})

/* ---- 形态专属遥测展示：巡检车轮速仪表 / 蜘蛛 8 足触地 ----
   数据取自遥测 wheels / gait（模拟器与真机桥同字段）；缺失时如实显示“—”。 */

const isCarForm = computed(() => (selectedDevice.value?.formFactor || 'CAR') === 'CAR')
const isSpiderForm = computed(() => selectedDevice.value?.formFactor === 'SPIDER')

/* 左右轮原始遥测值交给 WheelSpeedDial 统一格式化与绘制 */
const wheelGauges = computed(() => {
  const wheels = telemetry.value?.wheels
  return [
    { side: 'left', label: '左轮', speed: Number(wheels?.leftSpeed), angular: Number(wheels?.leftAngular) },
    { side: 'right', label: '右轮', speed: Number(wheels?.rightSpeed), angular: Number(wheels?.rightAngular) }
  ]
})

const carWheelRadiusText = computed(() => {
  const radius = Number(telemetry.value?.wheels?.radius)
  return Number.isFinite(radius) && radius > 0 ? `${(radius * 100).toFixed(1)} cm` : '—'
})

const carTrackWidthText = computed(() => {
  const track = Number(telemetry.value?.wheels?.trackWidth)
  return Number.isFinite(track) && track > 0 ? `${(track * 100).toFixed(1)} cm` : '—'
})

const odometerText = computed(() => {
  const odometer = Number(telemetry.value?.odometer)
  return Number.isFinite(odometer) ? `${odometer.toFixed(2)} m` : '—'
})

const lidarRpmText = computed(() => {
  const rpm = Number(telemetry.value?.wheels?.lidarRpm)
  return Number.isFinite(rpm) && rpm > 0 ? `${Math.round(rpm)} rpm` : '—'
})

const spiderFeet = computed(() => {
  const contacts = telemetry.value?.gait?.footContacts
  return Array.isArray(contacts) ? contacts.map((contact) => Boolean(contact)) : []
})

const spiderContactText = computed(() => {
  const feet = spiderFeet.value
  if (!feet.length) return '等待步态遥测'
  const grounded = feet.filter(Boolean).length
  return `支撑 ${grounded} / ${feet.length}`
})

const spiderStrideText = computed(() => {
  const stride = Number(telemetry.value?.gait?.strideHz)
  return Number.isFinite(stride) ? `${stride.toFixed(2)} Hz` : '—'
})

const spiderBodyHeightText = computed(() => {
  const height = Number(telemetry.value?.gait?.bodyHeight)
  return Number.isFinite(height) ? `${height.toFixed(3)} m` : '—'
})

const spiderPhaseText = computed(() => {
  const phase = Number(telemetry.value?.gait?.phase)
  return Number.isFinite(phase) ? `${phase.toFixed(2)} rad` : '—'
})

function formFactorLabel(formFactor) {
  return FORM_FACTOR_LABELS[formFactor] || formFactor || '未知形态'
}

function pushEvent(tag, text, level = 'info') {
  events.value = [
    { tag, text, level, time: new Date().toLocaleTimeString('zh-CN', { hour12: false }) },
    ...events.value
  ].slice(0, 60)
}

function setNotice(message) {
  noticeMessage.value = message
  window.setTimeout(() => {
    if (noticeMessage.value === message) noticeMessage.value = ''
  }, 4000)
}

function canSwitchMode(target) {
  if (!selectedDevice.value?.enabled) return false
  if (!bridgeConnected.value) return false
  if (mode.value === target) return false
  if (mode.value === 'E_STOP' || mode.value === 'FAULT' || mode.value === 'OFFLINE') return false
  return true
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await getRobotDevices()
    devices.value = Array.isArray(response?.data) ? response.data : []
    if (!devices.value.length) {
      selectedKey.value = ''
      return
    }
    const stillExists = devices.value.some((device) => device.deviceKey === selectedKey.value)
    if (!stillExists) {
      const preferred = devices.value.find((device) => device.enabled) || devices.value[0]
      selectedKey.value = preferred.deviceKey
    }
    await loadLive()
    loadFleetTasks(selectedKey.value)
    loadFrame()
    connect()
    pollFleet()
  } catch (error) {
    errorMessage.value = error?.message || '加载设备台账失败'
  }
}

async function loadLive() {
  if (!selectedKey.value) return
  try {
    const response = await getRobotLive(selectedKey.value)
    const data = response?.data || {}
    mode.value = data.mode || 'OFFLINE'
    bridgeConnected.value = Boolean(data.bridgeConnected)
    if (data.telemetry) {
      telemetry.value = data.telemetry
      telemetryAt.value = Date.now()
    }
    ingestFleet(selectedKey.value, {
      mode: mode.value,
      bridgeConnected: bridgeConnected.value,
      telemetry: data.telemetry || null
    })
  } catch (error) {
    errorMessage.value = error?.message || '加载实时状态失败'
  }
}

async function loadFrame() {
  if (!selectedKey.value) return
  try {
    const response = await getRobotFrame(selectedKey.value)
    const data = response?.data
    if (data?.imageBase64) {
      frameSrc.value = `data:${data.mime || 'image/jpeg'};base64,${data.imageBase64}`
      lastFrameAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
      frameSimulated.value = Boolean(data.simulated)
    }
    if (data?.lastAnalysis) visionResult.value = data.lastAnalysis
  } catch {
    // 首屏回填失败不阻塞控制台；后续帧仍会经 WebSocket 到达
  }
}

async function loadVisionStatus() {
  try {
    const response = await getVisionStatus()
    visionConfigured.value = Boolean(response?.data?.configured)
  } catch {
    visionConfigured.value = false
  }
}

function onDeviceChange() {
  mode.value = 'OFFLINE'
  bridgeConnected.value = false
  telemetry.value = null
  frameSrc.value = ''
  lastFrameAt.value = ''
  frameSimulated.value = false
  visionResult.value = null
  loadFleetTasks(selectedKey.value)
  loadLive().then(() => {
    loadFrame()
    sendSubscribe()
  })
}

/** 跨面板选中设备：同步下拉框、重启订阅并刷新该设备任务。 */
function selectDevice(deviceKey) {
  if (!deviceKey || deviceKey === selectedKey.value) return
  selectedKey.value = deviceKey
  onDeviceChange()
}

/** 态势卡快捷急停：直接走安全优先的 REST 通道，不依赖当前选中项。 */
async function quickEstop(deviceKey) {
  if (!deviceKey) return
  try {
    await robotEmergencyStop(deviceKey)
    ingestFleet(deviceKey, { mode: 'E_STOP' })
    if (deviceKey === selectedKey.value) mode.value = 'E_STOP'
    pushEvent('急停', `${deviceKey} 已通过态势卡下发急停`, 'error')
  } catch (error) {
    errorMessage.value = error?.message || '急停下发失败'
  }
}

function refreshAlerts() {
  loadInspectorEvents()
  loadTaskSummary()
}

function onTaskStarted() {
  loadLive()
  loadFleetTasks(selectedKey.value)
  loadTaskSummary()
}

function onRouteSubmitted() {
  loadLive()
  loadFleetTasks(selectedKey.value)
  loadTaskSummary()
  plannerEditable.value = false
  setNotice('巡检任务已下发，进度可在任务面板与孪生地图查看')
}

function connect() {
  closeSocket()
  if (disposed || !selectedKey.value) return
  try {
    socket = new WebSocket(robotConsoleEndpoint())
  } catch {
    wsState.value = 'closed'
    pushEvent('通道', 'WebSocket 创建失败，遥控不可用', 'error')
    return
  }
  wsState.value = 'connecting'
  socket.onopen = () => {
    wsState.value = 'open'
    pushEvent('通道', '控制通道已连接')
    sendSubscribe()
  }
  socket.onmessage = (event) => handleMessage(event.data)
  socket.onerror = () => {
    wsState.value = 'closed'
  }
  socket.onclose = () => {
    wsState.value = 'closed'
    holding.value = false
    if (disposed) return
    reconnectTimer = window.setTimeout(connect, 3000)
  }
}

function closeSocket() {
  if (reconnectTimer) {
    window.clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (socket) {
    const current = socket
    socket = null
    current.onopen = null
    current.onmessage = null
    current.onerror = null
    current.onclose = null
    try {
      current.close()
    } catch {
      // 已关闭
    }
  }
}

function sendJson(type, payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return false
  socket.send(JSON.stringify({ type, payload }))
  return true
}

function sendSubscribe() {
  if (!selectedKey.value) return
  sendJson('subscribe', { deviceKey: selectedKey.value })
}

function handleMessage(raw) {
  let envelope
  try {
    envelope = JSON.parse(raw)
  } catch {
    return
  }
  const payload = envelope?.payload || {}
  switch (envelope?.type) {
    case 'telemetry':
      if (payload.deviceKey && payload.deviceKey !== selectedKey.value) return
      telemetry.value = payload
      telemetryAt.value = Date.now()
      ingestFleet(payload.deviceKey || selectedKey.value, {
        telemetry: payload,
        mode: mode.value,
        bridgeConnected: bridgeConnected.value
      })
      break
    case 'frame':
      if (payload.deviceKey && payload.deviceKey !== selectedKey.value) return
      if (payload.imageBase64) {
        frameSrc.value = `data:${payload.mime || 'image/jpeg'};base64,${payload.imageBase64}`
        lastFrameAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
        frameSimulated.value = Boolean(payload.simulated)
      }
      break
    case 'vision':
      if (payload.deviceKey && payload.deviceKey !== selectedKey.value) return
      visionResult.value = payload
      pushEvent(
        '视觉',
        payload.status === 'OK'
          ? `识别完成${payload.eventId ? `，事件 ${payload.eventId}` : ''}`
          : `${payload.status}｜${payload.message || ''}`,
        payload.status === 'OK' ? 'info' : 'error'
      )
      break
    case 'mode':
      if (payload.deviceKey && payload.deviceKey !== selectedKey.value) return
      mode.value = payload.mode || mode.value
      ingestFleet(selectedKey.value, { mode: mode.value })
      pushEvent('模式', `运行态 → ${MODE_LABELS[payload.mode] || payload.mode}（${payload.reason || '未知原因'}）`)
      break
    case 'device_event':
      if (payload.deviceKey && payload.deviceKey !== selectedKey.value) return
      pushEvent('设备', payload.detail || payload.kind || '设备上报事件')
      break
    case 'error':
      errorMessage.value = payload.message || '指令被拒绝'
      pushEvent('拒绝', `${payload.code || 'ROBOT_REJECTED'}｜${payload.message || ''}`, 'error')
      break
    case 'cmd_result':
      // 成功命令不刷事件流，避免遥控时刷屏
      break
    case 'estop_result':
      mode.value = 'E_STOP'
      ingestFleet(selectedKey.value, { mode: 'E_STOP' })
      pushEvent('急停', `已下发停止指令（${payload.deliveredToBridge ? '已送达桥' : '桥未连接'}）`, 'error')
      break
    case 'mode_result':
      if (payload.mode) mode.value = payload.mode
      ingestFleet(selectedKey.value, { mode: mode.value })
      break
    case 'reset_result':
      if (payload.mode) mode.value = payload.mode
      ingestFleet(selectedKey.value, { mode: mode.value })
      setNotice('已复位')
      break
    default:
      break
  }
}

function sendCommand(op, params = {}) {
  const delivered = sendJson('cmd', { deviceKey: selectedKey.value, op, params })
  if (!delivered) {
    pushEvent('通道', '控制通道未连接，命令未下发', 'error')
  }
  return delivered
}

/**
 * 统一遥控面板已按设备能力模型组装好合法参数，这里只负责通道与续传：
 * 参数里的 `unsupportedAxes` 是给 UI 的提示字段，不下发给后端。
 */
function onTeleopCommand(params) {
  if (!controllable.value) return
  const { unsupportedAxes: _unsupportedAxes, ...payload } = params || {}
  lastVector.value = { ...payload }
  holding.value = true
  lastCommandAt.value = Date.now()
  sendCommand('MOVE', payload)
}

function onTeleopRelease() {
  if (!holding.value) return
  holding.value = false
  lastVector.value = {}
  sendCommand('STOP')
}

function changeMode(target) {
  errorMessage.value = ''
  const sent = sendJson('mode', { deviceKey: selectedKey.value, mode: target })
  if (!sent) {
    switchRobotMode(selectedKey.value, target)
      .then((response) => {
        mode.value = response?.data?.mode || mode.value
        setNotice('模式已切换')
      })
      .catch((error) => {
        errorMessage.value = error?.message || '切换模式失败'
      })
  }
}

function resetDevice() {
  const sent = sendJson('reset', { deviceKey: selectedKey.value })
  if (!sent) {
    resetRobot(selectedKey.value)
      .then((response) => {
        mode.value = response?.data?.mode || mode.value
        setNotice('已复位')
      })
      .catch((error) => {
        errorMessage.value = error?.message || '复位失败'
      })
  }
}

function emergencyStop() {
  holding.value = false
  lastVector.value = {}
  const sent = sendJson('estop', { deviceKey: selectedKey.value })
  if (!sent) {
    robotEmergencyStop(selectedKey.value)
      .then(() => {
        mode.value = 'E_STOP'
        pushEvent('急停', '已通过 REST 下发停止', 'error')
      })
      .catch((error) => {
        errorMessage.value = error?.message || '急停下发失败'
      })
  }
}

function captureOnce() {
  sendCommand('CAPTURE', { target: selectedDevice.value?.name || selectedKey.value })
  setNotice('已下发拍照指令，结论将进入纠察中心待复核')
}

function speak() {
  const text = window.prompt('喊话内容（不超过 200 字）', '请注意，正在巡检作业')
  if (text === null) return
  sendCommand('SPEAK', { text })
}

function centerPtz() {
  sendCommand('PTZ', { pan: 0, tilt: 0 })
}

let fleetTimer = null
let alertTimer = null
let summaryTimer = null
let taskTimer = null

onMounted(() => {
  reload()
  loadVisionStatus()
  loadInspectorEvents()
  loadTaskSummary()
  fleetTimer = window.setInterval(pollFleet, 3000)
  alertTimer = window.setInterval(loadInspectorEvents, 15000)
  summaryTimer = window.setInterval(loadTaskSummary, 12000)
  taskTimer = window.setInterval(() => {
    if (selectedKey.value) loadFleetTasks(selectedKey.value)
  }, 5000)
  clockTimer = window.setInterval(() => {
    nowTick.value = Date.now()
    // 续传：保持按住时按 ttl 周期重发运动指令，实现 dead-man switch
    if (holding.value && controllable.value) {
      const now = Date.now()
      if (now - lastCommandAt.value >= RENEW_INTERVAL_MS) {
        lastCommandAt.value = now
        sendCommand('MOVE', lastVector.value)
      }
    }
  }, 50)
})

onBeforeUnmount(() => {
  disposed = true
  if (clockTimer) window.clearInterval(clockTimer)
  if (fleetTimer) window.clearInterval(fleetTimer)
  if (alertTimer) window.clearInterval(alertTimer)
  if (summaryTimer) window.clearInterval(summaryTimer)
  if (taskTimer) window.clearInterval(taskTimer)
  holding.value = false
  closeSocket()
})
</script>

<style scoped>
.robot-console {
  display: flex;
  flex-direction: column;
  gap: var(--ds-section-gap, var(--ds-space-6));
  color: var(--ds-color-text);
  font-size: var(--ds-font-md);
}

.console-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ds-space-4);
}

.console-title {
  margin: 0 0 var(--ds-space-1);
  font-size: var(--ds-font-2xl);
}

.console-sub {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-sm);
}

.head-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--ds-space-3);
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-1);
}

.field-label {
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
}

select {
  min-width: 220px;
  height: var(--ds-control-height, 36px);
  padding: 0 var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-size: var(--ds-font-sm);
}

.console-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
  gap: var(--ds-space-4);
}

.console-tabs {
  display: flex;
  gap: 4px;
  padding-bottom: 2px;
  border-bottom: 1px solid var(--ds-color-border);
  overflow-x: auto;
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid transparent;
  border-bottom: 2px solid transparent;
  border-radius: var(--ds-radius-md) var(--ds-radius-md) 0 0;
  background: transparent;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-sm);
  white-space: nowrap;
  cursor: pointer;
  transition: color var(--ds-duration-fast) ease, border-color var(--ds-duration-fast) ease;
}

.tab-btn:hover {
  color: var(--ds-color-text);
}

.tab-btn.active {
  border-bottom-color: var(--ds-color-primary);
  color: var(--ds-color-text);
  background: rgba(36, 150, 237, 0.08);
}

.tab-badge {
  min-width: 16px;
  padding: 0 4px;
  border-radius: var(--ds-radius-pill);
  background: rgba(227, 160, 8, 0.2);
  color: #f0c260;
  font-size: 9px;
  line-height: 16px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.tab-panel {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-4);
  min-width: 0;
}

.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(300px, 1fr);
  gap: var(--ds-space-4);
  align-items: start;
}

.overview-side {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-4);
  min-width: 0;
}

.overview-metrics {
  grid-column: 1 / -1;
}

.patrol-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(320px, 1fr);
  gap: var(--ds-space-4);
  align-items: start;
}

.patrol-lower {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: var(--ds-space-4);
  align-items: start;
}

.analysis-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(300px, 1fr);
  gap: var(--ds-space-4);
  align-items: start;
}

.assistant-cta {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-3);
}

.assistant-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--ds-space-2);
  margin: 0;
}

.assistant-facts div {
  padding: var(--ds-space-2) var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
}

.assistant-facts dt {
  color: var(--ds-color-muted);
  font-size: 10px;
}

.assistant-facts dd {
  margin: 2px 0 0;
  font-size: var(--ds-font-sm);
  font-variant-numeric: tabular-nums;
}

.assistant-cta-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space-2);
}

.link-btn {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
}

.head-action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: var(--ds-control-height, 36px);
  padding: 0 var(--ds-space-3);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-sm);
  cursor: pointer;
}

.head-action:hover {
  border-color: var(--ds-color-primary);
  color: var(--ds-color-text);
}

.head-action.primary {
  border-color: rgba(36, 150, 237, 0.5);
  background: rgba(36, 150, 237, 0.14);
  color: var(--ds-color-text);
}

.head-badge {
  min-width: 16px;
  padding: 0 4px;
  border-radius: var(--ds-radius-pill);
  background: rgba(227, 160, 8, 0.22);
  color: #f0c260;
  font-size: 9px;
  line-height: 16px;
  text-align: center;
}

.panel-stack {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-4);
  min-width: 0;
}

.panel {
  padding: var(--ds-card-padding, var(--ds-space-4));
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-3);
  margin-bottom: var(--ds-space-3);
}

.panel-head h2 {
  margin: 0;
  font-size: var(--ds-font-lg);
}

.hud-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--ds-space-3);
  margin: 0;
}

.hud-item {
  padding: var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
}

.hud-item dt {
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
}

.hud-item dd {
  margin: var(--ds-space-1) 0 0;
  font-family: var(--ds-font-mono);
  font-size: var(--ds-font-lg);
}

.hud-warn {
  color: var(--ds-color-warning);
}

.hud-danger {
  color: var(--ds-color-danger);
}

/* 形态专属遥测：轮速仪表 / 8 足触地 */
.hud-extra {
  margin-top: var(--ds-space-3);
  padding: var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
}

.hud-extra-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--ds-space-1) var(--ds-space-3);
  margin-bottom: var(--ds-space-2);
}

.hud-extra-head h3 {
  margin: 0;
  font-size: var(--ds-font-sm);
  font-weight: 600;
}

.hud-extra-meta {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  font-variant-numeric: tabular-nums;
}

.wheel-gauges {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--ds-space-3);
}

.mode-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space-2);
}

.btn {
  height: var(--ds-control-height, 36px);
  padding: 0 var(--ds-space-4);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-size: var(--ds-font-sm);
  cursor: pointer;
  transition: border-color var(--ds-duration-fast) ease, background var(--ds-duration-fast) ease;
}

.btn:hover:not(:disabled) {
  border-color: var(--ds-color-primary);
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-active {
  border-color: var(--ds-color-primary);
  background: rgba(36, 150, 237, 0.16);
}

.btn-ghost {
  background: transparent;
}

.drive-area {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-4);
  flex-wrap: wrap;
}

.drive-panel {
  flex: 1 1 320px;
  min-width: 260px;
}

.drive-side {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-2);
  min-width: 132px;
}

.estop {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-height: 76px;
  border: 2px solid var(--ds-color-danger);
  border-radius: var(--ds-radius-lg);
  background: rgba(220, 132, 144, 0.14);
  color: var(--ds-color-danger);
  cursor: pointer;
}

.estop:hover {
  background: rgba(220, 132, 144, 0.24);
}

.estop:focus-visible {
  outline: 2px solid var(--ds-color-danger);
  outline-offset: 2px;
}

.estop-label {
  font-size: var(--ds-font-lg);
  font-weight: 700;
  letter-spacing: 0.08em;
}

.estop-sub {
  font-size: var(--ds-font-xs);
}

.pill {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--ds-space-2);
  border-radius: var(--ds-radius-pill);
  font-size: var(--ds-font-xs);
  white-space: nowrap;
}

.pill-ok {
  background: rgba(139, 207, 180, 0.16);
  color: var(--ds-color-success);
}

.pill-warn {
  background: rgba(217, 185, 109, 0.16);
  color: var(--ds-color-warning);
}

.pill-danger {
  background: rgba(220, 132, 144, 0.16);
  color: var(--ds-color-danger);
}

.pill-neutral {
  background: var(--ds-pill-neutral-bg, rgba(159, 190, 207, 0.12));
  color: var(--ds-color-muted);
}

.banner {
  margin: 0;
  padding: var(--ds-space-3) var(--ds-space-4);
  border-radius: var(--ds-radius-md);
  font-size: var(--ds-font-sm);
}

.banner-error {
  border: 1px solid var(--ds-color-danger);
  color: var(--ds-color-danger);
}

.banner-info {
  border: 1px solid var(--ds-color-border-strong);
  color: var(--ds-color-muted);
}

.empty-state {
  padding: var(--ds-space-8);
  border: 1px dashed var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  color: var(--ds-color-muted);
  text-align: center;
}

.empty-state a {
  color: var(--ds-color-primary);
}

.event-list {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 220px;
  overflow-y: auto;
}

.event-item {
  display: flex;
  align-items: center;
  gap: var(--ds-space-2);
  font-size: var(--ds-font-sm);
}

.event-time {
  color: var(--ds-color-muted);
  font-family: var(--ds-font-mono);
  font-size: var(--ds-font-xs);
}

.event-text {
  color: var(--ds-color-text);
}

.hint-text {
  margin: var(--ds-space-2) 0 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  line-height: var(--ds-line-base);
}

@media (max-width: 1024px) {
  .console-grid,
  .overview-grid,
  .patrol-grid,
  .analysis-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .overview-metrics {
    grid-column: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .btn {
    transition: none;
  }
}
</style>
