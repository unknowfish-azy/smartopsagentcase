/**
 * 神经 TTS 客户端（ai-service /api/tts）。
 *
 * 开发环境走 Vite 的 /ai 代理到 :8001；生产用 VITE_AI_SERVICE_URL。
 * 接口不可用时（503/网络/未配置）直接抛错，由调用方如实回落浏览器语音，
 * 这里绝不生成占位音频。
 */

const AI_SERVICE_BASE = import.meta.env.VITE_AI_SERVICE_URL || '/ai'

export interface TtsProviderStatus {
  name: string
  display_name: string
  available: boolean
  reason: string
  detail?: Record<string, unknown>
}

export interface TtsVoiceStatus {
  name: string
  description?: string
  has_reference?: boolean
}

export interface TtsStatus {
  requested: string
  provider: string | null
  available: boolean
  reason: string
  providers: TtsProviderStatus[]
  voices: TtsVoiceStatus[]
}

/** 边界时间戳（毫秒）：来自后端 TTS 的真实事件，不是前端估算。 */
export interface TtsTimingWord {
  text: string
  offset_ms: number
  duration_ms: number
  /** 可选：服务端算出的真实韵母（音素级）；缺省表示只有边界、口型需前端近似 */
  viseme?: string
}

export interface TimedSpeech {
  blob: Blob
  /** 空数组 = 该 Provider 没有边界事件，调用方必须降级为近似口型 */
  timing: TtsTimingWord[]
  provider: string
  speedApplied: boolean
}

/** 取 Java 边缘签发的短时 run 令牌（TTS 复用聊天鉴权，只验签不消耗 run）。 */
async function resolveRunToken(): Promise<string> {
  const { default: fetchChatRunToken } = await import('./chatRunToken.ts')
  const issued = (await fetchChatRunToken()) as
    | { data?: { runToken?: string }; runToken?: string }
    | undefined
  const token =
    typeof issued?.data?.runToken === 'string'
      ? issued.data.runToken
      : typeof issued?.runToken === 'string'
        ? issued.runToken
        : ''
  if (!token) throw new Error('聊天鉴权令牌签发失败，无法调用神经语音')
  return token
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json()
    if (typeof payload?.message === 'string' && payload.message) return payload.message
    if (typeof payload?.detail?.code === 'string') return payload.detail.code
    if (typeof payload?.code === 'string') return payload.code
  } catch {
    // 非 JSON 响应：退回状态码
  }
  return `HTTP ${response.status}`
}

/** 查询 TTS 真实可用性与音色列表。 */
export async function fetchTtsStatus(): Promise<TtsStatus> {
  const token = await resolveRunToken()
  const response = await fetch(`${AI_SERVICE_BASE}/api/tts/status`, {
    headers: { 'X-Run-Token': token }
  })
  if (!response.ok) throw new Error(await errorMessage(response))
  return response.json()
}

/**
 * 合成语音，返回音频 Blob（WAV 或 MP3，取决于后端选中的 provider）。
 * @param text 待播报文本（上限由服务端 TTS_MAX_CHARS 控制）
 * @param options.voice 音色名；只有一条预设时服务端自动选用（在线音源忽略）
 * @param options.speed 语速；本地模型与在线音源都尽量支持，不支持的 provider 会回报 speed_applied=false
 */
export async function synthesizeSpeech(
  text: string,
  { voice, speed }: { voice?: string | null; speed?: number } = {}
): Promise<Blob> {
  const token = await resolveRunToken()
  const body: Record<string, unknown> = { text }
  if (voice) body.voice = voice
  if (typeof speed === 'number') body.speed = speed
  const response = await fetch(`${AI_SERVICE_BASE}/api/tts/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Run-Token': token },
    body: JSON.stringify(body)
  })
  if (!response.ok) throw new Error(await errorMessage(response))
  const blob = await response.blob()
  if (!blob || blob.size === 0) throw new Error('神经语音返回空音频')
  return blob
}

function decodeBase64(content: string): Uint8Array<ArrayBuffer> {
  const binary = globalThis.atob(content)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes
}

/** /api/tts/synthesize 的 JSON 响应（timing 模式）。 */
interface TtsTimingPayload {
  audio_base64?: string
  timing?: Array<{
    text?: string
    offset_ms?: number
    duration_ms?: number
    viseme?: string
  }>
  provider?: string
  speed_applied?: boolean
  media_type?: string
}

/**
 * 合成语音并取回词级时间戳（口型 timeline 模式用）。
 *
 * 后端此时返回 JSON（base64 音频 + timing[]）；timing 为空数组表示该 Provider
 * 没有边界事件（如本地 VoxCPM2/F5-TTS、百度音源），调用方必须如实降级。
 */
export async function synthesizeSpeechWithTiming(
  text: string,
  { voice, speed }: { voice?: string | null; speed?: number } = {}
): Promise<TimedSpeech> {
  const token = await resolveRunToken()
  const body: Record<string, unknown> = { text, timing: true }
  if (voice) body.voice = voice
  if (typeof speed === 'number') body.speed = speed
  const response = await fetch(`${AI_SERVICE_BASE}/api/tts/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Run-Token': token },
    body: JSON.stringify(body)
  })
  if (!response.ok) throw new Error(await errorMessage(response))
  const payload = (await response.json()) as Partial<TtsTimingPayload>
  const audioBase64 = typeof payload?.audio_base64 === 'string' ? payload.audio_base64 : ''
  if (!audioBase64) throw new Error('神经语音返回空音频')
  const bytes = decodeBase64(audioBase64)
  if (!bytes.length) throw new Error('神经语音返回空音频')
  const timing: TtsTimingWord[] = Array.isArray(payload?.timing)
    ? payload.timing
        .map((word) => ({
          text: typeof word?.text === 'string' ? word.text : '',
          offset_ms: Number(word?.offset_ms),
          duration_ms: Number(word?.duration_ms),
          ...(typeof word?.viseme === 'string' && word.viseme ? { viseme: word.viseme } : {})
        }))
        .filter(
          (word: TtsTimingWord) =>
            word.text &&
            Number.isFinite(word.offset_ms) &&
            word.offset_ms >= 0 &&
            Number.isFinite(word.duration_ms) &&
            word.duration_ms > 0
        )
    : []
  return {
    blob: new Blob([bytes], { type: payload?.media_type || 'audio/mpeg' }),
    timing,
    provider: typeof payload?.provider === 'string' ? payload.provider : '',
    speedApplied: Boolean(payload?.speed_applied)
  }
}

export default synthesizeSpeech
