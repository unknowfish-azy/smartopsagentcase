import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { getAssistantOptions, saveAssistantPreference, sendAssistantChat } from '../api/assistant.ts'
import { streamChat } from '../api/stream.ts'
import { currentSession } from '../security/session.js'
import { chatAttachmentsApi } from '../api/chatAttachments.ts'
import { assistantHistory, createConversation, historyStorageKey, replyMetadata, restoreHistory } from '../domain/chat/history.ts'

function unwrap(value) {
  return value?.data ?? value
}

export const useAiChatStore = defineStore('ai-chat', () => {
  const conversations = ref([])
  const activeId = ref(null)
  const storageWarning = ref('')
  const options = ref([])
  const selectedKey = ref('mini')
  const optionsLoaded = ref(false)
  const optionsLoading = ref(false)
  const optionsError = ref('')
  const preferenceSaving = ref(false)
  const preferenceError = ref('')
  const preferenceNotice = ref('')
  const validationError = ref('')
  const accountEpoch = ref(0)
  const remoteError = ref('')
  const remoteLoading = ref(false)
  let attachmentLeaveGuard = () => true
  let remoteRevision = 0
  let remoteDetailSequence = 0
  const activeConversation = computed(() => conversations.value.find(item => item.id === activeId.value))
  const messages = computed(() => activeConversation.value?.messages ?? [])
  const sending = computed(() => messages.value.some(message => message.pending))
  const errorMessage = computed(() => validationError.value || (messages.value.at(-1)?.error ? messages.value.at(-1).content : ''))
  const selectedOption = computed(() => options.value.find(option => option.key === selectedKey.value) ?? {
    key: selectedKey.value, name: selectedKey.value === 'mini' ? '智维 Mini' : '已保存的连接（已失效）',
    kind: selectedKey.value === 'mini' ? 'builtin' : 'connection', enabled: false, available: false,
    status: 'unavailable', detail: '已保存的选项不可用，请显式选择其他助手；不会自动切换。'
  })
  const canSend = computed(() => optionsLoaded.value && !optionsLoading.value && !optionsError.value && !preferenceSaving.value && selectedOption.value.enabled && selectedOption.value.available)
  const canSwitchToMini = computed(() => Boolean(messages.value.at(-1)?.error && messages.value.at(-1)?.providerKey?.startsWith('connection:') && selectedKey.value !== 'mini'))
  let storageKey = null
  let accountIdentity = null
  let optionsPromise = null

  function syncAccount() {
    const user = currentSession.value
    let previewUsername = ''
    try { previewUsername = JSON.parse(localStorage.getItem('smartops_preview_auth') || '{}')?.username || '' } catch {}
    const username = previewUsername || user?.username || ''
    const identity = JSON.stringify([user?.id, username, user?.mustChangePassword])
    if (identity === accountIdentity) return
    accountIdentity = identity
    accountEpoch.value++
    remoteRevision++
    remoteDetailSequence++
    remoteError.value = ''
    remoteLoading.value = false
    storageKey = historyStorageKey(username)
    options.value = []
    selectedKey.value = 'mini'
    optionsLoaded.value = false
    optionsLoading.value = false
    optionsError.value = ''
    preferenceSaving.value = false
    preferenceError.value = ''
    preferenceNotice.value = ''
    validationError.value = ''
    optionsPromise = null
    storageWarning.value = ''
    let restored = { conversations: [], activeId: null }
    try { restored = restoreHistory(localStorage.getItem(storageKey)) } catch {
      storageWarning.value = '浏览器存储不可用，本次对话仅临时保留。'
    }
    conversations.value = restored.conversations
    activeId.value = restored.activeId
  }

  function sameAccount(generation) {
    syncAccount()
    return generation === accountEpoch.value
  }

  async function loadOptions(force = false) {
    syncAccount()
    if (!currentSession.value || currentSession.value.mustChangePassword || preferenceSaving.value) return false
    if (optionsPromise) return optionsPromise
    if (optionsLoaded.value && !force) return !optionsError.value
    const generation = accountEpoch.value
    optionsLoading.value = true
    optionsError.value = ''
    optionsPromise = (async () => {
      try {
        const data = unwrap(await getAssistantOptions())
        if (!sameAccount(generation)) return false
        if (!Array.isArray(data?.options) || typeof data.selectedKey !== 'string' || !data.selectedKey) throw new Error('助手选项响应无效，请重试。')
        options.value = data.options
        selectedKey.value = data.selectedKey
        optionsLoaded.value = true
        return true
      } catch (error) {
        if (sameAccount(generation)) {
          optionsLoaded.value = false
          optionsError.value = error?.message || '助手选项加载失败，请重试。'
        }
        return false
      } finally {
        if (sameAccount(generation)) {
          optionsLoading.value = false
          optionsPromise = null
        }
      }
    })()
    return optionsPromise
  }

  async function selectProvider(providerKey) {
    syncAccount()
    if (!optionsLoaded.value || optionsLoading.value || preferenceSaving.value) return false
    const option = options.value.find(item => item.key === providerKey)
    if (!option?.enabled) return false
    const generation = accountEpoch.value
    preferenceSaving.value = true
    preferenceError.value = ''
    preferenceNotice.value = ''
    try {
      const data = unwrap(await saveAssistantPreference(providerKey))
      if (!sameAccount(generation)) return false
      if (data?.selectedKey !== providerKey) throw new Error('偏好保存结果不一致，请刷新选项后重试。')
      selectedKey.value = data.selectedKey
      preferenceNotice.value = '偏好已保存；不会自动重发，请再次发送问题。'
      validationError.value = ''
      return true
    } catch (error) {
      if (sameAccount(generation)) preferenceError.value = error?.message || '偏好保存失败，仍保留原选择。'
      return false
    } finally {
      if (sameAccount(generation)) preferenceSaving.value = false
    }
  }

  function persist() {
    try {
      localStorage.setItem(storageKey, JSON.stringify({ version: 1, conversations: conversations.value.filter(item => !item.remote), activeId: activeId.value }))
      storageWarning.value = ''
    } catch {
      storageWarning.value = '历史记录保存失败，可能是浏览器存储已满或被禁用；刷新可能丢失本次更改。'
    }
  }

  function newConversation() {
    syncAccount()
    if (!attachmentLeaveGuard()) return activeId.value
    const empty = conversations.value.find(item => !item.remote && item.messages.length === 0)
    if (empty) activeId.value = empty.id
    else {
      const conversation = createConversation()
      conversations.value.unshift(conversation)
      activeId.value = conversation.id
    }
    persist()
    return activeId.value
  }

  function selectConversation(id) {
    syncAccount()
    if (!conversations.value.some(item => item.id === id)) return
    if (activeId.value !== id && !attachmentLeaveGuard()) return
    activeId.value = id
    validationError.value = ''
    persist()
    if (activeConversation.value?.remote && activeConversation.value.backed) loadRemoteDetail(id)
  }

  async function renameConversation(id, title) {
    syncAccount()
    const conversation = conversations.value.find(item => item.id === id)
    if (!conversation || !title.trim()) return false
    const generation = accountEpoch.value
    if (conversation.remote && conversation.backed) {
      invalidateRemoteReads()
      try { await chatAttachmentsApi.rename(id, title.trim().slice(0, 80)) }
      catch (error) { if (sameAccount(generation)) remoteError.value = error.message; return false }
      if (!sameAccount(generation) || !conversations.value.includes(conversation)) return false
    }
    conversation.title = title.trim().slice(0, 80)
    persist()
    return true
  }

  async function deleteConversation(id) {
    syncAccount()
    if (activeId.value === id && !attachmentLeaveGuard()) return
    const conversation = conversations.value.find(item => item.id === id)
    const generation = accountEpoch.value
    if (conversation?.remote && conversation.backed) {
      invalidateRemoteReads()
      try { await chatAttachmentsApi.delete(id) }
      catch (error) { if (sameAccount(generation)) remoteError.value = error.message; return }
      if (!sameAccount(generation)) return
    }
    conversations.value = conversations.value.filter(item => item.id !== id)
    if (activeId.value === id) activeId.value = [...conversations.value].sort((first, second) => second.updatedAt - first.updatedAt)[0]?.id ?? null
    persist()
    if (activeConversation.value?.remote && activeConversation.value.backed) loadRemoteDetail(activeId.value)
  }

  function setAttachmentLeaveGuard(guard) { attachmentLeaveGuard = guard || (() => true) }

  function invalidateRemoteReads() { remoteRevision++; remoteDetailSequence++; remoteLoading.value = false }

  function prepareAttachmentConversation() {
    syncAccount()
    if (activeConversation.value?.remote) return activeConversation.value
    const conversation = { ...createConversation(), title: '个人附件会话', remote: true, backed: false }
    conversations.value.unshift(conversation)
    activeId.value = conversation.id
    return activeConversation.value
  }

  async function loadRemoteConversations() {
    syncAccount()
    if (!currentSession.value || currentSession.value.mustChangePassword) return
    const generation = accountEpoch.value
    const revision = remoteRevision
    try {
      const items = await chatAttachmentsApi.list()
      if (!sameAccount(generation) || revision !== remoteRevision) return
      if (!Array.isArray(items)) throw new Error('附件会话列表响应无效')
      for (const item of items) {
        if (item.teamId != null || typeof item.id !== 'string') continue
        if (!conversations.value.some(existing => existing.id === item.id)) conversations.value.push({ ...item, remote: true, backed: true, messages: [] })
      }
      remoteError.value = ''
    } catch (error) { if (sameAccount(generation) && revision === remoteRevision) remoteError.value = `附件历史加载失败：${error.message}；普通文本聊天不受影响。` }
  }

  async function loadRemoteDetail(id) {
    const generation = accountEpoch.value
    const revision = remoteRevision
    const sequence = ++remoteDetailSequence
    remoteLoading.value = true
    try {
      const detail = await chatAttachmentsApi.detail(id)
      if (!sameAccount(generation) || revision !== remoteRevision || sequence !== remoteDetailSequence) return
      const conversation = conversations.value.find(item => item.id === id && item.remote)
      if (conversation) Object.assign(conversation, detail, { remote: true, backed: true })
      remoteError.value = ''
    } catch (error) {
      if (sameAccount(generation) && revision === remoteRevision && sequence === remoteDetailSequence) {
        const conversation = conversations.value.find(item => item.id === id && item.remote)
        if (conversation) conversation.messages = []
        remoteError.value = `附件会话读取失败：${error.message}`
      }
    } finally { if (sameAccount(generation) && sequence === remoteDetailSequence) remoteLoading.value = false }
  }

  async function sendMessage(prompt) {
    syncAccount()
    if (activeConversation.value?.remote) return false
    const normalized = String(prompt || '').trim()
    validationError.value = ''
    if (!normalized || sending.value) return false
    if (normalized.length > 2000) {
      validationError.value = '消息不能超过 2000 字符。'
      return false
    }
    const generation = accountEpoch.value
    if (!optionsLoaded.value && !await loadOptions()) return false
    if (!sameAccount(generation) || !canSend.value || sending.value) return false
    if (!activeConversation.value) newConversation()
    const conversation = activeConversation.value
    const providerKey = selectedKey.value
    const history = assistantHistory(conversation.messages)
    if (!conversation.messages.length && conversation.title === '新对话') conversation.title = normalized.replace(/\s+/g, ' ').slice(0, 32)
    conversation.messages.push({ id: crypto.randomUUID(), role: 'user', content: normalized })
    conversation.messages.push({ id: crypto.randomUUID(), role: 'assistant', content: '', pending: true, providerKey })
    const pending = conversation.messages.at(-1)
    conversation.updatedAt = Date.now()
    persist()

    try {
      const data = unwrap(await sendAssistantChat({ providerKey, message: normalized, history }))
      if (!sameAccount(generation) || !conversations.value.includes(conversation)) return false
      if (typeof data?.content !== 'string' || !data.content.trim()) throw new Error('模型已响应，但没有返回可显示的内容。')
      Object.assign(pending, replyMetadata(data), { pending: false, content: data.content.trim() })
      return true
    } catch (error) {
      if (!sameAccount(generation) || !conversations.value.includes(conversation)) return false
      pending.pending = false
      pending.error = true
      pending.content = error?.message || '暂时无法连接助手，请稍后重试。'
      return false
    } finally {
      if (sameAccount(generation) && conversations.value.includes(conversation)) {
        pending.pending = false
        conversation.updatedAt = Date.now()
        persist()
      }
    }
  }

  async function sendMessageStreaming(prompt, { images } = {}) {
    syncAccount()
    if (activeConversation.value?.remote) return false
    const normalized = String(prompt || '').trim()
    const imageEvidence = Array.isArray(images) ? images.map(name => String(name || '').trim()).filter(Boolean).slice(0, 5) : []
    validationError.value = ''
    if (!normalized || sending.value) return false
    if (normalized.length > 2000) {
      validationError.value = '消息不能超过 2000 字符。'
      return false
    }
    const generation = accountEpoch.value
    if (!optionsLoaded.value && !await loadOptions()) return false
    if (!sameAccount(generation) || !canSend.value || sending.value) return false
    if (!activeConversation.value) newConversation()
    const conversation = activeConversation.value
    const providerKey = selectedKey.value
    if (!conversation.messages.length && conversation.title === '新对话') conversation.title = normalized.replace(/\s+/g, ' ').slice(0, 32)
    conversation.messages.push({ id: crypto.randomUUID(), role: 'user', content: normalized, ...(imageEvidence.length ? { images: imageEvidence } : {}) })
    conversation.messages.push({ id: crypto.randomUUID(), role: 'assistant', content: '', pending: true, streaming: true, thinking: [], providerKey })
    const pending = conversation.messages.at(-1)
    conversation.updatedAt = Date.now()
    persist()

    try {
      await streamChat(normalized, {
        onThinking: (step) => {
          if (!conversations.value.includes(conversation)) return
          pending.thinking = [...(pending.thinking || []), step]
        },
        onToken: (delta) => {
          if (!conversations.value.includes(conversation)) return
          pending.content = (pending.content || '') + delta
        },
        onDone: (payload) => {
          if (!conversations.value.includes(conversation)) return
          Object.assign(pending, {
            pending: false,
            streaming: false,
            provider: payload?.provider,
            model: payload?.model,
            trustScore: payload?.trust_score,
            citations: payload?.citations || [],
            evidence: payload?.evidence || [],
            metadata: payload?.metadata || {},
          })
          conversation.updatedAt = Date.now()
          persist()
        },
        onError: (err) => {
          if (!conversations.value.includes(conversation)) return
          pending.pending = false
          pending.streaming = false
          pending.error = true
          pending.content = err?.message || '流式响应中断，请重试。'
        },
      }, { images: imageEvidence })
      return true
    } catch (error) {
      if (!conversations.value.includes(conversation)) return false
      pending.pending = false
      pending.streaming = false
      pending.error = true
      pending.content = error?.message || '暂时无法连接 AI 服务，请确认 ai-service 已启动。'
      return false
    } finally {
      if (sameAccount(generation) && conversations.value.includes(conversation)) {
        conversation.updatedAt = Date.now()
        persist()
      }
    }
  }

  function clearConversation() {
    deleteConversation(activeId.value)
  }

  watch(currentSession, syncAccount, { immediate: true, flush: 'sync' })
  return { conversations, activeId, activeConversation, messages, sending, errorMessage, storageWarning,
    remoteError, remoteLoading, loadRemoteConversations, loadRemoteDetail, prepareAttachmentConversation, setAttachmentLeaveGuard, invalidateRemoteReads,
    options, selectedKey, selectedOption, optionsLoaded, optionsLoading, optionsError, preferenceSaving,
    preferenceError, preferenceNotice, canSend, canSwitchToMini, accountEpoch, loadOptions, selectProvider,
    syncAccount, newConversation, selectConversation, renameConversation, deleteConversation, sendMessage, sendMessageStreaming, clearConversation }
})
