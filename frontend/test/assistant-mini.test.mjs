import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { shallowRef } from 'vue'
import * as history from '../src/domain/chat/history.ts'

const mini = { key: 'mini', name: '智维 Mini', kind: 'builtin', model: 'qwen3:1.7b', enabled: true, available: true, status: 'ready' }
const external = { key: 'connection:7', name: '我的模型', kind: 'connection', model: 'test', enabled: true, available: true, status: 'configured' }
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }

async function setup({ selectedKey = 'mini', options = [mini, external] } = {}) {
  const values = new Map()
  globalThis.localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
  localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'alice' }))
  const calls = { options: 0, preferences: [], chats: [] }
  const fixture = {
    chatAttachmentsApi: { list: async () => [], detail: async () => { throw new Error('not configured') }, rename: async () => {}, delete: async () => {} },
    currentSession: shallowRef({ id: 1, username: 'alice' }),
    getAssistantOptions: async () => { calls.options++; return { data: { selectedKey, options } } },
    saveAssistantPreference: async providerKey => { calls.preferences.push(providerKey); return { data: { selectedKey: providerKey } } },
    sendAssistantChat: async payload => { calls.chats.push(payload); return { data: { content: '检查日志', providerKey: payload.providerKey, providerName: '智维 Mini', model: 'qwen3:1.7b', citations: [{ id: '1', title: '指南', source: 'knowledge/linux/cpu.md', snippet: '查看负载' }], readOnly: true } } },
    streamChat: async () => { throw new Error('stream not configured') },
    fetchChatRunToken: async () => ({ data: { runToken: 'test-run-token' } }),
    getModelConnections: async () => ({ data: [] }), invokeModelConnection: async () => { throw Error('legacy route') }
  }
  const key = '__assistantTest' + crypto.randomUUID().replaceAll('-', '')
  globalThis[key] = fixture
  let source = await readFile(new URL('../src/stores/aiChat.js', import.meta.url), 'utf8')
  source = source.replace("import { chatAttachmentsApi } from '../api/chatAttachments.ts'", `const chatAttachmentsApi = globalThis.${key}.chatAttachmentsApi`)
  source = source.replace("import { fetchChatRunToken } from '../api/chatRunToken.ts'", `const fetchChatRunToken = (...args) => globalThis.${key}.fetchChatRunToken(...args)`)
  source = source.replace(/import \{([^}]+)\} from '\.\.\/(?:api\/(?:model|assistant|stream)|security\/session)\.(?:js|ts)'/g, (_, names) => names.split(',').map(name => {
    name = name.trim()
    return 'const ' + name + ' = ' + (name === 'currentSession' ? 'globalThis.' + key + '.' + name : '(...args) => globalThis.' + key + '.' + name + '(...args)')
  }).join('\n'))
    .replace("'pinia'", JSON.stringify(import.meta.resolve('pinia')))
    .replace("'vue'", JSON.stringify(import.meta.resolve('vue')))
    .replace("'../domain/chat/history.ts'", JSON.stringify(new URL('../src/domain/chat/history.ts', import.meta.url).href))
  setActivePinia(createPinia())
  const { useAiChatStore } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64') + '#' + key)
  return { store: useAiChatStore(), fixture, calls, values }
}

test('stream failure preserves partial real answer and reports failure', async () => {
  const { store, fixture } = await setup({ options: [mini] })
  fixture.streamChat = async (_message, callbacks) => {
    callbacks.onToken('真实模型已返回的部分')
    callbacks.onError(new Error('输出中断'))
    throw new Error('输出中断')
  }
  assert.equal(await store.sendMessageStreaming('检查服务'), false)
  assert.match(store.messages.at(-1).content, /真实模型已返回的部分/)
  assert.equal(store.messages.at(-1).content.match(/输出中断/g).length, 1)
  assert.equal(store.messages.at(-1).error, true)
  assert.equal(store.messages.at(-1).streaming, false)
})

test('new account without model connections chats with explicit Mini and saves response metadata', async () => {
  const { store, calls } = await setup({ options: [mini] })
  assert.equal(await store.sendMessage('你好'), true)
  assert.deepEqual(calls.chats, [{ providerKey: 'mini', message: '你好', history: [] }])
  assert.equal(store.messages.at(-1).providerName, '智维 Mini')
  assert.equal(store.messages.at(-1).citations[0].source, 'knowledge/linux/cpu.md')
})

test('attachment history does not upload local history or persist remote metadata in browser storage', async () => {
  const { store, fixture, values } = await setup()
  await store.sendMessage('local-only')
  const localId = store.activeId
  const remote = { id: crypto.randomUUID(), title: 'private-file', createdAt: 1, updatedAt: 2, teamId: null }
  fixture.chatAttachmentsApi.list = async () => [remote]
  fixture.chatAttachmentsApi.detail = async () => ({ ...remote, messages: [{ id: 'message', role: 'user', content: '', attachments: [{ id: 'file', name: 'secret.log' }] }] })
  await store.loadRemoteConversations()
  store.selectConversation(remote.id)
  await store.loadRemoteDetail(remote.id)
  store.selectConversation(localId)
  assert.equal(store.messages[0].content, 'local-only')
  assert.ok(!JSON.stringify([...values]).includes('private-file'))
  assert.ok(!JSON.stringify([...values]).includes('secret.log'))
})

test('late attachment history cannot reappear after account switching and failed delete keeps history', async () => {
  const { store, fixture } = await setup()
  const pending = deferred()
  fixture.chatAttachmentsApi.list = () => pending.promise
  const load = store.loadRemoteConversations()
  localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'bob' }))
  fixture.currentSession.value = { id: 2, username: 'bob' }
  pending.resolve([{ id: 'alice-private', title: 'alice', teamId: null }])
  await load
  assert.deepEqual(store.conversations, [])
  fixture.chatAttachmentsApi.list = async () => [{ id: 'bob-private', title: 'bob', teamId: null }]
  await store.loadRemoteConversations()
  fixture.chatAttachmentsApi.delete = async () => { throw new Error('offline') }
  await store.deleteConversation('bob-private')
  assert.equal(store.conversations.length, 1)
  assert.match(store.remoteError, /offline/)
})

test('an older server list cannot resurrect a deleted attachment conversation', async () => {
  const { store, fixture } = await setup()
  const conversation = { id: 'remote-private', title: 'private', teamId: null }
  fixture.chatAttachmentsApi.list = async () => [conversation]
  await store.loadRemoteConversations()
  const stale = deferred()
  fixture.chatAttachmentsApi.list = () => stale.promise
  const loading = store.loadRemoteConversations()
  await store.deleteConversation(conversation.id)
  stale.resolve([conversation])
  await loading
  assert.deepEqual(store.conversations, [])
})

test('options default to Mini, restore preference and preserve deleted or disabled selection', async () => {
  const { store, calls, fixture } = await setup()
  await store.loadOptions()
  assert.equal(store.selectedKey, 'mini')
  assert.equal(await store.selectProvider(external.key), true)
  assert.deepEqual(calls.preferences, [external.key])
  fixture.getAssistantOptions = async () => ({ data: { selectedKey: 'connection:deleted', options: [mini] } })
  await store.loadOptions(true)
  assert.equal(store.selectedKey, 'connection:deleted')
  assert.equal(store.selectedOption.available, false)
  assert.equal(store.canSend, false)
  assert.equal(await store.sendMessage('不能偷偷降级'), false)
  assert.equal(calls.chats.length, 0)
  fixture.getAssistantOptions = async () => ({ data: { selectedKey: external.key, options: [mini, { ...external, enabled: false, available: false, status: 'disabled' }] } })
  await store.loadOptions(true)
  assert.equal(store.selectedKey, external.key)
  assert.equal(await store.selectProvider(external.key), false)
})

test('external failures never call Mini; explicit fallback persists without resending', async () => {
  const { store, fixture, calls } = await setup({ selectedKey: external.key })
  fixture.sendAssistantChat = async payload => { calls.chats.push(payload); throw Error('外部失败') }
  assert.equal(await store.sendMessage('敏感问题'), false)
  assert.equal(store.canSwitchToMini, true)
  assert.equal(await store.selectProvider('mini'), true)
  assert.equal(store.selectedKey, 'mini')
  assert.equal(calls.chats.length, 1)
  assert.equal(calls.chats[0].providerKey, external.key)
  assert.deepEqual(calls.preferences, ['mini'])
})

test('options and preference failures never silently choose another provider', async () => {
  const { store, fixture, calls } = await setup()
  fixture.getAssistantOptions = async () => { throw Error('选项失败') }
  assert.equal(await store.loadOptions(), false)
  assert.match(store.optionsError, /选项失败/)
  assert.equal(await store.sendMessage('不能发送'), false)
  assert.equal(calls.chats.length, 0)
  fixture.getAssistantOptions = async () => ({ data: { selectedKey: external.key, options: [mini, external] } })
  await store.loadOptions(true)
  fixture.saveAssistantPreference = async () => { throw Error('保存失败') }
  assert.equal(await store.selectProvider('mini'), false)
  assert.equal(store.selectedKey, external.key)
  assert.match(store.preferenceError, /保存失败/)
})

test('message length is enforced without sending or adding failed history', async () => {
  const { store, calls } = await setup()
  assert.equal(await store.sendMessage('文'.repeat(2001)), false)
  assert.equal(await store.sendMessage('   '), false)
  assert.equal(store.messages.length, 0)
  assert.equal(calls.chats.length, 0)
  assert.equal(await store.sendMessage('文'.repeat(2000)), true)
})

test('only successful exchanges in the active conversation enter structured history', async () => {
  const { store, fixture, calls } = await setup()
  await store.sendMessage('成功问题')
  const firstId = store.activeId
  const reply = fixture.sendAssistantChat
  fixture.sendAssistantChat = async () => { throw Error('失败') }
  await store.sendMessage('失败问题')
  fixture.sendAssistantChat = reply
  await store.sendMessage('追问')
  assert.deepEqual(calls.chats.at(-1).history, [{ role: 'user', content: '成功问题' }, { role: 'assistant', content: '检查日志' }])
  store.newConversation()
  await store.sendMessage('另一个会话')
  assert.deepEqual(calls.chats.at(-1).history, [])
  store.selectConversation(firstId)
  await store.sendMessage('回来')
  assert.ok(!JSON.stringify(calls.chats.at(-1).history).includes('另一个会话'))
})

for (const operation of ['options', 'preference', 'chat']) {
  test('session switch clears state and discards late ' + operation + ' response', async () => {
    const { store, fixture, values } = await setup()
    await store.loadOptions()
    const held = deferred()
    let pending
    if (operation === 'options') {
      fixture.getAssistantOptions = () => held.promise
      pending = store.loadOptions(true)
    } else if (operation === 'preference') {
      fixture.saveAssistantPreference = () => held.promise
      pending = store.selectProvider(external.key)
    } else {
      fixture.sendAssistantChat = () => held.promise
      pending = store.sendMessage('alice 私密')
      await Promise.resolve()
    }
    fixture.currentSession.value = { id: 2, username: 'bob' }
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'bob' }))
    store.syncAccount()
    assert.deepEqual(store.options, [])
    assert.equal(store.selectedKey, 'mini')
    assert.equal(store.messages.length, 0)
    held.resolve({ data: { selectedKey: external.key, options: [external], content: 'alice 回复' } })
    assert.equal(await pending, false)
    assert.deepEqual(store.options, [])
    assert.equal(store.messages.length, 0)
    assert.equal(store.selectedKey, 'mini')
    assert.ok(!String(values.get(history.historyStorageKey('bob'))).includes('alice'))
    fixture.currentSession.value = { id: 1, username: 'alice' }
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'alice' }))
    store.syncAccount()
    if (operation === 'chat') assert.equal(store.messages[0].content, 'alice 私密')
    store.$dispose()
  })
}

test('history bounds count, per-message and total size, rejecting failed/pending pairs and non-chat roles', () => {
  assert.equal(typeof history.assistantHistory, 'function')
  const messages = Array.from({ length: 16 }, (_, index) => [
    { role: 'user', content: '问题' + index + '文'.repeat(4100) },
    { role: 'assistant', content: '回复' + index + '文'.repeat(4100) }
  ]).flat()
  messages.push({ role: 'user', content: '失败问题' }, { role: 'assistant', content: '失败', error: true }, { role: 'system', content: '不能发送' })
  const result = history.assistantHistory(messages)
  assert.ok(result.length <= 12)
  assert.ok(result.every(item => item.content.length <= 4000))
  assert.ok(result.reduce((sum, item) => sum + item.content.length, 0) <= 16000)
  assert.ok(!JSON.stringify(result).includes('失败'))
  assert.equal(result.at(-1).content.startsWith('回复15'), true)
})

test('legacy history and optional provider/citation metadata survive restoration as text', () => {
  const conversation = history.createConversation()
  conversation.messages = [{ role: 'user', content: '旧问题' }, { role: 'assistant', content: '回复', providerName: '智维 Mini', model: 'qwen3:1.7b', citations: [{ id: '1', title: '<img src=x onerror=alert(1)>', source: 'javascript:alert(1)', snippet: '<script>bad()</script>' }] }]
  const restored = history.restoreHistory(JSON.stringify({ version: 1, conversations: [conversation], activeId: conversation.id })).conversations[0].messages
  assert.equal(restored[0].content, '旧问题')
  assert.equal(restored[1].providerName, '智维 Mini')
  assert.equal(restored[1].model, 'qwen3:1.7b')
  assert.equal(restored[1].citations[0].title, '<img src=x onerror=alert(1)>')
})

test('assistant API uses unified endpoints, explicit payload and 150 second timeout', async () => {
  const source = await readFile(new URL('../src/api/assistant.ts', import.meta.url), 'utf8')
  const calls = []
  globalThis.__assistantRequest = config => { calls.push(config); return Promise.resolve({ data: {} }) }
  const module = await import('data:text/javascript;base64,' + Buffer.from(source.replace(/import request from ['"][^'"]+['"]/, 'const request = globalThis.__assistantRequest')).toString('base64'))
  await module.getAssistantOptions()
  await module.saveAssistantPreference('mini')
  await module.sendAssistantChat({ providerKey: 'mini', message: '你好', history: [] })
  assert.deepEqual(calls.map(call => [call.method, call.url]), [['get', '/api/assistant/options'], ['put', '/api/assistant/preference'], ['post', '/api/assistant/chat']])
  assert.deepEqual(calls[1].data, { providerKey: 'mini' })
  assert.equal(calls[2].timeout, 150000)
})

test('streaming sends image evidence names and records vision thinking steps', async () => {
  const { store, fixture } = await setup()
  const stream = {}
  fixture.streamChat = async (message, callbacks, options) => {
    stream.message = message
    stream.images = options?.images
    callbacks.onThinking({ stage: 'vision', label: '图像证据解析', detail: `解析 ${options.images.length} 张图像证据` })
    callbacks.onToken('分析')
    callbacks.onToken('完成')
    callbacks.onDone({ provider: 'mock', model: 'qwen3:1.7b', trust_score: 0.5, citations: [], evidence: [], metadata: { images: options?.images || [] } })
  }
  assert.equal(await store.sendMessageStreaming('分析这张图', { images: ['screen-a.png', ' screen-b.png ', ''] }), true)
  assert.equal(stream.message, '分析这张图')
  assert.deepEqual(stream.images, ['screen-a.png', 'screen-b.png'])
  const [user, assistant] = store.messages
  assert.deepEqual(user.images, ['screen-a.png', 'screen-b.png'])
  assert.equal(assistant.thinking[0].stage, 'vision')
  assert.equal(assistant.content, '分析完成')
  assert.equal(assistant.streaming, false)
  assert.deepEqual(assistant.metadata.images, ['screen-a.png', 'screen-b.png'])
  assert.equal(await store.sendMessageStreaming('再来一次', { images: ['1.png', '2.png', '3.png', '4.png', '5.png', '6.png', '7.png'] }), true)
  assert.deepEqual(stream.images, ['1.png', '2.png', '3.png', '4.png', '5.png'])
})
