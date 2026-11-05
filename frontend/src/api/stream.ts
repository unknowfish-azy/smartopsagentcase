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
  for (const line of raw.split(/\r?\n/)) {
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
    throw new Error('AI 流响应 JSON 格式错误')
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
 * @param {object} [options]
 * @param {string[]} [options.images] 图像证据文件名（当前阶段仅传文件名参与模拟解析）
 * @param {object} [options.rag] 检索调试参数，全部可选；undefined 字段不会进请求体，
 *   ai-service 侧按 "None = 用默认值" 的约定处理。
 */
export async function streamChat(message: string, {
  signal,
  onThinking,
  onRun,
  onToken,
  onDone,
  onError,
}: {
  signal?: AbortSignal
  onThinking?: (step: any) => void
  onRun?: (event: any) => void
  onToken?: (delta: string) => void
  onDone?: (payload: any) => void
  onError?: (error: any) => void
} = {}, options: {
  correlation?: { request_id?: string; task_id?: string }
  images?: string[]
  rag?: {
    top_k?: number
    version?: string | null
    source?: string | null
    score_threshold?: number | null
    vector_weight?: number | null
    bm25_weight?: number | null
  }
} = {}) {
  const rag = options.rag || {}
  const requestId = options.correlation?.request_id || crypto.randomUUID()
  const taskId = options.correlation?.task_id || crypto.randomUUID()
  const body: Record<string, any> = {
    message,
    use_rag: true,
    top_k: rag.top_k ?? 5,
    metadata: {
      request_id: requestId,
      task_id: taskId,
    },
  }
  if (rag.version) body.version = rag.version
  if (rag.source) body.source = rag.source
  if (rag.score_threshold != null) body.score_threshold = rag.score_threshold
  if (rag.vector_weight != null) body.vector_weight = rag.vector_weight
  if (rag.bm25_weight != null) body.bm25_weight = rag.bm25_weight
  if (options.images?.length) body.images = options.images
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  try {
    const response = await fetch(`${AI_SERVICE_BASE}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': requestId,
        'X-Task-ID': taskId,
      },
      body: JSON.stringify(body),
      signal,
    })

    if (!response.ok) {
      throw new Error(`AI 服务返回 ${response.status}`)
    }
    if (!response.body) {
      throw new Error('当前环境不支持流式读取')
    }

    reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let completed = false

    const dispatch = (raw: string) => {
      const parsed = parseSse(raw)
      if (!parsed || completed) return
      if (parsed.event === 'error') {
        const error: Error & { runEvent?: any } = new Error(parsed.data?.message || 'AI 模型输出中断，请重试')
        error.runEvent = parsed.data?.run_event
        throw error
      }
      if (parsed.event === 'run' && onRun) onRun(parsed.data)
      else if (parsed.event === 'thinking' && onThinking) onThinking(parsed.data)
      else if (parsed.event === 'token' && onToken) onToken(parsed.data?.delta || '')
      else if (parsed.event === 'done') {
        const runEvent = parsed.data?.metadata?.run_event ?? parsed.data?.run_event
        const statuses = [parsed.data?.status, runEvent?.status].filter(value => value != null)
        if (parsed.data?.success === false || statuses.some(value => !['succeeded', 'success', 'completed', 'ok'].includes(value))) {
          const error: Error & { runEvent?: any } = new Error('AI 请求未成功完成，请查看状态后重试')
          error.runEvent = runEvent
          throw error
        }
        completed = true
        if (onDone) onDone(parsed.data)
      }
    }

    const flush = () => {
      let separator: RegExpExecArray | null
      while (!completed && (separator = /\r?\n\r?\n/.exec(buffer))) {
        const raw = buffer.slice(0, separator.index)
        buffer = buffer.slice(separator.index + separator[0].length)
        dispatch(raw)
      }
    }

    while (!completed) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      flush()
    }
    buffer += decoder.decode()
    flush()
    if (!completed && buffer.trim()) dispatch(buffer)
    if (!completed) throw new Error('AI 流响应提前结束，请重试')
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    if (onError) onError(error)
    throw error
  } finally {
    if (reader) {
      try { await reader.cancel() } catch { /* Preserve the original stream outcome. */ }
      reader.releaseLock()
    }
  }
}

export default streamChat
