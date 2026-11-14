/**
 * useCompositionFieldClock.js
 *
 * 把后端算出的 target field 做 spring 插值，输出"当前帧"的 field。
 *
 * 设计（DESIGN §4.1 + §4.2）：
 *   - spring：cur += (target - cur) * (1 - exp(-dt / tau))，tau = 0.28s
 *   - 迟滞：参数变化小于阈值时不更新 target，避免后端抖动让画面一直颤
 *   - 复用 motionScheduler（30fps），不自建 rAF
 *
 * 用法：
 *   const { current, setTarget, dispose } = useCompositionFieldClock(initialField)
 *   setTarget(newFieldFromBackend)   // 数据到达时调
 *   current.value                     // 插值后的当前值（Vue ref）
 */

import { ref, shallowRef } from 'vue'
import { subscribe } from '../../../visual/motionScheduler.js'

const TAU = 0.28 // 时间常数，秒

/** 迟滞阈值（DESIGN §4.2）：小于此值不更新 target */
const HYSTERESIS = {
  aperture: 0.02,
  tilt: 1.5,
  volume: 0.01,
  spin: 0.005,
  groove: 1,        // 整数，变化 1 条以上才更新
  grain: 0.01,
  gaze: 0.02,       // x/y 各自
  pulse: 0.1        // 秒
}

/** 中性默认值（数据未到或 stale 时使用） */
const NEUTRAL_FIELD = {
  aperture: 1.0,
  tilt: -12,
  volume: 1.0,
  spin: 0,
  groove: 8,
  grain: 0.5,
  gaze: { x: 0, y: 0 },
  pulse: 4.0
}

export function useCompositionFieldClock(initial = NEUTRAL_FIELD, reduced = false) {
  // 用浅引用避免深层响应式开销（每帧只替换顶层对象）
  const current = shallowRef(cloneField(initial))
  const target = cloneField(initial)
  let isReduced = reduced

  let stop = null
  let visibilityHandler = null

  // 逐帧 spring 插值
  const onFrame = (dtMs) => {
    // reduced-motion：不插值，直接落位（由 setReduced/snapTo 处理，这里跳过）
    if (isReduced) return

    const dt = Math.min(0.05, dtMs / 1000) // 秒，上限 50ms 防跳帧
    const k = 1 - Math.exp(-dt / TAU)
    const cur = current.value

    cur.aperture += (target.aperture - cur.aperture) * k
    cur.tilt += (target.tilt - cur.tilt) * k
    cur.volume += (target.volume - cur.volume) * k
    cur.spin += (target.spin - cur.spin) * k
    cur.groove += (target.groove - cur.groove) * k
    cur.grain += (target.grain - cur.grain) * k
    cur.gaze.x += (target.gaze.x - cur.gaze.x) * k
    cur.gaze.y += (target.gaze.y - cur.gaze.y) * k
    cur.pulse += (target.pulse - cur.pulse) * k

    // 收敛检测（DESIGN §10：数据不变时静置，画面必须完全静止）。
    // 所有参数与 target 的差都 < 1e-6 时跳过 shallowRef 替换，
    // 避免 Vue 因引用变化触发不必要的重渲染。
    const converged =
      Math.abs(target.aperture - cur.aperture) < 1e-6 &&
      Math.abs(target.tilt - cur.tilt) < 1e-6 &&
      Math.abs(target.volume - cur.volume) < 1e-6 &&
      Math.abs(target.spin - cur.spin) < 1e-6 &&
      Math.abs(target.groove - cur.groove) < 1e-6 &&
      Math.abs(target.grain - cur.grain) < 1e-6 &&
      Math.abs(target.gaze.x - cur.gaze.x) < 1e-6 &&
      Math.abs(target.gaze.y - cur.gaze.y) < 1e-6 &&
      Math.abs(target.pulse - cur.pulse) < 1e-6

    if (!converged) {
      current.value = { ...cur, gaze: { ...cur.gaze } }
    }
  }

  stop = subscribe(onFrame, { fps: 30, id: 'composition-field-clock' })

  /**
   * 离屏恢复时直接落位（DESIGN §8：不做补间）。
   * 监听 visibilitychange，从 hidden → visible 时 snapTo 当前 target。
   */
  if (typeof document !== 'undefined') {
    visibilityHandler = () => {
      if (!document.hidden) snapTo(target)
    }
    document.addEventListener('visibilitychange', visibilityHandler)
  }

  /**
   * 设置新的 target（后端数据到达时调用）。
   * 迟滞：每个参数单独判断，变化小于阈值则保留旧 target。
   * reduced-motion 时直接 snapTo，不经过 spring。
   */
  function setTarget(next) {
    if (!next) return
    const applySnap = isReduced
    const apply = (key, val, threshold) => {
      if (Math.abs(val - target[key]) >= threshold) target[key] = val
    }
    apply('aperture', next.aperture, HYSTERESIS.aperture)
    apply('tilt', next.tilt, HYSTERESIS.tilt)
    apply('volume', next.volume, HYSTERESIS.volume)
    apply('spin', next.spin, HYSTERESIS.spin)
    apply('groove', next.groove, HYSTERESIS.groove)
    apply('grain', next.grain, HYSTERESIS.grain)
    if (Math.abs(next.gaze.x - target.gaze.x) >= HYSTERESIS.gaze) target.gaze.x = next.gaze.x
    if (Math.abs(next.gaze.y - target.gaze.y) >= HYSTERESIS.gaze) target.gaze.y = next.gaze.y
    apply('pulse', next.pulse, HYSTERESIS.pulse)

    if (applySnap) snapTo(target)
  }

  /** 直接跳到指定值（无插值）—— reduced-motion 或离屏恢复时用 */
  function snapTo(value) {
    const v = value || NEUTRAL_FIELD
    target.aperture = v.aperture
    target.tilt = v.tilt
    target.volume = v.volume
    target.spin = v.spin
    target.groove = v.groove
    target.grain = v.grain
    target.gaze.x = v.gaze.x
    target.gaze.y = v.gaze.y
    target.pulse = v.pulse
    current.value = cloneField(v)
  }

  /** 切换 reduced-motion：开启时立即落位，关闭时恢复 spring 插值。 */
  function setReduced(value) {
    isReduced = Boolean(value)
    if (isReduced) snapTo(target)
  }

  function dispose() {
    if (stop) {
      stop()
      stop = null
    }
    if (visibilityHandler && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', visibilityHandler)
      visibilityHandler = null
    }
  }

  return { current, setTarget, snapTo, setReduced, dispose }
}

function cloneField(f) {
  return {
    aperture: f.aperture,
    tilt: f.tilt,
    volume: f.volume,
    spin: f.spin,
    groove: f.groove,
    grain: f.grain,
    gaze: { x: f.gaze.x, y: f.gaze.y },
    pulse: f.pulse
  }
}
