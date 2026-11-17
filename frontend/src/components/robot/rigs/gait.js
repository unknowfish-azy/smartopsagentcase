/**
 * 机器人步态解算（纯函数，无 three 依赖，可直接被 node --test 覆盖）。
 *
 * 四足（仿宇树 Go2）：
 *   - TROT：对角腿同相（FL+RR / FR+RL 相差 π），中高速默认
 *   - WALK：四拍步态，相位 0 / π/2 / π / 3π/2
 *   - STAND：速度低于阈值或显式指定时站立，全部关节回静态姿态
 *
 * 角度单位为弧度，符号约定：
 *   thigh > 0 足端向前摆；calf > 0 屈膝（小腿相对大腿回折）；hip > 0 外展
 */

export const QUADRUPED_LEGS = Object.freeze(['FL', 'FR', 'RL', 'RR'])

export const QUADRUPED_PHASE_OFFSETS = Object.freeze({
  TROT: Object.freeze({ FL: 0, RR: 0, FR: Math.PI, RL: Math.PI }),
  WALK: Object.freeze({ FL: 0, RR: Math.PI * 0.5, FR: Math.PI, RL: Math.PI * 1.5 })
})

/** 判定「静止」的线速度阈值（m/s），与遥控档位的 TROT 下限对齐。 */
export const STAND_SPEED_THRESHOLD = 0.03
/** 步幅归一化基准：来自 TELEOP_PROFILES.DOG.maxSpeed.linear。 */
export const QUADRUPED_MAX_LINEAR = 0.35
/** 人形步幅归一化基准（保守值，仅驱动视觉摆动，不参与限速）。 */
export const HUMANOID_MAX_LINEAR = 0.6

/** 四足站立静态姿态（无步态时保持蹲伏，与真机站立高度一致）。 */
export const QUADRUPED_STAND_POSE = Object.freeze({ hip: 0, thigh: -0.18, calf: 0.62 })

export function clamp(value, min, max) {
  if (!Number.isFinite(value)) return min
  return Math.min(max, Math.max(min, value))
}

/** 解析实际生效步态：显式 STAND 优先，其余按速度阈值兜底。 */
export function resolveGait(requested, speed) {
  const mode = String(requested || '').toUpperCase()
  if (mode === 'STAND') return 'STAND'
  const s = Math.abs(Number(speed) || 0)
  if (s < STAND_SPEED_THRESHOLD) return 'STAND'
  return mode === 'WALK' ? 'WALK' : 'TROT'
}

/**
 * 四足步态解算。
 * @param {{gait?: string, speed?: number, t?: number, strideHz?: number}} input
 *   t 为累计秒数；speed 为带符号线速度（负值 = 后退，步态相位反向）
 * @returns {{mode: string, amp: number, freq: number, legs: Record<string, {hip:number,thigh:number,calf:number}>, body: {bob:number, pitch:number}}}
 */
export function quadrupedPose({ gait = 'TROT', speed = 0, t = 0, strideHz } = {}) {
  const mode = resolveGait(gait, speed)
  const signed = Number(speed) || 0
  const amp = mode === 'STAND' ? 0 : clamp(Math.abs(signed) / QUADRUPED_MAX_LINEAR, 0, 1)
  const freq = strideHz ?? (mode === 'WALK' ? 1.1 : 1.7)
  const offsets = QUADRUPED_PHASE_OFFSETS[mode] || QUADRUPED_PHASE_OFFSETS.TROT
  const dir = signed < 0 ? -1 : 1
  const time = Number.isFinite(t) ? t : 0

  const legs = {}
  for (const leg of QUADRUPED_LEGS) {
    const phase = time * freq * Math.PI * 2 + (offsets[leg] || 0)
    const swing = Math.sin(phase) * amp * dir
    const lift = Math.max(0, Math.sin(phase)) * amp
    legs[leg] = {
      hip: 0.06 * Math.sin(phase) * amp,
      thigh: QUADRUPED_STAND_POSE.thigh + 0.42 * swing,
      calf: QUADRUPED_STAND_POSE.calf + 0.55 * lift
    }
  }

  return {
    mode,
    amp,
    freq,
    legs,
    body: {
      /* 步频两倍的上下起伏（对角腿落地时的重心下沉） */
      bob: amp * 0.012 * Math.sin(time * freq * Math.PI * 4),
      pitch: amp * 0.03 * Math.sin(time * freq * Math.PI * 2)
    }
  }
}

/**
 * 人形步态解算（仿宇树 G1）：双腿反相摆动，双臂与对侧腿同相。
 */
export function humanoidPose({ speed = 0, t = 0, strideHz = 1.05 } = {}) {
  const signed = Number(speed) || 0
  const amp = clamp(Math.abs(signed) / HUMANOID_MAX_LINEAR, 0, 1)
  const freq = strideHz
  const time = Number.isFinite(t) ? t : 0
  const phase = time * freq * Math.PI * 2
  const dir = signed < 0 ? -1 : 1
  const swing = Math.sin(phase) * amp * dir
  const cycle = Math.abs(Math.cos(phase)) * amp

  return {
    amp,
    freq,
    legs: {
      L: { thigh: 0.42 * swing, calf: 0.55 * Math.max(0, -swing) + 0.06, foot: -0.2 * swing },
      R: { thigh: -0.42 * swing, calf: 0.55 * Math.max(0, swing) + 0.06, foot: 0.2 * swing }
    },
    arms: {
      L: { upper: -0.38 * swing, fore: 0.3 + 0.18 * Math.abs(swing) },
      R: { upper: 0.38 * swing, fore: 0.3 + 0.18 * Math.abs(swing) }
    },
    torso: { bob: 0.015 * cycle, yaw: -0.06 * swing }
  }
}
