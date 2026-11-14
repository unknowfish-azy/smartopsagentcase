/**
 * 口型驱动：把「声音」或「文字」变成 VRM 的五个元音权重（aa / ih / ou / ee / oh）。
 *
 * 两条来源，互不冒充：
 *  - audio：<audio> → MediaElementAudioSourceNode → AnalyserNode，按实时频谱给权重；
 *  - text：没有音频时按字推一条近似时间线，只保证「有起伏、能闭嘴」，
 *    不代表与任何声音同步，UI 必须如实标注。
 *
 * 平滑自己做（默认 90ms 时间常数，60–120ms 内可调）。AnalyserNode 自带的
 * smoothingTimeConstant 只平滑频谱，权重还需要再过渡一层，否则口型会抖。
 *
 * 元音映射参考 pixiv/ChatVRM（MIT）的做法，阈值与系数按本地模型重新标定。
 */

export const VISEMES = Object.freeze(['aa', 'ih', 'ou', 'ee', 'oh'])

const DEFAULT_SMOOTH_MS = 90
const DEFAULT_CPS = 5.5
const CHAR_GAP_MS = 60
const PAUSE_MS = 360
const FFT_SIZE = 1024
const NOISE_FLOOR = 0.012
const AMP_GAIN = 10

const PAUSE_PATTERN = /[，。！？；：、,.!?;:\n]/
const SPACE_PATTERN = /\s/

// 五个元音桶：字符只决定主口型，次口型取桶里隔一个的邻居，避免五路同时满值
const VOWEL_BUCKETS = ['aa', 'oh', 'ih', 'ou', 'ee']
const LATIN_VOWELS = { a: 'aa', o: 'oh', e: 'ee', i: 'ih', u: 'ou', v: 'ou' }

function zeroWeights() {
  return { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 }
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

/** 没有拼音信息时，用确定性的码位散列挑口型：只求有起伏，不求准确 */
function visemeForChar(char) {
  const lower = char.toLowerCase()
  if (lower.length === 1 && LATIN_VOWELS[lower]) return LATIN_VOWELS[lower]
  const code = char.codePointAt(0) ?? 0
  return VOWEL_BUCKETS[code % VOWEL_BUCKETS.length]
}

function neighbourViseme(primary) {
  const index = VOWEL_BUCKETS.indexOf(primary)
  return VOWEL_BUCKETS[(index + 2) % VOWEL_BUCKETS.length]
}

/**
 * @param {{ smoothMs?: number }} [options]
 */
export function createLipSync({ smoothMs = DEFAULT_SMOOTH_MS } = {}) {
  let context = null
  let analyser = null
  let source = null
  let audioElement = null
  let freqData = null
  let timeData = null

  let timeline = null
  let timelineClock = 0
  let weights = zeroWeights()
  let disposed = false

  function detachAudio() {
    try {
      source?.disconnect()
    } catch {
      // 已经断开过就忽略
    }
    try {
      analyser?.disconnect()
    } catch {
      // 同上
    }
    if (context && context.state !== 'closed') context.close().catch(() => {})
    context = null
    analyser = null
    source = null
    audioElement = null
    freqData = null
    timeData = null
  }

  /**
   * 把一个 <audio> 接进分析链。同一个元素只接一次：Chrome 不允许对同一元素
   * 二次 createMediaElementSource，所以只在换元素或 dispose 时断开重建。
   */
  function attachAudio(element) {
    if (disposed || !element) return false
    if (element === audioElement) return Boolean(analyser)
    detachAudio()
    const AudioContextCtor = globalThis.AudioContext || globalThis.webkitAudioContext
    if (!AudioContextCtor) return false
    try {
      context = new AudioContextCtor()
      analyser = context.createAnalyser()
      analyser.fftSize = FFT_SIZE
      analyser.smoothingTimeConstant = 0.55
      source = context.createMediaElementSource(element)
      source.connect(analyser)
      // 必须接回扬声器：MediaElementSource 会把元素原声从默认输出摘走
      analyser.connect(context.destination)
      freqData = new Uint8Array(analyser.frequencyBinCount)
      timeData = new Uint8Array(analyser.fftSize)
      audioElement = element
      return true
    } catch (error) {
      console.warn('[lipSync] 音频接入失败，退回文字近似口型', error)
      detachAudio()
      return false
    }
  }

  /** 自动播放策略要求音频上下文在用户手势里恢复 */
  function resume() {
    if (context?.state === 'suspended') return context.resume().catch(() => {})
    return Promise.resolve()
  }

  /**
   * 按文字排一条近似口型时间线，返回总时长（毫秒）。
   * 标点留停顿、空格留间隙，其余字符按 cps 匀速推进。
   * entry 记录 UTF-16 字符索引，供 speechSynthesis boundary 事件校正时间线。
   */
  function speak(text, { cps = DEFAULT_CPS } = {}) {
    const spoken = String(text ?? '').trim()
    if (!spoken) {
      silence()
      return 0
    }
    const speed = clamp(Number(cps) || DEFAULT_CPS, 2, 12)
    const charMs = 1000 / speed
    const entries = []
    let clock = 0
    let charIndex = 0
    for (const char of spoken) {
      if (SPACE_PATTERN.test(char)) {
        clock += CHAR_GAP_MS
        charIndex += char.length
        continue
      }
      if (PAUSE_PATTERN.test(char)) {
        clock += PAUSE_MS
        charIndex += char.length
        continue
      }
      const primary = visemeForChar(char)
      entries.push({
        start: clock,
        end: clock + charMs,
        primary,
        secondary: neighbourViseme(primary),
        charIndex
      })
      clock += charMs
      charIndex += char.length
    }
    timeline = entries.length ? { entries, duration: clock } : null
    timelineClock = 0
    return clock
  }

  /**
   * speechSynthesis boundary 校正：把时间线跳到第 charIndex 个字符（UTF-16 索引）
   * 所在音段的起点。TTS 实际语速与 cps 时间线有漂移，靠词边界回调周期性对齐。
   * 跳过未发音字符（空格/标点）取其后的第一个音段。
   */
  function seek(charIndex) {
    if (!timeline) return
    const next = timeline.entries.find((entry) => entry.charIndex >= charIndex)
    if (next) {
      timelineClock = next.start
      return
    }
    // 索引已越过最后一个音段：播报收尾，直接清时间线归零
    timeline = null
    timelineClock = 0
  }

  function silence({ immediate = false } = {}) {
    timeline = null
    timelineClock = 0
    if (immediate) weights = zeroWeights()
  }

  function fillTextTarget(target, dt) {
    if (!timeline) return
    timelineClock += dt * 1000
    if (timelineClock >= timeline.duration) {
      timeline = null
      return
    }
    const entry = timeline.entries.find(
      (item) => timelineClock >= item.start && timelineClock < item.end
    )
    if (!entry) return
    target[entry.primary] = 0.85
    target[entry.secondary] = 0.25
  }

  function fillAudioTarget(target) {
    if (!analyser || !audioElement || audioElement.paused) return

    analyser.getByteTimeDomainData(timeData)
    let sum = 0
    for (let i = 0; i < timeData.length; i += 1) {
      const value = (timeData[i] - 128) / 128
      sum += value * value
    }
    const rms = Math.sqrt(sum / timeData.length)
    // 开方把轻声抬起来，否则正常说话的口型只有一条缝
    const amp = Math.sqrt(clamp((rms - NOISE_FLOOR) * AMP_GAIN, 0, 1))
    if (amp < 0.01) return

    analyser.getByteFrequencyData(freqData)
    const binHz = (context?.sampleRate || 44100) / analyser.fftSize
    let low = 0
    let mid = 0
    let high = 0
    for (let i = 1; i < freqData.length; i += 1) {
      const hz = i * binHz
      if (hz >= 3600) break
      const energy = freqData[i] / 255
      if (hz < 400) low += energy
      else if (hz < 1200) mid += energy
      else high += energy
    }
    const total = low + mid + high || 1
    const lowRatio = low / total
    const midRatio = mid / total
    const highRatio = high / total

    // 低频偏开口（aa/ou），中频偏圆唇（oh），高频偏扁唇（ee/ih）
    const raw = {
      aa: amp * (0.35 + 0.65 * lowRatio),
      oh: amp * (0.3 + 0.7 * midRatio) * 0.9,
      ou: amp * (0.25 + 0.75 * lowRatio) * (1 - amp * 0.45),
      ee: amp * highRatio * 1.25,
      ih: amp * (0.35 * midRatio + 0.65 * highRatio)
    }
    let rawSum = 0
    for (const name of VISEMES) rawSum += raw[name]
    // 五路合计超过别太离谱即可：过度归一化会把嘴压在一条缝
    const scale = rawSum > 1.6 ? 1.6 / rawSum : 1
    for (const name of VISEMES) target[name] = Math.min(1, raw[name] * scale)
  }

  /**
   * 逐帧推进，返回平滑后的权重（只读，不要在外部改写）。
   * @param {number} dt 秒
   */
  function update(dt) {
    const target = zeroWeights()
    if (analyser && audioElement && !audioElement.paused) fillAudioTarget(target)
    else fillTextTarget(target, dt)

    const tau = smoothMs / 1000
    const k = dt > 0 ? 1 - Math.exp(-dt / tau) : 1
    for (const name of VISEMES) {
      const next = weights[name] + (target[name] - weights[name]) * k
      weights[name] = next < 0.001 ? 0 : next
    }
    return weights
  }

  function isActive() {
    return {
      audio: Boolean(analyser && audioElement && !audioElement.paused),
      text: Boolean(timeline)
    }
  }

  function dispose() {
    if (disposed) return
    disposed = true
    timeline = null
    weights = zeroWeights()
    detachAudio()
  }

  return { attachAudio, detachAudio, resume, speak, seek, silence, update, isActive, dispose }
}
