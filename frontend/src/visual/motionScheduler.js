/**
 * 全页共享 rAF 调度器（P3 性能收口）。
 *
 * 目标：把散落在各 Canvas/SVG 组件里的 ~20 个独立 requestAnimationFrame 循环
 * 收敛到 1 个循环；支持按订阅者设定帧率、离屏暂停、低帧率自动降级。
 *
 * 设计参考（仅借鉴架构，不复制代码）：
 *  - Edwson/GalaxyJS（MIT）：全页单一共享 rAF、离屏暂停、DPR 钳制
 *  - sohumsuthar/liquid-glass（MIT）：粒子 canvas 30fps、低帧率自动降级门控
 *
 * 用法：
 *   const stop = subscribe((dt, now) => { ... }, { fps: 30, id: 'ambient-field' })
 *   // 组件卸载时 stop()
 */
const DEFAULT_FPS = 30

const subscribers = new Map()
let frameId = 0
let running = false
let lastFrameAt = 0
let slowFrames = 0
let degraded = false
let hidden = false

export function isDegraded() {
  return degraded
}

export function activeLoopCount() {
  return running ? 1 : 0
}

export function subscriberCount() {
  return subscribers.size
}

function tick(now) {
  frameId = 0
  if (!running || hidden || subscribers.size === 0) return
  const elapsed = lastFrameAt ? now - lastFrameAt : 16
  lastFrameAt = now

  // 连续 3 帧超过 50ms 时全局降帧，避免低配设备被装饰层拖垮。
  if (elapsed > 50) slowFrames += 1
  else slowFrames = Math.max(0, slowFrames - 1)
  if (slowFrames >= 3 && !degraded) {
    degraded = true
    for (const entry of subscribers.values()) entry.fps = Math.min(entry.fps, 15)
  }

  const interval = degraded ? 1000 / 15 : 1000 / DEFAULT_FPS
  for (const entry of subscribers.values()) {
    /* 门控：距上次执行不足一个完整间隔则跳过（原公式 interval - fps*0.5 会让 30fps 目标实际跑到 ~54fps） */
    if (now - entry.last < interval) continue
    /* dt 是该订阅者两次执行的真实间隔（门控跳帧时 dt 会累积），与全局 rAF 间隔无关；
       否则高刷屏（rAF 120/196Hz）下 30fps 订阅者拿到的 dt 只有真实间隔的一小半 */
    const subDt = entry.last ? Math.min(now - entry.last, 100) : 16
    entry.last = now
    try {
      entry.fn(subDt, now)
    } catch (error) {
      // 单个订阅者异常不应拖垮整条调度链。
      console.warn('[motionScheduler] subscriber failed', entry.id, error)
    }
  }
  frameId = requestAnimationFrame(tick)
}

function ensureRunning() {
  if (running || hidden || subscribers.size === 0) return
  running = true
  lastFrameAt = 0
  frameId = requestAnimationFrame(tick)
}

function stopRunning() {
  running = false
  if (frameId) cancelAnimationFrame(frameId)
  frameId = 0
}

function onVisibilityChange() {
  hidden = typeof document !== 'undefined' && document.hidden
  if (hidden) stopRunning()
  else ensureRunning()
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', onVisibilityChange)
}

/**
 * 注册一个逐帧回调。
 * @param {(dt:number, now:number)=>void} fn
 * @param {{fps?:number, id?:string}} options
 * @returns {() => void} 取消订阅
 */
export function subscribe(fn, options = {}) {
  if (typeof fn !== 'function') return () => {}
  const id = options.id || `sub-${subscribers.size + 1}`
  const fps = Math.max(1, Math.min(60, Number(options.fps) || DEFAULT_FPS))
  subscribers.set(id, { id, fn, fps, last: 0 })
  ensureRunning()
  return () => {
    subscribers.delete(id)
    if (subscribers.size === 0) stopRunning()
  }
}

export function disposeScheduler() {
  subscribers.clear()
  stopRunning()
  if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', onVisibilityChange)
}

export default { subscribe, isDegraded, activeLoopCount, subscriberCount, disposeScheduler }
