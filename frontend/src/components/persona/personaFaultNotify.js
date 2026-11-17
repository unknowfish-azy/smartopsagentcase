/**
 * 桌宠告警通知决策（纯逻辑，不依赖 DOM/Vue，可被 node:test 直测）。
 *
 * 订阅侧（PersonaPet.vue）收到 FAULT_DETECTED 事件后把 faultEvent 喂给本工厂，
 * 工厂只做「报不报、报什么、出不出声」的决策，展示与语音由注入的回调完成：
 *  - 去重：同一 faultEvent.id 只报一次（容量淘汰防泄漏）；
 *  - 节流：notifyGapMs 内只提示第一条，连环告警不轰炸；
 *  - 分级：HIGH/CRITICAL 算高危 → 气泡停留更久、允许出声；其余只出气泡；
 *  - 让路：正在播报（isBusy）或听筒静音（isMuted）时不出声，气泡照常。
 *
 * 定时与时间源可注入，测试用假时钟推进即可。
 */

/** 全局节流窗：窗内第二条及以后的告警只去重记录、不展示 */
export const FAULT_NOTIFY_GAP_MS = 5 * 60 * 1000
/** 普通告警气泡停留时长 */
export const FAULT_ALERT_HOLD_MS = 8000
/** 高危告警气泡停留时长 */
export const FAULT_ALERT_CRITICAL_HOLD_MS = 12000
/** 去重集合容量上限，超过后按插入序淘汰最旧 */
export const FAULT_ID_TRACK_LIMIT = 50

/** 算高危的告警等级 */
export function isCriticalFault(severity) {
  return severity === 'CRITICAL' || severity === 'HIGH'
}

/**
 * @param {{
 *   showAlert?: (alert: { id: string, critical: boolean, text: string }) => void,
 *   clearAlert?: () => void,
 *   playGesture?: (name: string) => void,
 *   speak?: (text: string) => void
 * }} handlers
 * @param {{
 *   notifyGapMs?: number,
 *   normalHoldMs?: number,
 *   criticalHoldMs?: number,
 *   maxTrackedIds?: number,
 *   now?: () => number,
 *   schedule?: (fn: Function, ms: number) => any,
 *   cancel?: (id: any) => void,
 *   isBusy?: () => boolean,
 *   isMuted?: () => boolean
 * }} [options]
 */
export function createFaultNotifier(handlers, options = {}) {
  const {
    showAlert = () => {},
    clearAlert = () => {},
    playGesture = () => {},
    speak = () => {}
  } = handlers
  const {
    notifyGapMs = FAULT_NOTIFY_GAP_MS,
    normalHoldMs = FAULT_ALERT_HOLD_MS,
    criticalHoldMs = FAULT_ALERT_CRITICAL_HOLD_MS,
    maxTrackedIds = FAULT_ID_TRACK_LIMIT,
    now = () => Date.now(),
    schedule = (fn, ms) => setTimeout(fn, ms),
    cancel = (id) => clearTimeout(id),
    isBusy = () => false,
    isMuted = () => false
  } = options

  const seenIds = new Set()
  let lastNotifyAt = Number.NEGATIVE_INFINITY
  let clearTimer = null

  function disarm() {
    if (clearTimer !== null) {
      cancel(clearTimer)
      clearTimer = null
    }
  }

  /**
   * 喂一条故障事件（companion 的 faultEvent）。
   * @returns {{ shown: boolean, spoke: boolean, reason?: string }}
   *   shown=是否展示了气泡；spoke=是否真的尝试出声；reason=未展示的原因。
   */
  function handleFault(faultEvent) {
    const id = faultEvent?.id
    if (!id) return { shown: false, spoke: false, reason: 'missing-id' }

    // 去重：同一事件只报一次；容量满时淘汰最旧，防止长会话内存膨胀
    if (seenIds.has(id)) return { shown: false, spoke: false, reason: 'duplicate' }
    seenIds.add(id)
    while (seenIds.size > maxTrackedIds) {
      seenIds.delete(seenIds.values().next().value)
    }

    // 节流：窗内只提示第一条（事件仍计入去重集合）
    const at = now()
    if (at - lastNotifyAt < notifyGapMs) {
      return { shown: false, spoke: false, reason: 'throttled' }
    }
    lastNotifyAt = at

    const critical = isCriticalFault(faultEvent.severity)
    disarm()
    showAlert({
      id,
      critical,
      text: `发现异常「${faultEvent.title ?? '未知异常'}」（${faultEvent.severity ?? 'UNKNOWN'}）`
    })
    clearTimer = schedule(() => {
      clearTimer = null
      clearAlert()
    }, critical ? criticalHoldMs : normalHoldMs)
    playGesture('pointUp')

    // 出声决策：高危 + 空闲 + 非静音；守卫在决策层，注入的 speak 不必自检
    let spoke = false
    if (critical && !isBusy() && !isMuted()) {
      const label = faultEvent.severity === 'CRITICAL' ? '高危' : '较高级'
      speak(`发现${label}异常：${faultEvent.title}，请查看处置面板。`)
      spoke = true
    }
    return { shown: true, spoke }
  }

  /** 用户点气泡或组件卸载时主动收起 */
  function dismiss() {
    disarm()
    clearAlert()
  }

  return { handleFault, dismiss }
}
