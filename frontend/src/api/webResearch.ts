import http from '../utils/request'

export const searchWebResearch = payload => http.post('/api/web-research/search', payload, { timeout: 90000 })
export const fetchWebResearchPage = payload => http.post('/api/web-research/fetch', payload, { timeout: 45000 })
export const getWebResearchRuntime = () => http.get('/api/web-research/runtime')
export const listWebResearchTasks = (limit = 12) => http.get('/api/web-research/tasks', { params: { limit } })
export const submitWebResearchCandidate = taskId => http.post(`/api/knowledge/candidates/from-web-research/${taskId}`)
export const compareWebResearchEvidence = payload => http.post('/api/web-research/evidence/compare', payload, { timeout: 15000 })
// T33：JS 渲染只读重试（按页显式选择，默认不渲染）与显式登录接续会话（不代填凭据）
export const fetchWebResearchPageJs = payload => http.post('/api/web-research/fetch-js', payload, { timeout: 60000 })
export const getWebRenderSession = () => http.get('/api/web-research/render-session')
export const startWebRenderSession = () => http.post('/api/web-research/render-session/start', {}, { timeout: 30000 })
export const finishWebRenderSession = () => http.post('/api/web-research/render-session/finish', {}, { timeout: 30000 })
export const deleteWebRenderSession = () => http.delete('/api/web-research/render-session')
