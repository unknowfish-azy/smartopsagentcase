import http from '../utils/request'

export const searchWebResearch = payload => http.post('/api/web-research/search', payload, { timeout: 90000 })
export const fetchWebResearchPage = payload => http.post('/api/web-research/fetch', payload, { timeout: 45000 })
export const getWebResearchRuntime = () => http.get('/api/web-research/runtime')
export const listWebResearchTasks = (limit = 12) => http.get('/api/web-research/tasks', { params: { limit } })
export const submitWebResearchCandidate = taskId => http.post(`/api/knowledge/candidates/from-web-research/${taskId}`)
export const compareWebResearchEvidence = payload => http.post('/api/web-research/evidence/compare', payload, { timeout: 15000 })
