/**
 * AI Service 流式对话客户端（SSE）。
 *
 * 开发环境：通过 Vite 的 /ai 代理转发到 ai-service(:8001)。
 * 生产环境：设置 VITE_AI_SERVICE_URL 指向 ai-service（或由网关代理的 /ai 前缀）。
 */

const AI_SERVICE_BASE = import.meta.env.VITE_AI_SERVICE_URL || '/ai'

/**
 * 解析单条 SSE 报文。
 * @returns {{ event: string, data: any } | null}
 */
function parseSse(raw: string): { event: string; data: any } | null {
  let event = 'message'
  const dataLines = []
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }
  if (!dataLines.length) return null
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) }
  } catch {
    return { event, data: {} }
  }
}

/**
 * 向 ai-service 发起流式对话。
 *
 * @param {string} message 用户消息
 * @param {object} callbacks
 * @param {AbortSignal} [callbacks.signal]
 * @param {(step: object) => void} [callbacks.onThinking]
 * @param {(delta: string) => void} [callbacks.onToken]
 * @param {(payload: object) => void} [callbacks.onDone]
 * @param {(error: Error) => void} [callbacks.onError]
 */
export async function streamChat(message: string, {
  signal,
  onThinking,
  onToken,
  onDone,
  onError,
}: {
  signal?: AbortSignal
  onThinking?: (step: any) => void
  onToken?: (delta: string) => void
  onDone?: (payload: any) => void
  onError?: (error: any) => void
} = {}) {
  const response = await fetch(`${AI_SERVICE_BASE}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, use_rag: true, top_k: 5 }),
    signal,
  })

  if (!response.ok) {
    throw new Error(`AI 服务返回 ${response.status}`)
  }
  if (!response.body) {
    throw new Error('当前环境不支持流式读取')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  const flush = () => {
    let sep
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const parsed = parseSse(raw)
      if (!parsed) continue
      if (parsed.event === 'thinking' && onThinking) onThinking(parsed.data)
      else if (parsed.event === 'token' && onToken) onToken(parsed.data?.delta || '')
      else if (parsed.event === 'done' && onDone) onDone(parsed.data)
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      flush()
    }
    buffer += decoder.decode()
    flush()
    if (buffer.trim()) {
      const parsed = parseSse(buffer)
      if (parsed?.event === 'done' && onDone) onDone(parsed.data)
    }
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    if (onError) onError(error)
    else throw error
  }
}

export default streamChat
