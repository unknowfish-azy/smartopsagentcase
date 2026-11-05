import http from '../utils/request'

export function getDecisionLoops(limit = 30) {
    return http.get('/api/agent/loops', { params: { limit } })
}

export function getDecisionLoop(id) {
    return http.get(`/api/agent/loops/${id}`)
}

export function getDecisionLoopStats() {
    return http.get('/api/agent/loops/stats')
}

export function createDecisionLoop(data) {
    return http.post('/api/agent/loops', data)
}

export function recallDecisionMemories(id) {
    return http.post(`/api/agent/loops/${id}/recall`)
}

export function decideDecisionLoop(id, data) {
    return http.post(`/api/agent/loops/${id}/decide`, data)
}

export function reviewDecisionLoop(id, data) {
    return http.post(`/api/agent/loops/${id}/review`, data)
}
