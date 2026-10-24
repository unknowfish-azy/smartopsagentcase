import http from '../utils/request'
export const getArtifactDrafts = () => http.get('/api/knowledge/artifacts')
export const createArtifactDraft = payload => http.post('/api/knowledge/artifacts', payload)
export const submitArtifactDraft = id => http.post(`/api/knowledge/artifacts/${id}/submit-review`)
