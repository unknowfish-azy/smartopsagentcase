/**
 * 2D 动态兜底（L2）的纯数据映射：七状态 → 2D 视觉变量。
 *
 * 为什么单独一层：
 *  - 移动端 / 无 WebGL / 轻量档位不加载 3D，但静态立绘又失去"数字人"的说服力；
 *  - 这里只做状态 → 数值的纯映射，不碰 DOM / Vue，渲染层见 usePersona2D.js；
 *  - 沿用 personaStates.js 的七状态与姿态增量，不新增状态定义，也不复制一套姿态表。
 */
import { personaProfile } from './personaStates.js'

const RAD_TO_DEG = 180 / Math.PI

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

function round(value, digits = 0) {
  const scale = 10 ** digits
  return Math.round(value * scale) / scale
}

/** 呼吸周期：speed 越大周期越短，限制在 1.8–5.5s，避免过快或接近静止 */
export function breathDurationSec(speed) {
  const safe = clamp(Number(speed) || 1.35, 0.8, 2.4)
  return round(clamp(4.2 / safe, 1.8, 5.5), 2)
}

/**
 * 状态 → 2D 视觉参数（角度用度、位移用 px）。
 * 2D 没有三维骨骼，需要把弧度适度放大，肉眼才看得出状态差异。
 */
export function build2DVisual(state) {
  const profile = personaProfile(state)
  const pose = profile.pose ?? {}
  const gaze = profile.gaze ?? {}
  const expressions = profile.expressions ?? {}
  const motion = profile.motion ?? {}

  const head = pose.head ?? {}
  const chest = pose.chest ?? {}
  const happy = Number(expressions.happy) || 0
  const sad = Number(expressions.sad) || 0
  const angry = Number(expressions.angry) || 0
  const relaxed = Number(expressions.relaxed) || 0

  return {
    state,
    accent: profile.glow,
    headTilt: round((head.z ?? 0) * RAD_TO_DEG * 1.6, 1),
    headNod: round((head.x ?? 0) * 60, 1),
    headTurn: round((head.y ?? 0) * 16, 1),
    bodyShift: round((chest.x ?? 0) * 40, 1),
    gazeX: round((gaze.yaw ?? 0) * 6, 1),
    gazeY: round((gaze.pitch ?? 0) * 4, 1),
    browLift: round(relaxed * 2 - angry * 3 + sad * 1.5, 1),
    browAngle: round(angry * 12 - sad * 6, 1),
    eyeOpen: round(clamp(1 - sad * 0.25 + happy * 0.08, 0.55, 1.15), 2),
    blush: round(clamp(0.1 + happy * 0.35, 0, 0.5), 2),
    mouthCurve: round(clamp(happy * 0.5 - sad * 0.4 + relaxed * 0.1, -0.5, 0.5), 2),
    breathDuration: breathDurationSec(motion.breathSpeed),
    breathAmp: Math.round(clamp(Number(motion.breathAmp) || 0.012, 0.004, 0.03) * 320)
  }
}

/**
 * 口型权重 → 2D 嘴巴的开口 / 宽度倍率。
 * 只做形状映射，不做平滑（平滑在 useLipSync 里完成）。
 */
export function mouthShape(weights = {}) {
  const aa = clamp(Number(weights.aa) || 0, 0, 1)
  const ih = clamp(Number(weights.ih) || 0, 0, 1)
  const ou = clamp(Number(weights.ou) || 0, 0, 1)
  const ee = clamp(Number(weights.ee) || 0, 0, 1)
  const oh = clamp(Number(weights.oh) || 0, 0, 1)

  const open = clamp(aa * 0.9 + oh * 0.75 + ou * 0.55 + ee * 0.35 + ih * 0.3, 0, 1)
  const wide = 1 + (ee + ih) * 0.35 - (ou + oh) * 0.2

  return {
    open: round(Math.max(open, 0.08), 3),
    wide: round(clamp(wide, 0.72, 1.28), 3)
  }
}

/**
 * 手势名 → 2D 动画类。3D 手势库有 34 个，2D 只需要归一到几组能看出差别的动作，
 * 未知手势统一给"应答"动作，避免调用方必须维护一份白名单。
 */
export function gestureClass(name) {
  const text = String(name ?? '').toLowerCase()
  if (!text) return 'ack'
  if (/wave|hello|greet|hand|挥手|招手|致意/.test(text)) return 'wave'
  if (/bow|鞠躬|欠身/.test(text)) return 'bow'
  if (/point|指|引路|方向/.test(text)) return 'point'
  if (/think|托腮|思考/.test(text)) return 'think'
  if (/nod|点头|确认/.test(text)) return 'nod'
  if (/shy|害羞|低头/.test(text)) return 'shy'
  return 'ack'
}

/** 手势动画时长：调用方与 CSS 共用，避免两边各写一个魔法数字 */
export const GESTURE_MS = 900
