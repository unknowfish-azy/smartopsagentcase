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

export function isSpeechSynthesisAvailable() {
  return typeof globalThis !== 'undefined' && typeof globalThis.speechSynthesis === 'object'
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
   * @param {string} text
   * @param {{ lang?: string, rate?: number, voiceIndex?: number }} [options]
   */
  function speak(text, { lang = 'zh-CN', rate = 1 } = {}) {
    if (disposed || !isSpeechSynthesisAvailable()) return false
    stop()
    const spoken = String(text ?? '').trim()
    if (!spoken) return false

    utterance = new globalThis.SpeechSynthesisUtterance(spoken)
    utterance.lang = lang
    utterance.rate = Math.min(3, Math.max(0.5, rate))
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
