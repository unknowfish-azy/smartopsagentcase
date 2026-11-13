/**
 * 顶栏全局运行态（环境 / 活跃告警 / 健康分 / Agent 状态）。
 *
 * 只读真实接口：`/api/inspector/summary` 提供巡检分级计数，
 * 已加载的哨兵告警（sentinelStore）提供处置中的告警数。
 * 任一来源不可用 → 计数返回 null（界面显示「—」），绝不编造看起来像真的数字。
 */
import { computed, onBeforeUnmount, reactive } from 'vue'
import { getInspectorSummary } from '../api/inspector'
import { sentinelState } from '../views/sentinel/sentinelStore'

/** 仍在处置链路上的告警状态（与告警中心的统计口径一致）。 */
const ACTIVE_ALERT_STATUSES = new Set(['OPEN', 'PENDING_APPROVAL', 'REMEDIATING'])

const opsStatus = reactive({
  /** 'loading' | 'ready' | 'offline' */
  inspectorStatus: 'loading',
  summary: null,
  updatedAt: null
})

let pollTimer = null
let inflight = null

/** 拉取一次巡检摘要；并发调用复用同一个 Promise。 */
export async function refreshGlobalOpsStatus() {
  if (inflight) return inflight
  inflight = (async () => {
    try {
      const response = await getInspectorSummary()
      opsStatus.summary = response?.data || null
      opsStatus.inspectorStatus = 'ready'
      opsStatus.updatedAt = Date.now()
    } catch {
      // 401 / 网络错误一律视为离线，不做任何补数。
      opsStatus.summary = null
      opsStatus.inspectorStatus = 'offline'
    } finally {
      inflight = null
    }
  })()
  return inflight
}

export function startGlobalOpsPolling(intervalMs = 60000) {
  stopGlobalOpsPolling()
  refreshGlobalOpsStatus()
  pollTimer = window.setInterval(refreshGlobalOpsStatus, intervalMs)
}

export function stopGlobalOpsPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

export function useGlobalOpsStatus() {
  /** 活跃告警：哨兵就绪用告警真实状态统计，否则退到巡检 high+critical，两者都不可用则为 null。 */
  const activeAlerts = computed(() => {
    if (sentinelState.status === 'ready') {
      return sentinelState.alerts.filter(alert => ACTIVE_ALERT_STATUSES.has(String(alert?.status || '').toUpperCase())).length
    }
    if (opsStatus.inspectorStatus === 'ready' && opsStatus.summary) {
      return Number(opsStatus.summary.high ?? 0) + Number(opsStatus.summary.critical ?? 0)
    }
    return null
  })

  /** 健康分：PASS 记满分、WARN 记半分；没有巡检记录时返回 null（不是 0 分）。 */
  const healthScore = computed(() => {
    if (opsStatus.inspectorStatus !== 'ready' || !opsStatus.summary) return null
    const total = Number(opsStatus.summary.total ?? 0)
    if (!Number.isFinite(total) || total <= 0) return null
    const pass = Number(opsStatus.summary.pass ?? 0)
    const warning = Number(opsStatus.summary.warning ?? 0)
    return Math.max(0, Math.min(100, Math.round(((pass + warning * 0.5) / total) * 100)))
  })

  const inspectorOffline = computed(() => opsStatus.inspectorStatus === 'offline')

  onBeforeUnmount(stopGlobalOpsPolling)

  return { opsStatus, activeAlerts, healthScore, inspectorOffline, refreshGlobalOpsStatus }
}
