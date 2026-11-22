import request from '../utils/request.ts'

/**
 * 情绪识别输入接口层（P2-8）。
 *
 * 端点：`POST /api/nn/emotion`、`GET /api/nn/emotion-info`。
 *
 * 降级契约：网络失败 / 后端不可用一律返回 `null`，**不抛错、不伪造标签**，
 * 由调用方决定「不叠加情绪」——情绪只是状态 profile 的加成层。
 */

const BASE = '/api/nn'

export interface EmotionResult {
  available: boolean
  ok: boolean
  reason: string | null
  engine: string
  label: string
  confidence: number | null
  scores: Record<string, number>
  warnings: string[]
  /** 引擎状态：SUCCEEDED / EMPTY / UNAVAILABLE（后端如实回传） */
  status?: string
  elapsed_ms: number
}

export interface EmotionInfo {
  available: boolean
  engine: string | null
  reason: string | null
  labels: string[]
  model: string | null
  model_available: boolean
  model_dimension: string
  license_status: string
}

/**
 * 响应拦截器返回的是统一包装 `{code, message, data}`，这里拆出 data；
 * 与项目内其它 api 模块的 `unwrap` 约定一致（兼容未包装的直接返回）。
 */
function unwrap<T>(payload: unknown): T {
  const candidate = payload as { data?: unknown } | null
  return (candidate && typeof candidate === 'object' && 'data' in candidate ? candidate.data : payload) as T
}

/** 文本 → 情绪标签；空文本或请求失败返回 null（不叠加）。 */
export async function recognizeEmotion(text: string, maxText = 0): Promise<EmotionResult | null> {
  const trimmed = String(text ?? '').trim()
  if (!trimmed) return null
  try {
    const data = await request({
      url: `${BASE}/emotion`,
      method: 'post',
      data: { text: trimmed, max_text: maxText }
    })
    return unwrap<EmotionResult>(data) ?? null
  } catch {
    return null
  }
}

/** 引擎状态探针；失败返回 null。 */
export async function fetchEmotionInfo(): Promise<EmotionInfo | null> {
  try {
    const data = await request({ url: `${BASE}/emotion-info`, method: 'get' })
    return unwrap<EmotionInfo>(data) ?? null
  } catch {
    return null
  }
}

export default recognizeEmotion
