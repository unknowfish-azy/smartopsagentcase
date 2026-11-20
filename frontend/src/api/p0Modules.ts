import http from '../utils/request'

/** P0-2 情景记忆审核 */
export function listMemoryCandidates() : any {
  return http.get('/api/memory/operator/candidates')
}

export function approveMemory(id: number) {
  return http.post(`/api/memory/operator/${id}/approve`)
}

export function rejectMemory(id: number,    reason?: string) {
  return http.post(`/api/memory/operator/${id}/reject`, { reason })
}

export function recallMemory(query: string,    limit = 5) {
  return http.get('/api/memory/operator/recall', { params: { query, limit } })
}

/** P0-3 风险门 */
export function assessRisk(command: string,    toolId?: string,    context?: Record<string,    string>) {
  return http.post('/api/risk/assess', { command, toolId, context })
}

export function assessRiskBatch(commands: string[],    toolId?: string,    context?: Record<string,    string>) {
  return http.post('/api/risk/assess-batch', { commands, toolId, context })
}

export function listRiskHistory(limit = 50) : any {
  return http.get('/api/risk/history', { params: { limit } })
}

/** P0-1 统一检索 */
export function unifiedSearch(query: string,    collections?: string[],    limit = 10) {
  return http.get('/api/retrieval/search', {
    params: { query, collections, limit },
    paramsSerializer: { indexes: null }
  })
}
