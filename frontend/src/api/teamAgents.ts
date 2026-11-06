import request from '../utils/request.ts'

const value = promise => promise.then(response => response.data)
const base = teamId => `/api/teams/${encodeURIComponent(teamId)}/agents`
const agent = (teamId, agentId) => `${base(teamId)}/${encodeURIComponent(agentId)}`

export const teamAgentsApi = {
  list: teamId => value(request.get(base(teamId))),
  catalog: teamId => value(request.get(`${base(teamId)}/catalog`)),
  detail: (teamId, agentId) => value(request.get(agent(teamId, agentId))),
  create: (teamId, input) => value(request.post(base(teamId), input)),
  saveDraft: (teamId, agentId, input) => value(request.put(`${agent(teamId, agentId)}/draft`, input)),
  publish: (teamId, agentId) => value(request.post(`${agent(teamId, agentId)}/publish`))
}

export const teamConversationApi = {
  list: teamId => value(request.get('/api/assistant/conversations', { params: { teamId } })),
  create: (teamId, title) => value(request.post('/api/assistant/conversations', { id: crypto.randomUUID(), title, teamId })),
  detail: id => value(request.get(`/api/assistant/conversations/${encodeURIComponent(id)}`)),
  append: (id, text) => value(request.post(`/api/assistant/conversations/${encodeURIComponent(id)}/messages`, {
    requestId: crypto.randomUUID(), text, attachmentIds: []
  }))
}

export const teamToolsApi = {
  list: (teamId, agentId) => value(request.get(`${agent(teamId, agentId)}/tools`))
}

export const teamRunsApi = {
  list: teamId => value(request.get(`/api/teams/${encodeURIComponent(teamId)}/runs`)),
  pendingApprovals: teamId => value(request.get(`/api/teams/${encodeURIComponent(teamId)}/approvals`)),
  detail: runId => value(request.get(`/api/team-agent-runs/${encodeURIComponent(runId)}`)),
  create: (teamId, agentId, input) => value(request.post(`${agent(teamId, agentId)}/runs`, input)),
  preview: runId => value(request.post(`/api/team-agent-runs/${encodeURIComponent(runId)}/preview`)),
  // 决策依据可选；服务端只在提供时写入审计，且要求审批人先完成预览。
  approve: (runId, decisionBasis) => value(request.post(`/api/team-agent-runs/${encodeURIComponent(runId)}/approve`, decisionBasis ? { decisionBasis } : {})),
  // SEC-05：执行必须携带审批签发的 grantToken；缺失时服务端返回 409 TEAM_RUN_GRANT_TOKEN_REQUIRED。
  execute: (runId, grantToken) => value(request.post(`/api/team-agent-runs/${encodeURIComponent(runId)}/execute`, grantToken ? { grantToken } : {})),
  cancel: (runId, reason) => value(request.post(`/api/team-agent-runs/${encodeURIComponent(runId)}/cancel`, reason ? { reason } : {}))
}
