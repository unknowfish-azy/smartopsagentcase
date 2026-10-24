<template>
  <section class="ai-chat-panel" :class="{ 'ai-chat-panel--compact': compact }" aria-label="AI 对话面板" @dragover.prevent="dragging = true" @dragleave.self="dragging = false" @drop.prevent="handleDrop">
    <AssistantSelector v-if="!activeConversation?.remote" />
    <p v-else class="ai-chat-hint">附件会话 · 不调用模型 · <button type="button" class="attachment-text-action" @click="chatStore.newConversation()">新建文本问答</button></p>
    <div v-if="messages.length" ref="messageList" class="ai-chat-messages" aria-live="polite" role="log" aria-label="会话消息">
      <article v-for="message in messages" :key="message.id" class="ai-chat-message" :class="`ai-chat-message--${message.role}`">
        <div class="ai-chat-message__meta">{{ message.role === 'user' ? 'YOU' : message.providerKey === 'attachment-receipt' ? '附件保存回执 · 非 AI 分析' : 'SMARTOPS AGENT' }}</div>
        <p v-if="message.pending" class="ai-chat-pending"><span></span><span></span><span></span></p>
        <p v-else :class="{ 'ai-chat-message__error': message.error }">{{ message.content }}</p>
        <AssistantEvidence v-if="!message.pending && !message.error" :message="message" />
        <ChatMessageAttachments :key="`${activeId}:${message.id}`" :conversation-id="activeId" :attachments="message.attachments" :vision-events="message.visionEvents" />
      </article>
    </div>
    <div v-else class="ai-chat-empty">
      <span class="ai-chat-empty__mark" aria-hidden="true">AI</span>
      <div><strong>从一个运维问题开始</strong><p>描述现象、目标或需要核对的指标，默认使用智维 Mini，也可选择自己的模型连接；仅提供建议，不执行命令。</p></div>
    </div>

    <form class="ai-chat-composer" :class="{ 'is-dragging': dragging }" @submit.prevent="sendMessage">
      <p v-if="dragging" class="ai-chat-hint">松开以添加附件；不会发送给模型</p>
      <ChatAttachmentComposer ref="attachmentComposer" @context-change="preserveDraft" />
      <textarea ref="textareaRef" v-model="draft" rows="1" maxlength="2000" aria-label="输入消息" :placeholder="activeConversation?.remote ? '补充附件说明（可留空）…' : compact ? '输入一个运维问题…' : '描述你要完成的运维目标…'" :disabled="sending || attachmentBusy" @paste="attachmentComposer?.paste($event)" @input="adjustHeight()" @keydown="handleKeyDown"></textarea>
      <div class="ai-chat-composer__footer">
        <div class="ai-chat-composer__tools">
          <button type="button" class="ai-chat-icon-button" :disabled="sending || attachmentBusy" aria-label="添加附件" title="添加图片或文本附件（私有保存，暂不分析）" @click="attachmentComposer?.pick()">
            <Paperclip :size="16" aria-hidden="true" />
          </button>
          <button type="button" class="ai-chat-project" @click="attachmentNotice = '当前会话使用默认运维工作空间'">
            <Plus :size="15" aria-hidden="true" /> 项目
          </button>
        </div>
        <button type="submit" class="ai-chat-send" :disabled="sending || attachmentBusy || remoteLoading || (!activeConversation?.remote && !canSend) || (!draft.trim() && !attachmentCount)" aria-label="发送消息" title="发送消息">
          <Loading v-if="sending" class="is-loading" :size="16" aria-hidden="true" />
          <ArrowUp v-else :size="16" aria-hidden="true" />
        </button>
      </div>
      <p v-if="attachmentNotice" class="ai-chat-hint" role="status">{{ attachmentNotice }}</p>
      <p v-if="errorMessage" class="ai-chat-error" role="alert">{{ errorMessage }}</p>
    </form>

    <div v-if="!messages.length && !activeConversation?.remote" class="ai-chat-quick-actions" aria-label="快捷问题">
      <button v-for="action in quickActions" :key="action.label" type="button" @click="useQuickAction(action.prompt)">{{ action.label }}</button>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ArrowUp, Loading, Paperclip, Plus } from '@element-plus/icons-vue'
import { useAiChatStore } from '../../stores/aiChat.js'
import AssistantSelector from './AssistantSelector.vue'
import AssistantEvidence from './AssistantEvidence.vue'
import ChatAttachmentComposer from './ChatAttachmentComposer.vue'
import ChatMessageAttachments from './ChatMessageAttachments.vue'

defineProps({ compact: { type: Boolean, default: false } })

const drafts = ref({})
const attachmentNotice = ref('')
const textareaRef = ref(null)
let disposed = false
const chatStore = useAiChatStore()
const { messages, sending, errorMessage, activeId, activeConversation, remoteLoading, canSend, accountEpoch } = storeToRefs(chatStore)
const attachmentComposer = ref(null)
const attachmentBusy = computed(() => Boolean(attachmentComposer.value?.busy))
const attachmentCount = computed(() => attachmentComposer.value?.count || 0)
const dragging = ref(false)
function handleDrop(event) { dragging.value = false; attachmentComposer.value?.drop(event) }
function preserveDraft({ previousId, nextId }) { drafts.value[nextId] = drafts.value[previousId || 'new'] || '' }
const messageList = ref(null)
const draft = computed({ get: () => drafts.value[activeId.value || 'new'] || '', set: value => { drafts.value[activeId.value || 'new'] = value } })

watch([activeId, () => messages.value.length, sending], async () => {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
  adjustHeight()
}, { immediate: true })

watch(accountEpoch, () => { drafts.value = {}; attachmentNotice.value = '' }, { flush: 'sync' })

const quickActions = [
  { label: '诊断 CPU 过载', prompt: '帮我诊断一台服务器 CPU 持续过载的问题，列出需要核对的指标、日志和处置步骤。' },
  { label: '生成巡检计划', prompt: '为中小企业生产环境生成一份今天的服务器巡检计划。' },
  { label: '查询运维知识', prompt: '解释如何快速判断 Kubernetes Pod 反复重启的根因。' }
]

function adjustHeight(reset = false) {
  const textarea = textareaRef.value
  if (!textarea) return
  if (reset) {
    textarea.style.height = '60px'
    return
  }
  textarea.style.height = '60px'
  textarea.style.height = `${Math.min(Math.max(textarea.scrollHeight, 60), 200)}px`
}

function handleKeyDown(event) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    sendMessage()
  }
}

function useQuickAction(prompt) {
  draft.value = prompt
  attachmentNotice.value = ''
  nextTick(() => { adjustHeight(); textareaRef.value?.focus() })
}

async function sendMessage() {
  const prompt = draft.value.trim()
  if (activeConversation.value?.remote) {
    const conversationId = activeId.value
    if (await attachmentComposer.value?.submit(prompt) && activeId.value === conversationId) { draft.value = ''; adjustHeight(true) }
    return
  }
  if (!prompt || sending.value || !canSend.value || disposed) return
  attachmentNotice.value = ''
  draft.value = ''
  adjustHeight(true)
  const conversationId = activeId.value
  const generation = accountEpoch.value
  const success = await chatStore.sendMessage(prompt)
  if (!success && !disposed && accountEpoch.value === generation && (!conversationId || activeId.value === conversationId) && !draft.value) draft.value = prompt
  await nextTick()
  if (!disposed && activeId.value === conversationId) textareaRef.value?.focus()
}

onBeforeUnmount(() => { disposed = true })
</script>

<style scoped>
.ai-chat-panel { display: grid; gap: 14px; width: 100%; max-width: 860px; margin: 0 auto; }
.ai-chat-panel button svg { flex: 0 0 16px; width: 16px; height: 16px; }
.ai-chat-panel--compact { max-width: none; }
.ai-chat-messages { display: grid; gap: 10px; max-height: 420px; overflow-y: auto; padding: 2px; }
.ai-chat-message { max-width: min(88%, 700px); padding: 12px 14px; border: 1px solid var(--smart-border); border-radius: 10px; background: color-mix(in srgb, var(--smart-surface) 88%, transparent); }
.ai-chat-message--user { justify-self: end; border-color: color-mix(in srgb, var(--smart-primary) 50%, var(--smart-border)); background: color-mix(in srgb, var(--smart-primary-soft, rgba(122,215,245,.12)) 72%, var(--smart-surface)); }
.ai-chat-message__meta { margin-bottom: 7px; color: var(--smart-primary-strong); font: 9px var(--font-mono); letter-spacing: .12em; }
.ai-chat-message p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--smart-text); font-size: 13px; line-height: 1.65; }
.ai-chat-message__error, .ai-chat-error { color: var(--smart-danger, #f08d9c) !important; }
.ai-chat-pending { display: flex; gap: 5px; align-items: center; min-height: 22px; }
.ai-chat-pending span { width: 5px; height: 5px; border-radius: 50%; background: var(--smart-primary-strong); animation: chat-pulse 1s infinite ease-in-out; }
.ai-chat-pending span:nth-child(2) { animation-delay: .14s; }.ai-chat-pending span:nth-child(3) { animation-delay: .28s; }
.ai-chat-empty { display: flex; align-items: center; gap: 14px; padding: 16px 2px 4px; color: var(--smart-muted); }
.ai-chat-empty__mark { display: grid; place-items: center; flex: 0 0 38px; height: 38px; border: 1px solid var(--smart-border-strong); border-radius: 10px; color: var(--smart-primary-strong); font: 11px var(--font-mono); }
.ai-chat-empty strong { display: block; color: var(--smart-text); font-size: 14px; font-weight: 500; }.ai-chat-empty p { margin: 5px 0 0; font-size: 12px; line-height: 1.6; }
.ai-chat-composer { border: 1px solid var(--smart-border-strong); border-radius: 12px; background: color-mix(in srgb, var(--smart-surface) 94%, transparent); box-shadow: 0 14px 34px rgba(0,0,0,.12); overflow: hidden; }
.ai-chat-composer.is-dragging { border-color: var(--smart-primary-strong); outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.attachment-text-action { min-height: 32px; padding: 4px 9px; border: 1px solid var(--smart-border-strong); border-radius: 6px; background: var(--smart-surface); color: var(--smart-text); cursor: pointer; font: inherit; }.attachment-text-action:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.ai-chat-composer textarea { display: block; width: 100%; min-height: 60px; max-height: 200px; box-sizing: border-box; padding: 15px 16px 8px; border: 0; resize: none; overflow-y: auto; background: transparent; color: var(--smart-text); font: 13px/1.6 var(--font-cn); outline: none; }
.ai-chat-composer textarea::placeholder { color: var(--smart-muted); }.ai-chat-composer__footer { display: flex; align-items: center; justify-content: space-between; min-height: 48px; padding: 7px 10px; border-top: 1px solid var(--smart-border); }
.ai-chat-composer__tools { display: flex; align-items: center; gap: 5px; }.ai-chat-icon-button, .ai-chat-project, .ai-chat-send, .ai-chat-quick-actions button { border: 1px solid transparent; background: transparent; color: var(--smart-muted); cursor: pointer; transition: color var(--duration-fast), background-color var(--duration-fast), border-color var(--duration-fast); }
.ai-chat-icon-button { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 7px; }.ai-chat-icon-button:hover, .ai-chat-icon-button:focus-visible { color: var(--smart-text); background: var(--smart-primary-soft); }
.ai-chat-project { display: inline-flex; align-items: center; gap: 4px; min-height: 32px; padding: 0 9px; border-style: dashed; border-color: var(--smart-border); border-radius: 7px; font-size: 11px; }.ai-chat-project:hover, .ai-chat-project:focus-visible { color: var(--smart-text); border-color: var(--smart-border-strong); }
.ai-chat-send { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 8px; border-color: var(--smart-border); }.ai-chat-send:not(:disabled) { color: var(--smart-primary-foreground, #041018); background: var(--smart-primary); border-color: transparent; }.ai-chat-send:disabled { opacity: .42; cursor: not-allowed; }.ai-chat-send:focus-visible, .ai-chat-project:focus-visible, .ai-chat-quick-actions button:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.ai-chat-hint, .ai-chat-error { margin: 0; padding: 0 13px 9px; font-size: 11px; }.ai-chat-hint { color: var(--smart-muted); }
.ai-chat-quick-actions { display: flex; flex-wrap: wrap; gap: 7px; }.ai-chat-quick-actions button { min-height: 32px; padding: 0 10px; border-color: var(--smart-border); border-radius: 999px; font-size: 11px; }.ai-chat-quick-actions button:hover { color: var(--smart-text); background: var(--smart-surface); border-color: var(--smart-border-strong); }
.is-loading { animation: chat-spin 1s linear infinite; } @keyframes chat-spin { to { transform: rotate(360deg); } } @keyframes chat-pulse { 0%, 80%, 100% { opacity: .35; transform: scale(.8); } 40% { opacity: 1; transform: scale(1); } }
@media (max-width: 600px) { .ai-chat-message { max-width: 94%; }.ai-chat-empty { align-items: flex-start; }.ai-chat-quick-actions { gap: 6px; }.ai-chat-quick-actions button { flex: 1 1 140px; } }
@media (prefers-reduced-motion: reduce) { .ai-chat-pending span, .is-loading { animation: none; } }
</style>
