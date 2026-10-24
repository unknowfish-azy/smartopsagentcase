import request from '../utils/request'

export const getInspectorSummary = () => request.get('/api/inspector/summary')
export const getInspectorEvents = (limit = 50) => request.get('/api/inspector/events', { params: { limit } })
export const getInspectorEvent = id => request.get(`/api/inspector/events/${id}`)
export const getInspectorStatistics = () => request.get('/api/inspector/statistics')
export const recordInspection = data => request.post('/api/inspector/check', data)
export const verifyInspection = data => request.post('/api/inspector/verify', data)
export const replanInspection = data => request.post('/api/inspector/replan', data)
