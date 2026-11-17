/**
 * ai-service 流式对话客户端（主进程 Node fetch，P0）。
 *
 * 与 Web 端 `frontend/src/api/stream.ts` 同构：
 * POST {base}/api/chat/stream（SSE：run/thinking/token/guard_truncated/inspection/done/error）。
 * 桌面壳不走 Vite 代理，直连 ai-service，故无 CORS 问题。
 *
 * 鉴权：P0 依赖 ai-service 的 CHAT_ALLOW_ANONYMOUS=true（本地联调模式）；
 * 若返回 401，如实把开启方法提示给用户，绝不伪造回答。
 */

const crypto = require('node:crypto');

let currentAbort = null;

/** 401 专用错误：面板据此展示「开启 CHAT_ALLOW_ANONYMOUS」指引。 */
class AuthError extends Error {
  constructor() {
    super('聊天鉴权失败（401）：桌面壳暂不签发运行令牌，请在 ai-service 本地联调时开启 CHAT_ALLOW_ANONYMOUS=true。');
    this.name = 'AuthError';
  }
}

function isAbort(err) {
  return Boolean(err) && (err.name === 'AbortError' || /aborted/i.test(String(err.message || '')));
}

/**
 * 发起一次流式对话。
 * @param {object} opts
 * @param {string} opts.baseUrl    ai-service 基址，如 http://localhost:8001
 * @param {string} opts.message    用户消息（截屏时为默认提问语）
 * @param {string[]} [opts.imageData] 截屏 dataURL 数组（非空时 ai-service 走视觉模型）
 * @param {string} [opts.conversationId] 面板会话 ID（透传 conversation_id）
 * @param {(evt: {type: string, data: any}) => void} onEvent 事件回调
 */
async function streamChat({ baseUrl, message, imageData = [], conversationId }, onEvent) {
  const requestId = crypto.randomUUID();
  const taskId = conversationId || crypto.randomUUID();
  const body = {
    message,
    use_rag: true,
    top_k: 5,
    metadata: { request_id: requestId, task_id: taskId },
  };
  if (conversationId) body.conversation_id = conversationId;
  if (imageData.length) {
    body.images = imageData.map((_, i) => `screenshot-${i + 1}.png`);
    body.image_data = imageData;
  }

  const controller = new AbortController();
  currentAbort = controller;
  let response;
  try {
    response = await fetch(`${baseUrl.replace(/\/+$/, '')}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': requestId,
        'X-Task-ID': taskId,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    currentAbort = null;
    if (controller.signal.aborted) return;
    throw new Error(`无法连接 AI 服务（${baseUrl}）：${err.message}。请确认 ai-service 已启动。`);
  }

  if (!response.ok) {
    currentAbort = null;
    const text = await response.text().catch(() => '');
    if (response.status === 401) {
      throw new AuthError();
    }
    throw new Error(`AI 服务返回 ${response.status}：${text.slice(0, 200)}`);
  }
  if (!response.body) {
    currentAbort = null;
    throw new Error('AI 服务未返回流式响应体');
  }

  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  try {
    for await (const chunk of response.body) {
      buffer += decoder.decode(chunk, { stream: true });
      let sep;
      while ((sep = /\r?\n\r?\n/.exec(buffer))) {
        const raw = buffer.slice(0, sep.index);
        buffer = buffer.slice(sep.index + sep[0].length);
        const evt = parseSse(raw);
        if (evt) dispatch(evt, onEvent);
        if (evt && evt.type === 'done') return; // 正常结束
      }
    }
    const tail = buffer.trim();
    if (tail) {
      const evt = parseSse(tail);
      if (evt) dispatch(evt, onEvent);
    }
  } finally {
    currentAbort = null;
  }
}

function abortStream() {
  if (currentAbort) {
    currentAbort.abort();
    currentAbort = null;
  }
}

/** 解析单条 SSE 报文（与 frontend/src/api/stream.ts 的 parseSse 行为一致）。 */
function parseSse(raw) {
  let event = 'message';
  const dataLines = [];
  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) };
  } catch {
    return { event: 'error', data: { message: 'AI 流响应 JSON 格式错误' } };
  }
}

/** 归一为面板可渲染的事件类型；成功语义与 stream.ts 的 dispatch 对齐。 */
function dispatch({ event, data }, onEvent) {
  switch (event) {
    case 'thinking':
      onEvent({ type: 'thinking', data });
      break;
    case 'token':
      onEvent({ type: 'token', data: { delta: data?.delta || '' } });
      break;
    case 'inspection':
      onEvent({ type: 'inspection', data });
      break;
    case 'run':
      onEvent({ type: 'run', data });
      break;
    case 'error':
      onEvent({ type: 'error', data: { message: data?.message || 'AI 模型输出中断，请重试' } });
      break;
    case 'done': {
      const runEvent = data?.metadata?.run_event ?? data?.run_event;
      const statuses = [data?.status, runEvent?.status].filter((v) => v != null);
      const ok =
        data?.success !== false &&
        statuses.every((v) => ['succeeded', 'success', 'completed', 'ok'].includes(v));
      if (!ok) {
        onEvent({ type: 'error', data: { message: 'AI 请求未成功完成，请查看状态后重试' } });
      } else {
        onEvent({ type: 'done', data });
      }
      break;
    }
    default:
      break; // guard_truncated 等事件 P0 不展示，仅忽略
  }
}

module.exports = { streamChat, abortStream, isAbort };
