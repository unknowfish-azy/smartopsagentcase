/**
 * 帧预算判定（纯逻辑，不依赖 three / DOM，便于单元测试）。
 *
 * 背景：共享 motionScheduler 会跳帧，回传给订阅者的 frameMs 是「相邻 rAF 间隔」，
 * 不是「两次真正渲染的间隔」。GPU 瓶颈下 rAF 仍是 16ms、实际只渲染 15fps，用回调值
 * 判断会让降级永远不触发，所以这里只接受调用方自己量出来的真实渲染间隔。
 */

export const SLOW_FRAME_MS = 20
export const SLOW_INTERVAL_MS = 60
export const SLOW_WINDOW_MS = 2000

/** 渲染间隔（毫秒）→ 动画步长（秒）；上限 100ms，避免长挂起后姿态瞬移 */
export function frameDeltaSeconds(intervalMs) {
  return Math.min(Math.max(intervalMs, 0), 100) / 1000
}

/**
 * @param {{ now?: () => number }} [options]
 */
export function createFrameBudget({ now = () => globalThis.performance?.now?.() ?? Date.now() } = {}) {
  // 用 null 而不是 0 做哨兵：测试或某些环境里 now() 可能正好从 0 开始
  let slowCostSince = null
  let slowIntervalSince = null
  let degraded = false

  /**
   * @param {number} cost 本帧 CPU 端耗时（毫秒）
   * @param {number} interval 与上一次真正渲染的间隔（毫秒）
   * @returns {boolean} 是否刚刚越过门槛；只会在越过的这一帧返回一次 true
   */
  function sample(cost, interval) {
    if (degraded) return false
    const timestamp = now()

    if (cost > SLOW_FRAME_MS) {
      if (slowCostSince === null) slowCostSince = timestamp
    } else {
      slowCostSince = null
    }

    if (interval >= SLOW_INTERVAL_MS) {
      if (slowIntervalSince === null) slowIntervalSince = timestamp
    } else {
      slowIntervalSince = null
    }

    const costTimedOut = slowCostSince !== null && timestamp - slowCostSince >= SLOW_WINDOW_MS
    const intervalTimedOut =
      slowIntervalSince !== null && timestamp - slowIntervalSince >= SLOW_WINDOW_MS
    if (!costTimedOut && !intervalTimedOut) return false

    degraded = true
    return true
  }

  return {
    sample,
    get degraded() {
      return degraded
    }
  }
}
