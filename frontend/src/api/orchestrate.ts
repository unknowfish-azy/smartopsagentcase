/**
 * 多子智能体编排 SSE 客户端。
 *
 * 开发环境经 Vite 的 /ai 代理转发到 ai-service(:8001)；
 * 生产环境用 VITE_AI_SERVICE_URL 指向网关地址。
 */

const AI_SERVICE_BASE = import.meta.env.VITE_AI_SERVICE_URL || '/ai'

export type OrchestrationEvent = {
  event: string
  trace_id?: string
  payload?: any
  at?: string
}

function parseSse(raw: string): { event: string; data: any } | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return null
  return { event, data: JSON.parse(dataLines.join('\n')) }
}

/**
 * 发起一次编排并持续回调进度事件。
 *
 * @param options.goal 自然语言目标
 * @param options.context 业务上下文（device_key / device_keys / submit 等）
 * @param options.maxConcurrency 同波并发上限
 * @param options.signal 取消信号
 * @param options.onEvent 每收到一条编排事件回调一次
 */
export async function streamOrchestration(
  options: {
    goal: string
    context?: Record<string, any>
    maxConcurrency?: number
    signal?: AbortSignal
  },
  onEvent: (event: OrchestrationEvent) => void,
): Promise<void> {
  const query = new URLSearchParams({ goal: options.goal })
  if (options.context && Object.keys(options.context).length) {
    query.set('context', JSON.stringify(options.context))
  }
  if (options.maxConcurrency) query.set('max_concurrency', String(options.maxConcurrency))

  const response = await fetch(`${AI_SERVICE_BASE}/api/orchestrate/stream?${query.toString()}`, {
    method: 'GET',
    headers: { Accept: 'text/event-stream' },
    credentials: 'omit',
    signal: options.signal,
  })
  if (!response.ok) {
    throw new Error(response.status === 403 ? '本机之外的编排请求需要内部令牌' : `编排服务返回 ${response.status}`)
  }
  if (!response.body) throw new Error('当前环境不支持流式读取')

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let completed = false

  const dispatch = (raw: string) => {
    if (completed) return
    let parsed: { event: string; data: any } | null = null
    try {
      parsed = parseSse(raw)
    } catch {
      return
    }
    if (!parsed || parsed.event === 'open' || parsed.event === 'close') return
    if (parsed.event === 'result' || parsed.event === 'error') completed = true
    onEvent({
      event: parsed.event,
      trace_id: parsed.data?.trace_id,
      payload: parsed.data?.payload ?? parsed.data,
      at: parsed.data?.at,
    })
  }

  const flush = () => {
    let separator: RegExpExecArray | null
    while (!completed && (separator = /\r?\n\r?\n/.exec(buffer))) {
      const raw = buffer.slice(0, separator.index)
      buffer = buffer.slice(separator.index + separator[0].length)
      dispatch(raw)
    }
  }

  try {
    while (!completed) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      flush()
    }
    buffer += decoder.decode()
    flush()
    if (buffer.trim()) dispatch(buffer)
  } finally {
    try {
      await reader.cancel()
    } catch {
      /* 连接已关闭时忽略 */
    }
    reader.releaseLock()
  }
}
