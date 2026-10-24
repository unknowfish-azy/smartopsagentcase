import http from '../utils/request'
export const getKnowledgeRecommendations = incident => http.post('/api/knowledge/recommendations', incident)
