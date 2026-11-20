/**
 * 桌宠神经语音播放器：纯逻辑，不依赖 Vue。
 *
 * 与 petSpeech（浏览器 speechSynthesis）的分工：
 *  - 优先用后端合成的音频（本地 VoxCPM2/F5-TTS，或在线 Edge 神经语音 / 百度女声，
 *    由后端 provider 自动挑选，真实格式可能是 WAV 也可能是 MP3），音色统一；
 *  - 失败/不可用返回 false，由调用方回落 speechSynthesis —— 这里绝不假装播放成功；
 *  - 口型优先用后端回传的词级时间戳（Edge WordBoundary）；没有时间戳的 Provider
 *    （本地 VoxCPM2/F5-TTS、百度音源）由调用方按真实音频时长反推 cps 近似驱动。
 */

/**
 * @param {{
 *   fetchStatus: () => Promise<{ available: boolean, provider?: string | null, reason?: string }>,
 *   synthesize: (text: string, options?: { voice?: string, speed?: number }) => Promise<Blob>,
 *   synthesizeWithTiming?: (text: string, options?: { voice?: string, speed?: number }) =>
 *     Promise<{ blob: Blob, timing?: Array<{ text: string, offset_ms: number, duration_ms: number }> }>,
 *   createAudio?: (url: string) => any,
 *   createObjectUrl?: (blob: Blob) => string,
 *   revokeObjectUrl?: (url: string) => void,
 *   playbackRate?: number,
 *   onEnd?: () => void,
 *   onError?: (reason: string) => void
 * }} options
 */
export function createPetNeuralTts(options = {}) {
  const {
    fetchStatus,
    synthesize,
    synthesizeWithTiming = null,
    createAudio = (url) => new globalThis.Audio(url),
    createObjectUrl = (blob) => globalThis.URL.createObjectURL(blob),
    revokeObjectUrl = (url) => globalThis.URL.revokeObjectURL(url),
    // 音高统一由服务端掌握（Edge 走 SSML pitch，默认 +18Hz ≈ 两个半音）。
    // 默认 1.0 不再叠加：两处同时上抬会把少女音推成花栗鼠音、并且带来"电子味"。
    playbackRate = 1.0,
    onEnd = () => {},
    onError = () => {}
  } = options

  let status = null
  let statusPromise = null
  let statusAt = 0
  let audio = null
  let objectUrl = ''
  let disposed = false
  let lastError = ''
  let lastDurationMs = 0
  /** 最近一次合成拿到的词级时间戳；空数组 = 后端没有边界事件，调用方需降级 */
  let lastTiming = []
  /** 播放代际：每次 stop/speak 递增，旧合成结果回来时据此作废，避免两句叠着播 */
  let generation = 0
  /** 负向状态（服务不可用）的缓存时间：超过就重新探测，不能把整场会话钉死在浏览器音色上 */
  const STATUS_RETRY_MS = 15000

  function cleanup() {
    if (audio) {
      audio.onended = null
      audio.onerror = null
      try {
        audio.pause?.()
      } catch {
        // 已释放的播放器 pause 可能抛错，忽略
      }
      audio = null
    }
    if (objectUrl) {
      revokeObjectUrl(objectUrl)
      objectUrl = ''
    }
  }

  /** 查询后端真实可用性；失败不抛错，返回 available=false + 原因。 */
  function probe({ force = false } = {}) {
    if (disposed) return Promise.resolve({ available: false, reason: '已释放' })
    const negativeStale = status?.available === false && Date.now() - statusAt > STATUS_RETRY_MS
    if (!force && statusPromise && !negativeStale) return statusPromise
    statusPromise = (async () => {
      try {
        const result = await fetchStatus()
        status = result
        statusAt = Date.now()
        return result
      } catch (error) {
        statusAt = Date.now()
        status = {
          available: false,
          provider: null,
          reason: `TTS 状态查询失败：${error?.message ?? error}`
        }
        // 允许下次重试（服务可能后启动或刚装好依赖）
        statusPromise = null
        return status
      }
    })()
    return statusPromise
  }

  /**
   * 只合成不播放：流式分句时在当前句播报期间预合成下一句，播完即可无缝接上。
   * @returns {Promise<{ blob: Blob, timing: Array<object>, text: string } | null>}
   */
  async function prepare(text, { voice, speed } = {}) {
    const content = String(text ?? '').trim()
    if (disposed || !content) return null
    const current = await probe()
    if (disposed || !current?.available) return null
    const mine = generation
    try {
      let blob
      let timing = []
      if (synthesizeWithTiming) {
        const result = await synthesizeWithTiming(content, { voice, speed })
        blob = result?.blob
        timing = Array.isArray(result?.timing) ? result.timing : []
      } else {
        blob = await synthesize(content, { voice, speed })
      }
      if (disposed || mine !== generation) return null
      if (!blob || (typeof blob.size === 'number' && blob.size === 0)) {
        throw new Error('后端返回空音频')
      }
      return { blob, timing, text: content }
    } catch (error) {
      // 合成失败不当作播放成功：交给调用方统一回落，避免逐句换引擎
      lastError = String(error?.message ?? error)
      return null
    }
  }

  /** 播放 prepare() 产出的音频；返回 false 表示调用方应回落浏览器语音 */
  async function playPrepared(prepared) {
    if (disposed || !prepared?.blob) return false
    stop()
    const mine = generation
    const { blob, timing = [] } = prepared
    lastTiming = []
    try {
      objectUrl = createObjectUrl(blob)
      const element = createAudio(objectUrl)
      audio = element
      // preservesPitch=false 让 playbackRate 抬音高（默认浏览器会做时间伸缩，听不出变化）
      element.preservesPitch = false
      element.mozPreservesPitch = false
      element.webkitPreservesPitch = false
      element.playbackRate = playbackRate
      element.onended = () => {
        cleanup()
        onEnd()
      }
      element.onerror = () => {
        cleanup()
        lastError = '神经语音播放失败'
        onError(lastError)
      }
      await element.play()
      if (disposed || mine !== generation) {
        // 已有更新的播报接手：只停掉自己这一个元素，不要动共享引用（否则会掐掉新播报）
        try {
          element.pause?.()
        } catch {
          // 元素已释放，忽略
        }
        return false
      }
      // 真实时长用于口型：播放倍率已折算回原速，供调用方算 cps
      const seconds = Number(element.duration)
      lastDurationMs = Number.isFinite(seconds) && seconds > 0 ? (seconds * 1000) / playbackRate : 0
      // 播放真正起来了才公开时间戳：合成成功但自动播放被拦时，
      // 调用方会回落浏览器语音，不能拿这份时间戳去驱动错位的口型
      lastTiming = timing
      return true
    } catch (error) {
      // 合成/自动播放失败：不当作"播放成功"，交给调用方回落
      cleanup()
      lastError = String(error?.message ?? error)
      return false
    }
  }

  /**
   * 合成并播放一段文本。
   * @returns {Promise<boolean>} true = 神经音频已开始播放；false = 调用方应回落浏览器语音
   */
  async function speak(text, options = {}) {
    // 先停旧音频再合成：单次播报语义下，新语音应立即接管，不等合成完成
    stop()
    const prepared = await prepare(text, options)
    if (!prepared) return false
    return playPrepared(prepared)
  }

  function stop() {
    generation += 1
    cleanup()
  }

  function dispose() {
    if (disposed) return
    disposed = true
    stop()
  }

  return {
    probe,
    speak,
    prepare,
    playPrepared,
    stop,
    dispose,
    get status() {
      return status
    },
    get lastError() {
      return lastError
    },
    /** 最近一次真正播放起来的音频时长（毫秒，已折算回原速）；0 表示未知 */
    get lastDurationMs() {
      return lastDurationMs
    },
    /** 最近一次合成的词级时间戳（毫秒）；空数组表示没有边界事件，只能近似驱动口型 */
    get lastTiming() {
      return lastTiming
    },
    /** 当前正在播放的 <audio> 元素；调用方用它把音频接进口型分析链（音频主时钟） */
    get audioElement() {
      return audio
    }
  }
}
