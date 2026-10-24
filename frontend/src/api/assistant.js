import request from '../utils/request.js'

export function getAssistantOptions() {
  return request({ url: '/api/assistant/options', method: 'get' })
}

export function saveAssistantPreference(providerKey) {
  return request({ url: '/api/assistant/preference', method: 'put', data: { providerKey } })
}

export function sendAssistantChat(data) {
  return request({ url: '/api/assistant/chat', method: 'post', data, timeout: 150000 })
}
