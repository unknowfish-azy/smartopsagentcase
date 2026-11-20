import request from '../utils/request'

/** 单个服务的运行状态（由 scripts/windows/ai-runtime-control.ps1 的 status 输出） */
export interface AiRuntimeServiceState {
  running: boolean
  /** 是否由本平台托管（外部安装的 Ollama 为 false，不会被停止） */
  managed: boolean
  pid: number
  health?: string
  version?: string
  models?: string[]
  modelReady?: boolean
  secretConfigured?: boolean
}

export type AiRuntimeState =
  | 'running' | 'partial' | 'stopped' | 'starting' | 'stopping' | 'error' | 'disabled' | 'unknown'

export interface AiRuntimeStatus {
  controlEnabled: boolean
  /** 当前账号是否有权启停（仅 ADMIN + 本地开启控制时为 true） */
  controllable: boolean
  state: AiRuntimeState
  ollama?: AiRuntimeServiceState
  aiService?: AiRuntimeServiceState
  message?: string
}

export function getAiRuntimeStatus(): any {
  return request({ url: '/api/runtime/ai/status', method: 'get', timeout: 30000 })
}

export function startAiRuntime() {
  return request({ url: '/api/runtime/ai/start', method: 'post', timeout: 30000 })
}

export function stopAiRuntime() {
  return request({ url: '/api/runtime/ai/stop', method: 'post', timeout: 30000 })
}

/** 把聊天链路的原始错误码翻译成可执行的中文提示。 */
export function describeAiError(code: string): string {
  switch (code) {
    case 'CHAT_RUN_TOKEN_NOT_CONFIGURED':
      return 'AI 服务缺少聊天令牌密钥（CHAT_RUN_TOKEN_NOT_CONFIGURED），请重启 AI 服务'
    case 'RUN_TOKEN_REQUIRED':
    case 'RUN_TOKEN_INVALID':
    case 'RUN_TOKEN_EXPIRED':
      return '聊天鉴权令牌已失效，请刷新页面后重试'
    case 'RUN_TOKEN_REPLAYED':
      return '该次请求已被处理过，请重新提问'
    case 'BASELINE_BLOCK':
      return '请求被安全基线拦截'
    default:
      return code
  }
}
