import http from '../utils/request'
export { splitPane, orderOperationSessions, canConnect, capabilityLabel } from './operationsState.ts'

export function getOperationCapabilities() {
  return http.get('/api/operations/capabilities')
}

export function getOperationSessions() {
  return http.get('/api/operations/sessions')
}

export function listRemoteFiles(runtimeId, path) {
  return http.get(`/api/operations/runtimes/${runtimeId}/files`, { params: { path } })
}
export function downloadRemoteFile(runtimeId, path) {
  return http.get(`/api/operations/runtimes/${runtimeId}/files/content`, { params: { path }, responseType: 'blob' })
}
export function uploadRemoteFile(runtimeId, path, file, onUploadProgress) {
  const form = new FormData(); form.append('file', file)
  return http.post(`/api/operations/runtimes/${runtimeId}/files/content`, form, {
    params: { path }, headers: { 'Content-Type': 'multipart/form-data' }, onUploadProgress
  })
}

export function getOperationAgentContext(runtimeId) {
  return http.get(`/api/operations/runtimes/${runtimeId}/agent-context`)
}

export function createOperationSession(payload) {
  return http.post('/api/operations/sessions', payload)
}

export function deleteOperationSession(id) {
  return http.delete(`/api/operations/sessions/${id}`)
}

export function connectOperationSession(id, decision = 'NONE') {
  return http.post(`/api/operations/sessions/${id}/connect`, null, { params: { decision } })
}

export function closeOperationRuntime(runtimeId) {
  return http.delete(`/api/operations/runtimes/${runtimeId}`)
}

export function previewMultiExec(payload) {
  return http.post('/api/operations/multi-exec/preview', payload)
}

export function executeMultiExec(payload) {
  return http.post('/api/operations/multi-exec/execute', payload)
}

export function previewOperationTool(payload) {
  return http.post('/api/operations/tools/preview', payload)
}

export function getOperationTools() {
  return http.get('/api/operations/tools')
}

export function executeOperationTool(runtimeId, toolId, parameters = {}) {
  return http.post(`/api/operations/runtimes/${runtimeId}/tools/${toolId}/execute`, { parameters })
}

export function getOperationRuns(params = {}) {
  return http.get('/api/operations/runs', { params })
}

export function getOperationRun(id) {
  return http.get(`/api/operations/runs/${id}`)
}

export function createKnowledgeCandidateFromRun(runId) {
  return http.post(`/api/knowledge/candidates/from-operation-run/${runId}`)
}

export function getKnowledgeCandidates(params = {}) {
  return http.get('/api/knowledge/candidates', { params })
}

export function getKnowledgeCandidate(id) {
  return http.get(`/api/knowledge/candidates/${id}`)
}

export function promoteKnowledgeCandidate(id, payload) {
  return http.post(`/api/knowledge/candidates/${id}/promote`, payload)
}

export function rejectKnowledgeCandidate(id, reason) {
  return http.post(`/api/knowledge/candidates/${id}/reject`, { reason })
}

export function startOperationTunnel(runtimeId, payload) {
  return http.post(`/api/operations/runtimes/${runtimeId}/tunnels`, null, { params: payload })
}

export function stopOperationTunnel(runtimeId, tunnelId) {
  return http.delete(`/api/operations/runtimes/${runtimeId}/tunnels/${tunnelId}`)
}
