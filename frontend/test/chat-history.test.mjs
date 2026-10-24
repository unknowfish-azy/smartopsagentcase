import assert from 'node:assert/strict'
import test from 'node:test'
import { createConversation, restoreHistory, historyStorageKey, groupConversations, conversationPrompt } from '../src/domain/chat/history.js'

test('new conversations have unique identities and empty messages', () => {
  const first = createConversation()
  const second = createConversation()
  assert.notEqual(first.id, second.id)
  assert.equal(first.title, '新对话')
  assert.deepEqual(first.messages, [])
})

test('history restores active conversation and marks interrupted requests', () => {
  const conversation = createConversation()
  conversation.messages.push({ id: 'question', role: 'user', content: '检查 CPU' }, { id: 'pending', role: 'assistant', content: '', pending: true })
  const restored = restoreHistory(JSON.stringify({ version: 1, conversations: [conversation], activeId: conversation.id }))
  assert.equal(restored.activeId, conversation.id)
  assert.equal(restored.conversations[0].messages[1].pending, false)
  assert.equal(restored.conversations[0].messages[1].error, true)
  assert.match(restored.conversations[0].messages[1].content, /中断/)
})

test('invalid storage is rejected without throwing, invalid rows are ignored', () => {
  assert.equal(restoreHistory('{broken').conversations.length, 0)
  assert.equal(restoreHistory(JSON.stringify({ version: 2, conversations: [] })).conversations.length, 0)
  const conversation = createConversation()
  const restored = restoreHistory(JSON.stringify({ version: 1, conversations: [null, {}, conversation, conversation], activeId: 'missing' }))
  assert.equal(restored.conversations.length, 1)
  assert.equal(restored.activeId, conversation.id)
})

test('account keys do not overlap', () => {
  assert.notEqual(historyStorageKey('alice'), historyStorageKey('bob'))
  assert.notEqual(historyStorageKey(''), historyStorageKey('anonymous'))
})

test('history groups by local calendar day and searches titles and messages', () => {
  const now = new Date(2026, 9, 1, 12).getTime()
  const today = { ...createConversation(), title: 'CPU 问题', updatedAt: now }
  const yesterday = { ...createConversation(), title: '巡检', updatedAt: new Date(2026, 8, 30, 12).getTime(), messages: [{ role: 'user', content: '排查 CPU' }] }
  const older = { ...createConversation(), updatedAt: new Date(2026, 7, 1).getTime() }
  assert.deepEqual(groupConversations([older, yesterday, today], '', now).map(group => group.label), ['今天', '昨天', '更早'])
  const filtered = groupConversations([today, yesterday, older], 'cpu', now)
  assert.equal(filtered.flatMap(group => group.items).length, 2)
})

test('follow-up prompt carries only successful messages from the selected conversation', () => {
  assert.equal(conversationPrompt([], '你好'), '你好')
  const prompt = conversationPrompt([
    { role: 'user', content: 'CPU 满了' },
    { role: 'assistant', content: '查看进程' },
    { role: 'assistant', content: 'network failure', error: true },
    { role: 'assistant', content: '', pending: true }
  ], '接下来呢')
  assert.match(prompt, /CPU 满了/)
  assert.match(prompt, /查看进程/)
  assert.match(prompt, /接下来呢/)
  assert.doesNotMatch(prompt, /network failure/)
})
