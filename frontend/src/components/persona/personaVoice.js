/**
 * 桌宠语音交互闭环（纯逻辑，不依赖 Vue）：
 *
 *   语音识别（浏览器 SpeechRecognition，zh-CN）
 *     → AI 对话（ai-service 流式接口，聚合为完整回复）
 *     → 播报（petSpeech 的 speechSynthesis，由 PersonaPet 驱动）
 *     → 口型（useLipSync 按 boundary 校正，链路已有）。
 *
 * 拆成两个可独立测试的模块：
 *  - createVoiceInput：封装一次性听写。SpeechRecognition 的实现差异
 *    （webkit 前缀、无 finalResult、onerror 后自动重启）都收在这里；
 *  - askAssistant：签发 run 令牌 → streamChat → 聚合 delta 为完整回复文本。
 *    回复要完整拿一次再播报：口型时间线需要整段文字才能排布。
 */

const LISTEN_TIMEOUT_MS = 8000

export function isVoiceInputAvailable() {
  return typeof globalThis !== 'undefined'
    && Boolean(globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition)
}

/**
 * 一次性语音听写。start() 后听到一句完整话（finalResult）或超时/出错/手动停止即结束。
 * @param {{ lang?: string, timeoutMs?: number, setTimeoutFn?, clearTimeoutFn?, now? }} [options]
 * @returns {{ start: () => Promise<{ text: string, reason?: string }>, stop: () => void }}
 *  start resolve { text } 识别成功；{ text: '', reason } 表示未拿到内容
 *  （no-speech / not-allowed / timeout / aborted-by-user 等均已归一化为 reason 字符串）。
 */
export function createVoiceInput(options = {}) {
  const {
    lang = 'zh-CN',
    timeoutMs = LISTEN_TIMEOUT_MS,
    setTimeoutFn = (fn, ms) => globalThis.setTimeout(fn, ms),
    clearTimeoutFn = (id) => globalThis.clearTimeout(id)
  } = options

  let recognition = null
  let timeoutId = 0
  let resolveCurrent = null

  /** 只 settle 一次：resolveCurrent 置空后，晚到的 onend/onresult 全部忽略 */
  function finish(payload) {
    if (!resolveCurrent) return
    const resolve = resolveCurrent
    resolveCurrent = null
    if (timeoutId) {
      clearTimeoutFn(timeoutId)
      timeoutId = 0
    }
    try {
      recognition?.stop?.()
    } catch {
      // 已停止的实例 stop 会抛错，忽略
    }
    resolve(payload)
  }

  /** 用户主动停止：立即 settle，后续事件全部失效 */
  function stop() {
    finish({ text: '', reason: 'aborted-by-user' })
  }

  function start() {
    const Ctor = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition
    if (!Ctor) return Promise.resolve({ text: '', reason: 'unsupported' })
    return new Promise((resolve) => {
      resolveCurrent = resolve
      recognition = new Ctor()
      recognition.lang = lang
      recognition.interimResults = false
      recognition.maxAlternatives = 1

      timeoutId = setTimeoutFn(() => finish({ text: '', reason: 'timeout' }), timeoutMs)

      recognition.onresult = (event) => {
        const result = event?.results?.[0]?.[0]
        const text = String(result?.transcript ?? '').trim()
        if (text) finish({ text })
        // 空结果不等了：多数实现随后会触发 no-speech error
      }
      recognition.onerror = (event) => {
        finish({ text: '', reason: event?.error ?? 'speech-error' })
      }
      // onend 可能不带结果（用户直接松开/系统打断）；已 settle 则这里为空操作
      recognition.onend = () => {
        finish({ text: '', reason: 'no-result' })
      }
      try {
        recognition.start()
      } catch (error) {
        finish({ text: '', reason: error?.name === 'InvalidStateError' ? 'already-started' : 'start-failed' })
      }
    })
  }

  return { start, stop }
}

/**
 * 向 ai-service 发一段话并聚合完整回复。
 * @param {string} message 用户消息
 * @param {{ streamChat?: typeof import('../../api/stream.ts').default, fetchToken?, signal? }} [deps]
 *   streamChat / fetchToken 可注入 mock 供测试。
 * @returns {Promise<{ ok: boolean, text: string }>}
 */
export async function askAssistant(message, deps = {}) {
  const streamChatFn = deps.streamChat ?? deps.streamChatFn
  const fetchToken = deps.fetchToken ?? (async () => {
    const { default: fetchChatRunToken } = await import('../../api/chatRunToken.ts')
    return fetchChatRunToken()
  })
  const unwrap = (value) => value?.data ?? value

  if (!streamChatFn) {
    // 运行时才 import，避免测试环境解析 .ts 与业务依赖
    const mod = await import('../../api/stream.ts')
    return askAssistantCore(mod.default, message, fetchToken, unwrap, deps.signal)
  }
  return askAssistantCore(streamChatFn, message, fetchToken, unwrap, deps.signal)
}

async function askAssistantCore(streamChatFn, message, fetchToken, unwrap, signal) {
  const prompt = String(message ?? '').trim()
  if (!prompt) return { ok: false, text: '' }
  try {
    const issued = unwrap(await fetchToken())
    if (typeof issued?.runToken !== 'string' || !issued.runToken) {
      return { ok: false, text: '聊天鉴权令牌签发失败，请刷新页面后重试。' }
    }
    let reply = ''
    await streamChatFn(prompt, {
      signal,
      onToken: (delta) => {
        reply += delta || ''
      },
      onDone: (payload) => {
        // done 里可能带一次性完整答案（部分后端不逐 token），二者取长
        const finalText = typeof payload?.answer === 'string' ? payload.answer : ''
        if (finalText.length > reply.length) reply = finalText
      }
    }, { runToken: issued.runToken, correlation: { request_id: crypto.randomUUID(), task_id: crypto.randomUUID() } })
    const text = reply.trim()
    return { ok: Boolean(text), text: text || 'AI 没有返回内容，请稍后再试。' }
  } catch (error) {
    return { ok: false, text: `暂时无法连接 AI 服务：${error?.message ?? '未知错误'}` }
  }
}
