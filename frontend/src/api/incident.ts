import http from '../utils/request'

/**
 * 工单中心（Incident）后端接口层（backend IncidentController）。
 *
 * 主体身份（actorId / reporterId）由后端从会话上下文取，
 * 前端不传也不伪造——与恢复契约接口的口径一致。
 */

const BASE = '/api/incidents'

export function searchIncidents(params = {}) {
  // 过滤空值，避免把空字符串当成过滤条件发给后端
  const clean = Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== null && value !== undefined && value !== '')
  )
  return http.get(BASE, { params: clean })
}

export function getIncident(id) {
  return http.get(`${BASE}/${encodeURIComponent(id)}`)
}

export function createIncident(payload) {
  return http.post(BASE, payload)
}

export function createIncidentFromAlert(alertId) {
  return http.post(`${BASE}/from-alert/${encodeURIComponent(alertId)}`)
}

export function acknowledgeIncident(id) {
  return http.post(`${BASE}/${encodeURIComponent(id)}/acknowledge`)
}

export function mitigateIncident(id) {
  return http.post(`${BASE}/${encodeURIComponent(id)}/mitigate`)
}

export function resolveIncident(id, resolution) {
  const query = typeof resolution === 'string' && resolution.trim()
    ? `?resolution=${encodeURIComponent(resolution.trim())}`
    : ''
  return http.post(`${BASE}/${encodeURIComponent(id)}/resolve${query}`)
}

export function closeIncident(id, request) {
  return http.post(`${BASE}/${encodeURIComponent(id)}/close`, request)
}

export function reopenIncident(id) {
  return http.post(`${BASE}/${encodeURIComponent(id)}/reopen`)
}

export function assignIncident(id, request) {
  return http.post(`${BASE}/${encodeURIComponent(id)}/assign`, request)
}

export function addIncidentComment(id, request) {
  return http.post(`${BASE}/${encodeURIComponent(id)}/comments`, request)
}

export function listIncidentEvents(id) {
  return http.get(`${BASE}/${encodeURIComponent(id)}/events`)
}

export function listIncidentRelations(id) {
  return http.get(`${BASE}/${encodeURIComponent(id)}/relations`)
}

export function addIncidentRelation(id, request) {
  return http.post(`${BASE}/${encodeURIComponent(id)}/relations`, request)
}

export function removeIncidentRelation(id, relationId) {
  return http.delete(`${BASE}/${encodeURIComponent(id)}/relations/${encodeURIComponent(relationId)}`)
}
