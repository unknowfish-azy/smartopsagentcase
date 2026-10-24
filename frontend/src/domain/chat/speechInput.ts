/**
 * Web Speech API 语音输入封装（渐进增强，不依赖第三方服务）。
 *
 * 仅负责把识别结果追加到输入框文本；不自动发送、不上传音频。
 * 不支持的浏览器返回 supported=false，调用方据此隐藏或禁用入口。
 */

const ERROR_MESSAGES = Object.freeze({
  'not-allowed': '麦克风权限被拒绝，请在浏览器设置中允许访问后重试。',
  'service-not-allowed': '当前浏览器禁用了语音识别服务。',
  'audio-capture': '未检测到可用的麦克风设备。',
  'no-speech': '没有识别到语音，请靠近麦克风后重试。',
  network: '语音识别需要网络连接，请检查网络后重试。',
})

export function speechRecognitionCtor(scope = globalThis) {
  return scope?.SpeechRecognition || scope?.webkitSpeechRecognition || null
}

export function speechErrorMessage(code) {
  if (!code || code === 'aborted') return ''
  return ERROR_MESSAGES[code] || '语音识别失败，请重试。'
}

const UNSUPPORTED = Object.freeze({
  supported: false,
  start: () => false,
  stop: () => {},
  dispose: () => {},
})

/**
 * @param {object} [options]
 * @param {string} [options.lang] 识别语言，默认普通话
 * @param {object} [options.scope] 注入的全局对象（便于测试）
 * @param {() => any} [options.recognitionFactory] 注入识别器工厂（便于测试）
 * @param {(text: string) => void} [options.onTranscript] 每次识别结果（含临时结果）
 * @param {(listening: boolean) => void} [options.onStateChange]
 * @param {(message: string) => void} [options.onError] 空字符串表示可忽略的中断
 */
interface SpeechInputOptions {
  lang?: string
  scope?: any
  recognitionFactory?: (ctor: any) => any
  onTranscript?: (text: string) => void
  onStateChange?: (listening: boolean) => void
  onError?: (message: string) => void
}

export function createSpeechInput({
  lang = 'zh-CN',
  scope = globalThis,
  recognitionFactory,
  onTranscript = () => {},
  onStateChange = () => {},
  onError = () => {},
}: SpeechInputOptions = {}) {
  const Ctor = speechRecognitionCtor(scope)
  if (!recognitionFactory && !Ctor) return UNSUPPORTED

  let recognition
  try {
    recognition = recognitionFactory ? recognitionFactory(Ctor) : new Ctor()
  } catch {
    return UNSUPPORTED
  }
  if (!recognition || typeof recognition.start !== 'function') return UNSUPPORTED

  recognition.lang = lang
  recognition.interimResults = true
  recognition.continuous = false
  recognition.maxAlternatives = 1

  let baseText = ''
  let finalText = ''
  let interimText = ''
  let listening = false
  let disposed = false

  function emitTranscript() {
    onTranscript(`${baseText}${finalText}${interimText}`)
  }

  function setListening(value) {
    if (disposed || listening === value) return
    listening = value
    onStateChange(value)
  }

  recognition.onstart = () => setListening(true)

  recognition.onresult = event => {
    interimText = ''
    for (let index = event.resultIndex || 0; index < event.results.length; index++) {
      const result = event.results[index]
      const transcript = result?.[0]?.transcript || ''
      if (result?.isFinal) finalText += transcript
      else interimText += transcript
    }
    emitTranscript()
  }

  recognition.onerror = event => {
    if (event?.error === 'aborted') return
    setListening(false)
    onError(speechErrorMessage(event?.error))
  }

  recognition.onend = () => {
    if (interimText) {
      finalText += interimText
      interimText = ''
      emitTranscript()
    }
    setListening(false)
  }

  return {
    supported: true,
    start(text = '') {
      if (disposed || listening) return false
      baseText = String(text || '')
      finalText = ''
      interimText = ''
      try {
        recognition.start()
        return true
      } catch {
        onError('语音输入启动失败，请稍后重试。')
        return false
      }
    },
    stop() {
      if (disposed || !listening) return
      try {
        recognition.stop()
      } catch {
        setListening(false)
      }
    },
    dispose() {
      if (disposed) return
      disposed = true
      listening = false
      recognition.onstart = recognition.onresult = recognition.onerror = recognition.onend = null
      try {
        recognition.abort?.()
      } catch {}
    },
  }
}
