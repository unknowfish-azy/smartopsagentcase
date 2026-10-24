export function historyStorageKey(username) {
  return `smartops_chat_history:v1:${username ? `user:${encodeURIComponent(username)}` : 'guest'}`
}

export function createConversation() {
  const now = Date.now()
  return { id: crypto.randomUUID(), title: '新对话', createdAt: now, updatedAt: now, messages: [] }
}

export function restoreHistory(raw) {
  const empty = { conversations: [], activeId: null }
  try {
    const saved = JSON.parse(raw)
    if (saved?.version !== 1 || !Array.isArray(saved.conversations)) return empty
    const seen = new Set()
    const conversations = saved.conversations.flatMap(item => {
      if (!item || typeof item.id !== 'string' || seen.has(item.id) || !Array.isArray(item.messages)) return []
      seen.add(item.id)
      const messages = item.messages.filter(message => message && ['user', 'assistant'].includes(message.role) && typeof message.content === 'string').map(message => ({
        id: crypto.randomUUID(), role: message.role,
        content: message.pending ? '上次回复已中断，请重新发送问题。' : message.content,
        error: Boolean(message.error || message.pending), pending: false, ...replyMetadata(message)
      }))
      return [{ id: item.id, title: String(item.title || '新对话').slice(0, 80),
        createdAt: Number.isFinite(item.createdAt) ? item.createdAt : Date.now(),
        updatedAt: Number.isFinite(item.updatedAt) ? item.updatedAt : Date.now(), messages }]
    })
    return { conversations, activeId: conversations.some(item => item.id === saved.activeId) ? saved.activeId : conversations[0]?.id ?? null }
  } catch { return empty }
}

export function groupConversations(conversations, query = '', now = Date.now()) {
  const today = new Date(now)
  today.setHours(0, 0, 0, 0)
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const week = new Date(today)
  week.setDate(week.getDate() - 7)
  const groups = ['今天', '昨天', '最近 7 天', '更早'].map(label => ({ label, items: [] }))
  const search = query.trim().toLocaleLowerCase()
  for (const conversation of [...conversations].sort((first, second) => second.updatedAt - first.updatedAt)) {
    if (search && ![conversation.title, ...conversation.messages.map(message => message.content)].some(text => text.toLocaleLowerCase().includes(search))) continue
    const index = conversation.updatedAt >= today ? 0 : conversation.updatedAt >= yesterday ? 1 : conversation.updatedAt >= week ? 2 : 3
    groups[index].items.push(conversation)
  }
  return groups.filter(group => group.items.length)
}

export function conversationPrompt(messages, prompt) {
  const context = messages.filter(message => !message.error && !message.pending && message.content).slice(-20)
  if (!context.length) return prompt
  const transcript = context.map(message => `${message.role === 'user' ? '用户' : '助手'}：${message.content}`).join('\n\n').slice(-24000)
  return `以下是当前会话的历史记录，请结合上下文回答最后的问题。\n\n${transcript}\n\n用户：${prompt}`
}

export function replyMetadata(value: any) {
  const metadata: Record<string, any> = {}
  for (const field of ['providerKey', 'providerName', 'model']) {
    if (typeof value?.[field] === 'string') metadata[field] = value[field]
  }
  if (Array.isArray(value?.citations)) {
    metadata.citations = value.citations.filter(item => item && typeof item === 'object').map(item =>
      Object.fromEntries(['id', 'title', 'source', 'snippet'].map(field => [field, typeof item[field] === 'string' ? item[field] : ''])))
  }
  return metadata
}

export function assistantHistory(messages) {
  const exchanges = []
  for (let index = 0; index < messages.length - 1; index++) {
    const question = messages[index]
    const answer = messages[index + 1]
    if (question.role !== 'user' || answer.role !== 'assistant') continue
    if ([question, answer].some(message => message.error || message.pending || typeof message.content !== 'string' || !message.content.trim())) continue
    exchanges.push([question, answer].map(({ role, content }) => ({ role, content: content.slice(0, 4000) })))
  }
  const result = []
  let total = 0
  for (const pair of exchanges.reverse()) {
    const size = pair.reduce((sum, message) => sum + message.content.length, 0)
    if (result.length + 2 > 12 || total + size > 16000) break
    result.unshift(...pair)
    total += size
  }
  return result
}
