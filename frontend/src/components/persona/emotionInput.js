/**
 * 情绪识别输入的纯函数层（缺口清单 P2-8「数字人三短板」收口项）。
 *
 * 链路：用户文本 → `POST /api/nn/emotion` → `{label, confidence, engine, status}`
 *       → `withEmotion(profile, emotion)` → 新的状态 profile → 渲染层 `setState()`。
 *
 * 设计约束（与 docs/design/persona-emotion-input-v1/DESIGN.md 一致）：
 * - **只叠加、不覆盖**：情绪权重与状态权重按 `max` 合并，状态语义优先；
 * - **告警 / 故障态不叠加情绪**：`warning` / `error` 时一律原样返回，
 *   避免「用户说开心，告警中的小鱼就变高兴」这种语义冲突；
 * - **不伪造**：引擎不可用（`available=false` / `status!='SUCCEEDED'`）、
 *   标签未知、置信度缺失或低于阈值时，原样返回，不猜；
 * - 纯函数、无 Vue / 无网络，可被 `node --test` 直接单测。
 */

/** 渲染层实际支持的表情枚举（与 personaStates.js / personaGestures.js 一致）。 */
export const EMOTION_LABELS = Object.freeze(['happy', 'sad', 'angry', 'surprised', 'neutral'])

/** 情绪 → expressions 权重（只使用渲染层已有枚举）。 */
export const EMOTION_TO_EXPRESSION = Object.freeze({
  happy: Object.freeze({ happy: 0.6, relaxed: 0.2 }),
  sad: Object.freeze({ sad: 0.55, relaxed: 0.15 }),
  angry: Object.freeze({ angry: 0.6 }),
  surprised: Object.freeze({ surprised: 0.6 }),
  neutral: Object.freeze({ relaxed: 0.2 })
})

/** 低于该置信度不叠加（词典弱词 0.5 勉强过线，否定下调的 0.45 会被拦下）。 */
export const DEFAULT_MIN_CONFIDENCE = 0.5

/** 这些状态下情绪不得改变表情语义（状态主导）。 */
export const EMOTION_BLOCKED_STATES = Object.freeze(['warning', 'error'])

export const EMOTION_LABEL_TEXT = Object.freeze({
  happy: '开心',
  sad: '难过',
  angry: '生气',
  surprised: '惊讶',
  neutral: '平静'
})

export function normalizeEmotionLabel(label) {
  return String(label ?? '').trim().toLowerCase()
}

/**
 * 取情绪对应的 expressions 权重；不可用时返回 null（不伪造）。
 *
 * @param {{label?: string, confidence?: number|null, status?: string, available?: boolean}} emotion
 * @param {{minConfidence?: number}} [options]
 */
export function emotionExpression(emotion, { minConfidence = DEFAULT_MIN_CONFIDENCE } = {}) {
  if (!emotion || typeof emotion !== 'object') return null
  // 后端约定：available=false 时 label 恒为 neutral，不能当识别结果用。
  if (emotion.available === false) return null
  if (emotion.status && String(emotion.status).toUpperCase() !== 'SUCCEEDED') return null
  const label = normalizeEmotionLabel(emotion.label)
  const weights = EMOTION_TO_EXPRESSION[label]
  if (!weights) return null
  const confidence = Number(emotion.confidence)
  if (!Number.isFinite(confidence)) return null
  if (confidence < minConfidence) return null
  return weights
}

/**
 * 把情绪权重叠加到状态 profile 的 expressions 上，返回**新对象**（不改入参）。
 *
 * @param {{expressions?: Record<string, number>} & Record<string, unknown>} profile
 * @param {object} emotion 端点返回（或本地构造）的情绪结果
 * @param {{minConfidence?: number, state?: string|null}} [options]
 * @returns {object} 新 profile；不叠加时返回**原对象**（便于调用方判等）
 */
export function withEmotion(profile, emotion, { minConfidence = DEFAULT_MIN_CONFIDENCE, state = null } = {}) {
  const base = profile ?? {}
  // 告警 / 故障态：状态语义优先，情绪一律不叠加。
  if (state && EMOTION_BLOCKED_STATES.includes(state)) return base

  const weights = emotionExpression(emotion, { minConfidence })
  if (!weights) return base

  const current = base.expressions ?? {}
  const merged = { ...current }
  for (const [key, value] of Object.entries(weights)) {
    const previous = Number(merged[key])
    merged[key] = Math.max(Number.isFinite(previous) ? previous : 0, Number(value) || 0)
  }
  return { ...base, expressions: merged }
}

/**
 * 情绪来源档位的中文标注（UI 如实展示，不写「高精度」「已识别」这类夸张措辞）。
 * @returns {{ text: string, tone: 'model'|'lexicon'|'none' }}
 */
export function emotionSourceLabel(emotion) {
  const engine = String(emotion?.engine ?? '')
  if (emotion?.available === false || !emotion) {
    return { text: '情绪未识别', tone: 'none' }
  }
  if (engine.includes('model')) return { text: '本地模型', tone: 'model' }
  if (engine.includes('lexicon')) return { text: '词典兜底', tone: 'lexicon' }
  return { text: '情绪未识别', tone: 'none' }
}

/** 情绪标签的中文文案；未知标签回退「未知」。 */
export function emotionLabelText(label) {
  return EMOTION_LABEL_TEXT[normalizeEmotionLabel(label)] ?? '未知'
}
