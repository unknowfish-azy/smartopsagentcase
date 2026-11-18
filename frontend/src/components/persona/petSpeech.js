/**
 * 桌宠语音：包一层 speechSynthesis，把「播报进度」变成可订阅的字符边界流。
 *
 * 口型同步的关键：useLipSync 的文字时间线是按 cps 自由跑钟的，而 TTS 实际语速
 * 因系统音色/文本而异，两者会漂移。speechSynthesis 的 boundary 事件（Chrome/Edge
 * 支持）在词边界回调 charIndex，正好用来周期性校正口型时间线。
 *
 * 有的环境不发 boundary（如部分 Firefox 中文音色）：回退为按 cps 估算的定时推进，
 * 只保证「有起伏、能闭嘴」，UI 如实标注近似。
 */

const FALLBACK_TICK_MS = 120
const FALLBACK_ARM_MS = 800
/** 无 boundary 时的估算语速（字符/秒），与 useLipSync 的 DEFAULT_CPS 同量级 */
const FALLBACK_CPS = 5

/**
 * 甜妹少女音的选型偏好（按顺序命中，越靠前越优先）。
 * 各环境可用音色差异很大，这里只做「有就优先用」的软偏好：
 *  - Windows 系统音色：慧慧 / 瑶瑶（女），康康（男，排除）；
 *  - Edge / Chrome 的在线自然音色：晓伊（活泼少女）、晓晓（温柔）；
 *  - 其他平台的中文女声若名字带 female / 女 也能兜底命中。
 */
const SWEET_VOICE_HINTS = Object.freeze([
  'xiaoyi', '晓伊',
  'xiaoxiao', '晓晓',
  'xiaomo', '晓梦',
  'xiaohan', '晓涵',
  'huihui', '慧慧',
  'yaoyao', '瑶瑶',
  'female', '女'
])
/** 明确是男声的音色，直接排除，避免默认落到云希/康康这类音色上 */
const MALE_VOICE_HINTS = Object.freeze([
  'kangkang', 'yunxi', 'yunjian', 'yunyang',
  '康康', '云希', '云健', '云扬',
  'male'
])

/**
 * 从系统音色表里挑一个最接近「甜妹少女音」的中文音色。
 * @param {SpeechSynthesisVoice[]} voices
 * @returns {SpeechSynthesisVoice | null} 无中文音色时返回 null（交给系统默认）
 */
export function pickSweetVoice(voices) {
  if (!Array.isArray(voices) || voices.length === 0) return null
  const chinese = voices.filter((voice) => {
    const name = String(voice?.name ?? '').toLowerCase()
    if (!/^zh/i.test(String(voice?.lang ?? ''))) return false
    return !MALE_VOICE_HINTS.some((hint) => name.includes(hint))
  })
  if (chinese.length === 0) return null
  let best = null
  let bestScore = Number.POSITIVE_INFINITY
  for (const voice of chinese) {
    const name = String(voice?.name ?? '').toLowerCase()
    const hint = SWEET_VOICE_HINTS.findIndex((item) => name.includes(item))
    // 命中偏好词的按顺序排；natural 音色质量更好，在同档内优先
    let score = hint >= 0 ? hint * 10 : 1000
    if (name.includes('natural')) score -= 5
    if (score < bestScore) {
      bestScore = score
      best = voice
    }
  }
  return best
}

export function isSpeechSynthesisAvailable() {
  return typeof globalThis !== 'undefined' && typeof globalThis.speechSynthesis === 'object'
}

/**
 * 浏览器兜底朗读前，把会被逐字母念出的技术缩写换成中文读法。
 *
 * 后端的数字/单位规范化只在 piper-plus 合成前生效；神经语音整条链路失败、
 * 回落到 speechSynthesis 时拿到的是原文，QPS 会被念成「Q U P S」这种字母串。
 * 这里只改写「读出来一定是错的」的缩写，其余内容原样朗读，不改写语义。
 */
const SPEECH_ABBREVIATIONS = Object.freeze([
  [/(?<![A-Za-z])QPS(?![A-Za-z])/gi, '每秒查询数'],
  [/(?<![A-Za-z])IOPS(?![A-Za-z])/gi, '每秒读写次数'],
  [/(?<![A-Za-z])dpi(?![A-Za-z])/gi, '每英寸点数'],
  [/(?<![A-Za-z])fps(?![A-Za-z])/gi, '帧每秒'],
  [/(?<![A-Za-z])mAh(?![A-Za-z])/gi, '毫安时'],
  [/(?<![A-Za-z])kWh(?![A-Za-z])/gi, '千瓦时'],
  [/(?<![A-Za-z])Wh(?![A-Za-z])/g, '瓦时'],
  // ms/px 只在跟在数字后时替换，避免把 MS SQL 这类专有名词读成"毫秒"
  [/(?<=\d)\s*ms(?![A-Za-z])/gi, '毫秒'],
  [/(?<=\d)\s*px(?![A-Za-z])/gi, '像素'],
  // 带斜杠的速率单位单独处理：读成「GB 每秒」而不是逐字母
  [/(\d)\s*GB\/s/gi, '$1GB每秒'],
  [/(\d)\s*MB\/s/gi, '$1MB每秒']
])

/**
 * 生成浏览器兜底播报用的文本：去 markdown 噪音与裸链接，再替换缩写读法。
 * @param {string} text
 * @returns {string}
 */
export function normalizeSpeechText(text) {
  let spoken = String(text ?? '')
  spoken = spoken.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1') // markdown 链接只念文字
  spoken = spoken.replace(/https?:\/\/\S+/g, '')           // 裸链接不念
  spoken = spoken.replace(/[*`]+/g, '')                    // 加粗/行内代码标记不念
  for (const [pattern, replacement] of SPEECH_ABBREVIATIONS) {
    spoken = spoken.replace(pattern, replacement)
  }
  return spoken.replace(/\s+/g, ' ').trim()
}

/**
 * @param {{ onBoundary?: (charIndex: number) => void, onEnd?: () => void, onError?: (reason: string) => void, now?: () => number, setTimeout?: typeof setTimeout, clearTimeout?: typeof clearTimeout }} [handlers]
 */
export function createPetSpeech(handlers = {}) {
  const {
    onBoundary = () => {},
    onEnd = () => {},
    onError = () => {},
    now = () => Date.now(),
    setTimeoutFn = (fn, ms) => globalThis.setTimeout(fn, ms),
    clearTimeoutFn = (id) => globalThis.clearTimeout(id)
  } = handlers

  let utterance = null
  let fallbackTimer = 0
  let armTimer = 0
  let fallbackIndex = 0
  let boundarySeen = false
  let startedAt = 0
  let disposed = false
  let cachedVoice

  /**
   * 解析甜妹音色。音色表未加载完（空数组）时不缓存，留给下一次 speak 重试。
   * @returns {SpeechSynthesisVoice | null}
   */
  function resolveVoice() {
    if (cachedVoice) return cachedVoice
    const voices = globalThis.speechSynthesis.getVoices?.() ?? []
    if (voices.length === 0) return null
    cachedVoice = pickSweetVoice(voices)
    return cachedVoice
  }

  function clearFallback() {
    if (fallbackTimer) {
      clearTimeoutFn(fallbackTimer)
      fallbackTimer = 0
    }
    if (armTimer) {
      clearTimeoutFn(armTimer)
      armTimer = 0
    }
  }

  /**
   * onstart 后武装一次检查：若 FALLBACK_ARM_MS 内没见过 boundary，
   * 启动按 cps 估算推进 charIndex 的兜底循环，直到 onend/onerror 清理。
   */
  function handleStart() {
    startedAt = now()
    armTimer = setTimeoutFn(() => {
      armTimer = 0
      if (disposed || !utterance || boundarySeen || fallbackTimer) return
      fallbackTimer = setTimeoutFn(function tick() {
        if (disposed || !utterance || boundarySeen) return
        const elapsed = (now() - startedAt) / 1000
        const estimated = Math.floor(elapsed * FALLBACK_CPS)
        if (estimated > fallbackIndex) {
          fallbackIndex = estimated
          onBoundary(estimated)
        }
        fallbackTimer = setTimeoutFn(tick, FALLBACK_TICK_MS)
      }, FALLBACK_TICK_MS)
    }, FALLBACK_ARM_MS)
  }

  /**
   * 播报一段文本。返回 false 表示当前环境不支持（调用方降级为纯文字口型）。
   *
   * 音色：默认挑一个甜妹少女音（pickSweetVoice）。getVoices 在部分环境首次调用
   * 返回空数组（音色表异步加载），此时不缓存结果，下一次 speak 再试，
   * 否则会永久锁死在系统默认（通常是男声）。
   *
   * @param {string} text
   * @param {{ lang?: string, rate?: number, pitch?: number }} [options]
   */
  function speak(text, { lang = 'zh-CN', rate = 1.06, pitch = 1.2 } = {}) {
    if (disposed || !isSpeechSynthesisAvailable()) return false
    stop()
    const spoken = String(text ?? '').trim()
    if (!spoken) return false

    utterance = new globalThis.SpeechSynthesisUtterance(spoken)
    utterance.lang = lang
    utterance.rate = Math.min(3, Math.max(0.5, rate))
    // 音高上抬是「少女感」的主要来源；上限 2 是 Web Speech 的规范上限。
    // 1.2 与后端 Edge 甜度档位（pitch +18Hz ≈ 两个半音）同一取向，
    // 浏览器合成器更"脆"，所以不再往 1.3 以上加，避免电子味；
    // 语速 1.06 只为"轻快"，再快会显得催促。
    utterance.pitch = Math.min(2, Math.max(0, pitch))
    const voice = resolveVoice()
    if (voice) utterance.voice = voice
    boundarySeen = false
    fallbackIndex = 0

    utterance.onstart = () => handleStart()
    utterance.onboundary = (event) => {
      boundarySeen = true
      clearFallback()
      if (typeof event?.charIndex === 'number') onBoundary(event.charIndex)
    }
    utterance.onend = () => {
      cleanup()
      onEnd()
    }
    utterance.onerror = (event) => {
      cleanup()
      onError(event?.error ?? 'speech-error')
    }
    globalThis.speechSynthesis.speak(utterance)
    return true
  }

  function cleanup() {
    utterance = null
    clearFallback()
    boundarySeen = false
  }

  function stop() {
    if (!isSpeechSynthesisAvailable()) return
    globalThis.speechSynthesis.cancel()
    cleanup()
  }

  function dispose() {
    if (disposed) return
    disposed = true
    stop()
  }

  return { speak, stop, dispose }
}
