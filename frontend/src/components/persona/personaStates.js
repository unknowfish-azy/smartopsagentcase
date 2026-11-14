/** 七个状态的共用枚举与中文标签。 */
export const PERSONA_STATES = Object.freeze([
  'idle',
  'thinking',
  'executing',
  'observing',
  'warning',
  'error',
  'recovering'
])

export const PERSONA_STATE_LABELS = Object.freeze({
  idle: '待机',
  thinking: '思考',
  executing: '执行',
  observing: '观察',
  warning: '告警',
  error: '故障',
  recovering: '恢复'
})

/**
 * 基准姿态（弧度）。来自 VRM 的 T-pose：上臂先放下，其余为零。
 * 每个状态的 pose 只写「相对基准的增量」，避免七个状态互相复制大量数字。
 */
export const PERSONA_POSE_BASE = Object.freeze({
  head: Object.freeze({ x: 0, y: 0, z: 0 }),
  chest: Object.freeze({ x: 0, y: 0, z: 0 }),
  leftUpperArm: Object.freeze({ x: 0, y: 0, z: 1.15 }),
  rightUpperArm: Object.freeze({ x: 0, y: 0, z: -1.15 })
})

/**
 * 状态 → 表情 / 姿态 / 视线 / 节奏（纯数据）。
 *
 * 设计约束：**灰度下也要能分辨**，所以状态差异主要靠头颈角度、躯干倾角、手臂开合、
 * 动作节奏（点头 / 摇头 / 抖动 / 呼吸频率），颜色只作为第三通道。
 */
export const PERSONA_STATE_PROFILES = Object.freeze({
  idle: Object.freeze({
    expressions: { relaxed: 0.25 },
    pose: {},
    gaze: { yaw: 0, pitch: 0 },
    motion: { breathSpeed: 1.35, breathAmp: 0.012 },
    accent: 'neutral',
    hint: '待机 · 等待任务'
  }),
  thinking: Object.freeze({
    expressions: { relaxed: 0.15 },
    // 头右倾 + 微仰，肩略内收：一眼能看出在「想」
    pose: {
      head: { x: -0.05, z: 0.18 },
      chest: { x: -0.02, z: -0.02 },
      leftUpperArm: { z: 0.1 }
    },
    gaze: { yaw: 0.18, pitch: 0.22 },
    motion: { breathSpeed: 1.7, breathAmp: 0.01, nod: { freq: 0.5, amp: 0.012 } },
    accent: 'primary',
    hint: '思考 · 推理中'
  }),
  executing: Object.freeze({
    expressions: {},
    // 前倾 + 轻微点头节律：在「动手」
    pose: { head: { x: 0.08 }, chest: { x: 0.1 } },
    gaze: { yaw: 0, pitch: 0.02 },
    motion: { breathSpeed: 1.55, breathAmp: 0.014, nod: { freq: 1.7, amp: 0.022 } },
    accent: 'primary',
    hint: '执行 · 正在操作'
  }),
  observing: Object.freeze({
    expressions: { relaxed: 0.2 },
    // 头带躯干一起右转，慢速扫视：在「看」
    pose: { head: { y: 0.22, x: 0.01 }, chest: { y: 0.09 } },
    gaze: { yaw: 0.45, pitch: 0 },
    motion: { breathSpeed: 1.2, breathAmp: 0.012, sway: { freq: 0.22, amp: 0.1 } },
    accent: 'primary',
    hint: '观察 · 正在巡检'
  }),
  warning: Object.freeze({
    expressions: { angry: 0.45 },
    // 头微低、双肩收紧、小幅摇头：在「示警」
    pose: {
      head: { x: 0.08 },
      chest: { x: 0.05 },
      leftUpperArm: { z: 0.18 },
      rightUpperArm: { z: -0.18 }
    },
    gaze: { yaw: 0, pitch: -0.08 },
    motion: { breathSpeed: 2.1, breathAmp: 0.016, sway: { freq: 1.6, amp: 0.055 } },
    accent: 'warning',
    hint: '告警 · 指标越界'
  }),
  error: Object.freeze({
    expressions: { sad: 0.55, angry: 0.2 },
    // 明显低头 + 前倾 + 双臂内垂 + 抖动
    pose: {
      head: { x: 0.24 },
      chest: { x: 0.12 },
      leftUpperArm: { z: 0.22, x: 0.05 },
      rightUpperArm: { z: -0.22, x: 0.05 }
    },
    gaze: { yaw: 0, pitch: -0.4 },
    motion: { breathSpeed: 0.95, breathAmp: 0.008, jitter: 0.004 },
    accent: 'danger',
    hint: '故障 · 执行中断'
  }),
  recovering: Object.freeze({
    expressions: { relaxed: 0.35, happy: 0.12 },
    // 缓慢抬头、肩放松：在「回血」，节奏刻意更慢
    pose: { head: { x: -0.1 }, chest: { x: -0.03 } },
    gaze: { yaw: 0, pitch: 0.08 },
    motion: { breathSpeed: 1.05, breathAmp: 0.02 },
    accent: 'success',
    hint: '恢复 · 正在收敛'
  })
})

/** error → recovering 的换场要慢一倍多，其他状态之间用默认值 */
export const PERSONA_STATE_FADE_MS = 350
export const PERSONA_RECOVERY_FADE_MS = 1200

export function personaTransitionMs(previous, next) {
  if (previous === 'error' && next === 'recovering') return PERSONA_RECOVERY_FADE_MS
  return PERSONA_STATE_FADE_MS
}

export function personaProfile(state) {
  return PERSONA_STATE_PROFILES[state] ?? PERSONA_STATE_PROFILES.idle
}
