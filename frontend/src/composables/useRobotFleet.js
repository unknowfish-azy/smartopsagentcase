import { computed, ref } from 'vue'
import { getRobotLive, getRobotTasks, getRobotTaskSummary } from '../api/robot'
import { getInspectorEvents } from '../api/inspector'

/**
 * 机队控制台数据层。
 *
 * 只聚合真实接口：设备实时视图、任务列表、任务汇总、纠察事件；
 * 派生预警全部来自真实遥测阈值（电量 / 心跳 / 障碍 / 运行态）与真实任务状态，
 * 没有数据时如实为空，不生成占位事件。
 */

const ACK_STORAGE_KEY = 'smartops_robot_alert_ack'
const TRAIL_LIMIT = 180
const HISTORY_LIMIT = 120
const HEARTBEAT_STALE_MS = 5000
const HISTORY_SAMPLE_MS = 1000
/** 设备类预警的确认只保留 30 分钟，避免一次确认后长期漏看复发问题。 */
const DEVICE_ACK_TTL_MS = 30 * 60 * 1000

const SEVERITY_RANK = { CRITICAL: 0, HIGH: 1, WARN: 2, INFO: 3 }

function loadAck() {
  try {
    const raw = window.localStorage.getItem(ACK_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function normalizeSeverity(value) {
  const text = String(value || '').trim().toUpperCase()
  if (text === 'WARNING') return 'WARN'
  if (text === 'ERROR' || text === 'FATAL') return 'CRITICAL'
  if (text in SEVERITY_RANK) return text
  return 'INFO'
}

function batteryPercent(raw) {
  const value = Number(raw)
  if (!Number.isFinite(value)) return null
  return Math.round(value <= 1 ? value * 100 : value)
}

function timeOf(value) {
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : Date.now()
}

function formatClock(ts) {
  try {
    return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return '—'
  }
}

export function useRobotFleet(devices) {
  const states = ref({})
  const trails = ref({})
  const history = ref({})
  const tasks = ref([])
  const taskSummary = ref({ running: 0, paused: 0, failed: 0 })
  const inspectorEvents = ref([])
  const ack = ref(loadAck())
  const pollError = ref('')
  const lastPollAt = ref(0)

  const sampling = new Map()

  function persistAck() {
    try {
      window.localStorage.setItem(ACK_STORAGE_KEY, JSON.stringify(ack.value))
    } catch {
      /* 隐私模式 / 配额不足：仅当次生效 */
    }
  }

  function appendTrail(key, x, y) {
    const list = trails.value[key] || []
    const last = list[list.length - 1]
    if (last && Math.hypot(last.x - x, last.y - y) < 0.02) return
    list.push({ x, y })
    if (list.length > TRAIL_LIMIT) list.splice(0, list.length - TRAIL_LIMIT)
    trails.value[key] = list
  }

  function appendHistory(key, telemetry, at) {
    const sample = sampling.get(key) || { at: 0, pose: null }
    if (at - sample.at < HISTORY_SAMPLE_MS) return
    const pose = telemetry?.pose
    const x = Number(pose?.x)
    const y = Number(pose?.y)
    let speed = null
    if (Number.isFinite(x) && Number.isFinite(y) && sample.pose) {
      const dt = (at - sample.at) / 1000
      if (dt > 0) {
        const distance = Math.hypot(x - sample.pose.x, y - sample.pose.y)
        speed = distance / dt
      }
    }
    if (Number.isFinite(x) && Number.isFinite(y)) {
      sampling.set(key, { at, pose: { x, y } })
    }
    const list = history.value[key] || []
    list.push({ t: at, battery: batteryPercent(telemetry?.battery), speed })
    if (list.length > HISTORY_LIMIT) list.splice(0, list.length - HISTORY_LIMIT)
    history.value[key] = list
  }

  /** 合并一次实时状态；WebSocket 与轮询共用同一入口。 */
  function ingest(deviceKey, patch = {}) {
    if (!deviceKey) return
    const previous = states.value[deviceKey] || {}
    const next = { ...previous, ...patch }
    const telemetry = patch.telemetry !== undefined ? patch.telemetry : previous.telemetry
    if (patch.telemetry) {
      next.telemetry = patch.telemetry
      next.telemetryAt = patch.telemetryAt || Date.now()
    }
    states.value = { ...states.value, [deviceKey]: next }
    if (telemetry?.pose) {
      const x = Number(telemetry.pose.x)
      const y = Number(telemetry.pose.y)
      if (Number.isFinite(x) && Number.isFinite(y)) {
        appendTrail(deviceKey, x, y)
        appendHistory(deviceKey, telemetry, next.telemetryAt || Date.now())
      }
    }
  }

  /** 轮询所有启用设备的实时视图（控制台没有为每台设备各开一条 WS）。 */
  async function pollFleet() {
    const keys = (devices.value || [])
      .filter(device => device.enabled !== false)
      .map(device => device.deviceKey)
    if (!keys.length) return
    try {
      const results = await Promise.all(keys.map(async (key) => {
        try {
          const response = await getRobotLive(key)
          return { key, data: response?.data || {} }
        } catch (error) {
          return { key, error }
        }
      }))
      results.forEach(({ key, data, error }) => {
        if (error || !data) return
        ingest(key, {
          mode: data.mode || 'OFFLINE',
          bridgeConnected: Boolean(data.bridgeConnected),
          telemetry: data.telemetry || null
        })
      })
      pollError.value = ''
      lastPollAt.value = Date.now()
    } catch (error) {
      pollError.value = error?.message || '机队状态刷新失败'
    }
  }

  async function loadTasks(deviceKey) {
    if (!deviceKey) {
      tasks.value = []
      return
    }
    try {
      const response = await getRobotTasks(deviceKey)
      tasks.value = Array.isArray(response?.data) ? response.data : []
    } catch {
      tasks.value = []
    }
  }

  async function loadTaskSummary() {
    try {
      const response = await getRobotTaskSummary()
      taskSummary.value = response?.data || { running: 0, paused: 0, failed: 0 }
    } catch {
      /* 汇总不可用时保持上一次真实值 */
    }
  }

  async function loadInspectorEvents() {
    try {
      const response = await getInspectorEvents(30)
      inspectorEvents.value = Array.isArray(response?.data) ? response.data : []
    } catch {
      inspectorEvents.value = []
    }
  }

  function acknowledge(id) {
    if (!id) return
    ack.value = { ...ack.value, [id]: Date.now() }
    persistAck()
  }

  function restore(id) {
    if (!id || !ack.value[id]) return
    const next = { ...ack.value }
    delete next[id]
    ack.value = next
    persistAck()
  }

  /** 由真实遥测与任务状态派生的设备预警。 */
  const derivedAlerts = computed(() => {
    const list = []
    const now = Date.now()
    for (const device of devices.value || []) {
      if (device.enabled === false) continue
      const key = device.deviceKey
      const name = device.name || key
      const state = states.value[key] || {}
      const telemetry = state.telemetry
      const at = state.telemetryAt || 0

      if (!state.bridgeConnected) {
        list.push({
          id: `dev-${key}-bridge`,
          source: 'DEVICE',
          severity: 'WARN',
          title: '控制桥未连接',
          detail: `${name}（${key}）当前无桥在线，遥控与任务下发不可用`,
          deviceKey: key,
          at: now,
          link: ''
        })
      }
      if (state.mode === 'E_STOP') {
        list.push({
          id: `dev-${key}-estop`,
          source: 'DEVICE',
          severity: 'CRITICAL',
          title: '设备处于急停态',
          detail: `${name}（${key}）已触发急停，需人工确认现场后复位`,
          deviceKey: key,
          at: at || now,
          link: ''
        })
      } else if (state.mode === 'FAULT') {
        list.push({
          id: `dev-${key}-fault`,
          source: 'DEVICE',
          severity: 'CRITICAL',
          title: '设备故障态',
          detail: `${name}（${key}）上报故障，需先排障再复位`,
          deviceKey: key,
          at: at || now,
          link: ''
        })
      }
      if (telemetry && at && now - at > HEARTBEAT_STALE_MS) {
        list.push({
          id: `dev-${key}-stale`,
          source: 'DEVICE',
          severity: 'WARN',
          title: '遥测心跳中断',
          detail: `${name}（${key}）已 ${Math.round((now - at) / 1000)}s 未上报遥测`,
          deviceKey: key,
          at,
          link: ''
        })
      }
      const percent = batteryPercent(telemetry?.battery)
      if (percent !== null && percent < 30) {
        list.push({
          id: `dev-${key}-battery`,
          source: 'DEVICE',
          severity: percent < 15 ? 'CRITICAL' : 'WARN',
          title: `电量偏低 ${percent}%`,
          detail: `${name}（${key}）剩余电量 ${percent}%，${percent < 15 ? '应立即返航充电' : '建议尽快安排充电'}`,
          deviceKey: key,
          at: at || now,
          link: ''
        })
      }
      const obstacle = Number(telemetry?.obstacleDistance)
      if (Number.isFinite(obstacle) && obstacle < 0.5 && now - at <= HEARTBEAT_STALE_MS) {
        list.push({
          id: `dev-${key}-obstacle`,
          source: 'DEVICE',
          severity: 'WARN',
          title: '障碍距离过近',
          detail: `${name}（${key}）前方障碍 ${obstacle.toFixed(2)}m，已进入安全阈值`,
          deviceKey: key,
          at,
          link: ''
        })
      }
    }
    const failed = Number(taskSummary.value?.failed) || 0
    if (failed > 0) {
      list.push({
        id: 'fleet-task-failed',
        source: 'TASK',
        severity: 'HIGH',
        title: `存在 ${failed} 个失败任务`,
        detail: '任务执行失败会自动触发急停，请在巡检页查看失败任务与重规划记录',
        deviceKey: '',
        at: now,
        link: ''
      })
    }
    return list
  })

  /** 纠察中心真实视觉/巡检事件。 */
  const inspectorAlerts = computed(() => (inspectorEvents.value || []).map((event) => {
    const id = event?.id == null ? '' : String(event.id)
    const severity = normalizeSeverity(event?.severity)
    const at = timeOf(event?.at ?? event?.createdAt)
    return {
      id: `insp-${id || at}`,
      source: 'VISUAL',
      severity,
      title: event?.title || event?.category || (severity === 'INFO' ? '巡检事件' : '视觉异常待复核'),
      detail: [event?.target, event?.reason].filter(Boolean).join(' · ') || '纠察中心记录',
      deviceKey: '',
      at,
      link: id ? `/inspector/events/${id}` : '/inspector'
    }
  }))

  const alerts = computed(() => [...derivedAlerts.value, ...inspectorAlerts.value]
    .map((item) => {
      const ackAt = ack.value[item.id]
      const acked = Boolean(ackAt) && (item.source === 'VISUAL' || Date.now() - ackAt < DEVICE_ACK_TTL_MS)
      return { ...item, timeText: formatClock(item.at), acked }
    })
    .sort((a, b) => {
      const rank = (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9)
      return rank !== 0 ? rank : b.at - a.at
    }))

  const activeAlerts = computed(() => alerts.value.filter(item => !item.acked))

  const fleetKpis = computed(() => {
    const list = devices.value || []
    const enabled = list.filter(device => device.enabled !== false)
    const online = enabled.filter(device => states.value[device.deviceKey]?.bridgeConnected)
    const batteries = enabled
      .map(device => batteryPercent(states.value[device.deviceKey]?.telemetry?.battery))
      .filter(value => value !== null)
    const avgBattery = batteries.length
      ? Math.round(batteries.reduce((sum, value) => sum + value, 0) / batteries.length)
      : null
    return {
      total: list.length,
      enabled: enabled.length,
      online: online.length,
      avgBattery,
      runningTasks: Number(taskSummary.value?.running) || 0,
      failedTasks: Number(taskSummary.value?.failed) || 0,
      activeAlerts: activeAlerts.value.length
    }
  })

  return {
    states,
    trails,
    history,
    tasks,
    taskSummary,
    inspectorEvents,
    ack,
    pollError,
    lastPollAt,
    alerts,
    activeAlerts,
    fleetKpis,
    ingest,
    pollFleet,
    loadTasks,
    loadTaskSummary,
    loadInspectorEvents,
    acknowledge,
    restore
  }
}
