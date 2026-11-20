import request from '../utils/request'
import { fetchChatRunToken } from './chatRunToken'

/**
 * Trust Ledger（可信账本）前端客户端。
 *
 * - run 列表 / 详情来自 Java 后端（已按登录用户隔离）；
 * - 一键验链直接调用 ai-service 的审计验真端点，返回哈希链的真实校验结果。
 */

const AI_SERVICE_BASE = import.meta.env.VITE_AI_SERVICE_URL || '/ai'

export interface AgentRunSummary {
  runId: string
  requestId: string | null
  intent: string | null
  risk: string
  status: string
  verificationStatus: string
  goal: string | null
  createdAt: string | null
}

export interface AgentToolCall {
  stepId?: number | string
  toolName: string
  action?: string
  risk?: string
  success?: boolean
  errorCategory?: string | null
  attempts?: number | null
  requiresApproval?: boolean
  duplicate?: boolean
}

export interface AgentRunDetail extends AgentRunSummary {
  brief: Record<string, unknown> | null
  toolCalls: AgentToolCall[] | null
  approvals: Array<Record<string, unknown>> | null
  result: Record<string, unknown> | null
  auditEventIds: string[] | null
  pageContext: Record<string, unknown> | null
}

export interface AuditVerifyResult {
  available: boolean
  ok: boolean
  reason?: string
  total_events?: number
  segments?: number
  first_bad_file?: string | null
  checkedAt?: string
}

export function listAgentRuns(limit = 30) {
  return request.get('/api/agent-ledger/runs', { params: { limit } })
}

export function getAgentRun(runId: string) {
  return request.get(`/api/agent-ledger/runs/${encodeURIComponent(runId)}`)
}

export async function verifyAuditChain(): Promise<AuditVerifyResult> {
  const response = await fetchChatRunToken()
  const issued = (response as any)?.data ?? response
  const runToken = issued?.runToken
  if (!runToken) {
    throw new Error('验链鉴权令牌签发失败，请刷新页面后重试。')
  }
  const res = await fetch(`${AI_SERVICE_BASE}/api/agent/audit/verify`, {
    method: 'GET',
    headers: { 'X-Run-Token': String(runToken) },
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error(`验链请求失败：HTTP ${res.status}`)
  }
  return res.json()
}
