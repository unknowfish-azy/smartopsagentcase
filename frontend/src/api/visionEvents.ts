import http from '../utils/request'

export const createVisionEvent = (conversationId, attachmentId, sourceType = 'FILE') => http.post(`/api/assistant/conversations/${conversationId}/vision-events/from-attachment/${attachmentId}`, null, { params: { sourceType } })
export const listVisionEvents = conversationId => http.get(`/api/assistant/conversations/${conversationId}/vision-events`)
export const getVisionEvent = (conversationId, eventId) => http.get(`/api/assistant/conversations/${conversationId}/vision-events/${eventId}`)
export const recordVisionOcr = (conversationId, eventId, payload) => http.post(`/api/assistant/conversations/${conversationId}/vision-events/${eventId}/ocr`, payload)
export const confirmVisionEvent = (conversationId, eventId) => http.post(`/api/assistant/conversations/${conversationId}/vision-events/${eventId}/confirm`)
export const handoffVisionToKnowledge = (conversationId, eventId, payload) => http.post(`/api/assistant/conversations/${conversationId}/vision-events/${eventId}/handoff/personal-knowledge`, payload)
export const handoffVisionToMemory = (conversationId, eventId, payload) => http.post(`/api/assistant/conversations/${conversationId}/vision-events/${eventId}/handoff/memory`, payload)
