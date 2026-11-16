import http from '../utils/request'

/** 聊天反馈：创建即触发 Agent 真独立复核（IGNORE 原答案 + 真实检索），返回三态结论。 */
export function submitChatFeedback(payload: {
  conversationId: string
  messageId: string
  prompt: string
  originalAnswer: string
  issueType: string
  description: string
  expected?: string
}) {
  return http.post('/api/chat-feedback', payload)
}

export function getChatFeedbackByMessage(messageId: string) {
  return http.get('/api/chat-feedback', { params: { messageId } })
}

export function listMyChatFeedback(limit = 20) {
  return http.get('/api/chat-feedback/mine', { params: { limit } })
}

/** 全员只读共享知识：只含审核 promote 后的条目。 */
export function listSharedKnowledge(limit = 50) {
  return http.get('/api/chat-feedback/shared', { params: { limit } })
}

export function retryChatFeedback(id: number) {
  return http.post(`/api/chat-feedback/${id}/retry`)
}
