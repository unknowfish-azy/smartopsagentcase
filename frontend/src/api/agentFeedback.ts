import http from '../utils/request'

/**
 * Agent 偏好反馈（DPO 数据源）。
 * 用户对 AI 回答 / Agent 执行结果点 👍(ADOPTED) / 👎(REJECTED)。
 * 必须带 run_id 或 step_id 之一才能回连轨迹。
 */
export type FeedbackVerdict = 'ADOPTED' | 'REJECTED'

export function submitAgentFeedback(payload: {
  requestId?: string
  runId?: string
  stepId?: string
  verdict: FeedbackVerdict
  reason?: string
  payloadJson?: string
}) {
  return http.post('/api/agent-feedback', payload)
}

export function getAgentFeedbackByRun(runId: string,    limit = 20) {
  return http.get('/api/agent-feedback/by-run', { params: { runId, limit } })
}
