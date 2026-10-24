import request from '../utils/request'

export function getModelAnalytics(month, connectionId = '') {
  return request({ url: '/api/model-analytics', method: 'get', params: { month, ...(connectionId ? { connectionId } : {}) } })
}

export function saveModelTokenBudget(month, tokenLimit) {
  return request({ url: '/api/model-analytics/budget', method: 'put', data: { month, tokenLimit } })
}
