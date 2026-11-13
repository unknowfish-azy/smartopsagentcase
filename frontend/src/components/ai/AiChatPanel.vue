<template>
  <section class="ai-chat-panel" :class="{ 'ai-chat-panel--compact': compact }" aria-label="AI 对话面板" @dragover.prevent="dragging = true" @dragleave.self="dragging = false" @drop.prevent="handleDrop">
    <AssistantSelector v-if="!activeConversation?.remote" allow-create />
    <p v-else class="ai-chat-hint">附件会话 · 不调用模型 · <button type="button" class="attachment-text-action" @click="chatStore.newConversation()">新建文本问答</button></p>
    <div v-if="messages.length" ref="messageList" class="ai-chat-messages" aria-live="polite" role="log" aria-label="会话消息" tabindex="-1">
      <button v-if="hiddenCount" type="button" class="ai-chat-earlier" @click="showEarlierMessages">加载更早的消息（还有 {{ hiddenCount }} 条）</button>
      <article v-for="message in visibleMessages" :key="message.id" class="ai-chat-message" :class="`ai-chat-message--${message.role}`">
        <div class="ai-chat-message__meta">{{ message.role === 'user' ? 'YOU' : message.providerKey === 'attachment-receipt' ? '附件保存回执 · 非 AI 分析' : 'SMARTOPS AGENT' }}</div>
        <details v-if="message.thinking && message.thinking.length" class="ai-trace" :open="message.streaming">
          <summary class="ai-trace__head">
            <span class="ai-trace__title">处理过程</span>
            <span class="ui-tag ui-tag--sm" :class="message.streaming ? 'ui-tag--info' : 'ui-tag--success'">{{ message.streaming ? '处理中' : '已完成' }}</span>
            <span class="ai-trace__count">{{ message.thinking.length }} 步</span>
          </summary>
          <ol class="ai-trace__list" aria-label="AI 处理时间线">
            <li
              v-for="(step, index) in message.thinking"
              :key="index"
              class="ai-trace__step"
              :class="{ 'is-active': message.streaming && index === message.thinking.length - 1, 'is-done': !message.streaming || index < message.thinking.length - 1 }"
            >
              <span class="ai-trace__marker" aria-hidden="true"></span>
              <div class="ai-trace__body">
                <div class="ai-trace__row">
                  <span class="ui-tag ui-tag--sm ui-tag--mono" :class="`ui-tag--${stepKind(step.label).tone}`">{{ stepKind(step.label).tag }}</span>
                  <strong>{{ step.label }}</strong>
                </div>
                <p v-if="step.detail">{{ step.detail }}</p>
              </div>
            </li>
          </ol>
        </details>
        <p v-if="message.pending && !message.streaming && !message.content" class="ai-chat-pending"><span></span><span></span><span></span></p>
        <p v-else-if="message.content" :class="{ 'ai-chat-message__error': message.error }">{{ message.content }}<span v-if="message.streaming" class="ai-cursor" aria-hidden="true"></span></p>
        <div v-if="message.error && !message.pending" class="ai-chat-retry-row">
          <span class="ai-chat-retry-hint">回答生成失败，可直接重试；不会重复发送你的问题。</span>
          <button type="button" class="ai-chat-retry" :disabled="sending" :aria-label="`重试第 ${message.attempt || 1} 次失败的回答`" @click="retryMessage(message.id)">重试</button>
        </div>
        <p v-if="message.recovered" class="ai-chat-status ai-chat-status--recovered" role="status">重试成功（第 {{ message.attempt }} 次尝试）</p>
        <p v-if="message.metadata?.degraded" class="ai-chat-status ai-chat-status--degraded" role="status">当前为降级模式：真实模型不可用，已回落到本地 mock。</p>
        <p v-if="message.metadata?.inspection?.status === 'REJECTED'" class="ai-chat-status ai-chat-status--rejected" role="alert">纠察结果：REJECTED，状态核验失败，需要重新规划。</p>
        <details v-if="message.metadata?.run_event" class="ai-run-diagnostics">
          <summary>运行诊断 · {{ runEventStatusLabel(message.metadata.run_event.status) }}</summary>
          <dl>
            <div><dt>来源</dt><dd>{{ message.metadata.run_event.source || '未知' }}</dd></div>
            <div>
              <dt>请求</dt>
              <dd class="ai-run-diagnostics__id">
                <span>{{ message.metadata.run_event.request_id }}</span>
                <button type="button" class="ai-run-diagnostics__copy" :aria-label="`复制请求 ID ${message.metadata.run_event.request_id}`" @click="copyDiagnostic(message.id, 'request_id', message.metadata.run_event.request_id)">复制</button>
                <span v-if="copyFeedback[`${message.id}:request_id`]" class="ai-run-diagnostics__feedback" role="status">{{ copyFeedback[`${message.id}:request_id`] === 'copied' ? '已复制' : '复制失败' }}</span>
              </dd>
            </div>
            <div><dt>任务</dt><dd>{{ message.metadata.run_event.task_id || '未设置' }}</dd></div>
            <div>
              <dt>运行</dt>
              <dd class="ai-run-diagnostics__id">
                <span>{{ message.metadata.run_event.run_id }}</span>
                <button type="button" class="ai-run-diagnostics__copy" :aria-label="`复制运行 ID ${message.metadata.run_event.run_id}`" @click="copyDiagnostic(message.id, 'run_id', message.metadata.run_event.run_id)">复制</button>
                <span v-if="copyFeedback[`${message.id}:run_id`]" class="ai-run-diagnostics__feedback" role="status">{{ copyFeedback[`${message.id}:run_id`] === 'copied' ? '已复制' : '复制失败' }}</span>
              </dd>
            </div>
            <div><dt>有效模型</dt><dd>{{ effectiveProvider(message) }}</dd></div>
            <div><dt>降级</dt><dd>{{ degradationText(message) }}</dd></div>
            <div v-if="message.metadata.degradation_reason"><dt>降级原因</dt><dd>{{ message.metadata.degradation_reason }}</dd></div>
            <div><dt>检索</dt><dd>{{ retrievalText(message) }}</dd></div>
            <div v-if="message.metadata.rag_degradation_reason"><dt>检索原因</dt><dd>{{ message.metadata.rag_degradation_reason }}</dd></div>
            <div><dt>引用</dt><dd>{{ citationCount(message) }} 条</dd></div>
            <div><dt>纠察</dt><dd>{{ inspectionText(message) }}</dd></div>
            <div><dt>首 token</dt><dd>{{ formatDuration(message.firstTokenMs) }}</dd></div>
            <div><dt>总耗时</dt><dd>{{ formatDuration(message.totalMs) }}</dd></div>
          </dl>
          <div class="ai-run-diagnostics__actions">
            <RouterLink to="/operations/runs" class="ai-run-diagnostics__link">打开运行记录</RouterLink>
          </div>
          <p class="ai-run-diagnostics__hint">关联 ID 仅用于定位本次请求，不代表审批或身份；运行记录页暂不支持按 run_id 精确检索，打开后可按时间范围与状态对照。</p>
        </details>
        <AssistantEvidence v-if="!message.pending && !message.error" :message="message" />
        <ChatMessageAttachments :key="`${activeId}:${message.id}`" :conversation-id="activeId" :attachments="message.attachments" :vision-events="message.visionEvents" />
      </article>
    </div>
    <div v-else class="ai-chat-empty">
      <span class="ai-chat-empty__mark" aria-hidden="true">AI</span>
      <div><strong>从一个运维问题开始</strong><p>描述现象、目标或需要核对的指标，默认使用智维 Mini，也可选择自己的模型连接；仅提供建议，不执行命令。</p></div>
    </div>

    <form class="ai-chat-composer" :class="{ 'is-dragging': dragging }" @submit.prevent="sendMessage">
      <p v-if="dragging" class="ai-chat-hint">松开以添加图像证据或附件；仅图像证据参与 AI 分析</p>
      <ChatAttachmentComposer ref="attachmentComposer" @context-change="preserveDraft" />
      <textarea ref="textareaRef" v-model="draft" rows="1" maxlength="2000" aria-label="输入消息" aria-keyshortcuts="Alt+C" title="Enter 发送 · Shift+Enter 换行 · Alt+C 聚焦输入框" :placeholder="activeConversation?.remote ? '补充附件说明（可留空）…' : compact ? '输入一个运维问题…' : '描述你要完成的运维目标…'" :disabled="sending || attachmentBusy" @paste="attachmentComposer?.paste($event)" @input="adjustHeight()" @keydown="handleKeyDown"></textarea>
      <div class="ai-chat-composer__footer">
        <div class="ai-chat-composer__tools">
          <button v-if="speechSupported" type="button" class="ai-chat-icon-button" :class="{ 'is-recording': speechListening }" :disabled="sending || attachmentBusy" :aria-pressed="speechListening" :aria-label="speechListening ? '停止语音输入' : '语音输入'" :title="speechListening ? '停止语音输入' : '语音输入（需浏览器支持）'" @click="toggleVoice">
            <Microphone :size="16" aria-hidden="true" />
          </button>
          <button type="button" class="ai-chat-icon-button" :disabled="sending || attachmentBusy" aria-label="添加附件" title="添加图像证据（参与 AI 分析）或文本附件（私有保存）" @click="attachmentComposer?.pick()">
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
      <p v-if="speechHint" class="ai-chat-hint" role="status">{{ speechHint }}</p>
      <p v-if="errorMessage" class="ai-chat-error" role="alert">{{ errorMessage }}</p>
      <details class="ai-chat-rag-debug">
        <summary>检索调试 · RAG 参数</summary>
        <div class="rag-debug-grid">
          <label class="rag-debug-item">
            <span>top_k <em>{{ ragTopK }}</em></span>
            <input type="range" min="1" max="20" :value="ragTopK" @input="ragTopK = Number($event.target.value)" />
          </label>
          <label class="rag-debug-item">
            <span>分数阈值 <em>{{ ragScoreThreshold.toFixed(2) }}{{ ragScoreThreshold === 0 ? '（不截断）' : '' }}</em></span>
            <input type="range" min="0" max="1" step="0.05" :value="ragScoreThreshold" @input="ragScoreThreshold = Number($event.target.value)" />
          </label>
          <label class="rag-debug-item">
            <span>向量权重 <em>{{ ragVectorWeight.toFixed(2) }} / BM25 {{ ragBm25Weight.toFixed(2) }}</em></span>
            <input type="range" min="0" max="1" step="0.05" :value="ragVectorWeight" @input="ragVectorWeight = Number($event.target.value)" />
          </label>
          <label class="rag-debug-item rag-debug-item--source">
            <span>source 过滤 <em>{{ ragSource || '不限' }}</em></span>
            <input type="text" v-model="ragSource" placeholder="nginx / reference/java" />
          </label>
        </div>
        <button type="button" class="rag-debug-reset" @click="ragTopK = 5; ragScoreThreshold = 0; ragVectorWeight = 0.6; ragSource = ''">恢复默认</button>
      </details>
    </form>

    <div v-if="!messages.length && !activeConversation?.remote" class="ai-chat-quick-actions" aria-label="快捷问题">
      <button v-for="action in quickActions" :key="action.label" type="button" @click="useQuickAction(action.prompt)">{{ action.label }}</button>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ArrowUp, Loading, Microphone, Paperclip, Plus } from '@element-plus/icons-vue'
import { useAiChatStore } from '../../stores/aiChat.js'
import { createSpeechInput } from '../../domain/chat/speechInput.ts'
import AssistantSelector from './AssistantSelector.vue'
import AssistantEvidence from './AssistantEvidence.vue'
import ChatAttachmentComposer from './ChatAttachmentComposer.vue'
import ChatMessageAttachments from './ChatMessageAttachments.vue'

defineProps({ compact: { type: Boolean, default: false } })

const drafts = ref({})
const attachmentNotice = ref('')
const textareaRef = ref(null)
let disposed = false
const speechSupported = ref(false)
const speechListening = ref(false)
const speechHint = ref('')
let speech = null
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

// 长会话只渲染最近一批消息，更早的按需展开，避免演示 20 分钟后 DOM 无限增长。
const MESSAGE_BATCH = 30
const visibleCount = ref(MESSAGE_BATCH)
const visibleMessages = computed(() => messages.value.slice(-visibleCount.value))
const hiddenCount = computed(() => Math.max(0, messages.value.length - visibleCount.value))
function showEarlierMessages() { visibleCount.value += MESSAGE_BATCH }

// 检索调试参数——默认值对齐 knowledge 服务 config。
const ragTopK = ref(5)
const ragScoreThreshold = ref(0)      // 0 = 不传 = 不截断
const ragVectorWeight = ref(0.6)     // 0.6 = knowledge 默认 vector_weight
const ragSource = ref('')             // '' = 不传 = 全源

const ragBm25Weight = computed(() => +(1 - ragVectorWeight.value).toFixed(2))

// 只组装有效字段；stream.ts 里只有非 null 才会进请求体。
function buildRagPayload() {
  const rag = { top_k: ragTopK.value }
  if (ragScoreThreshold.value > 0) rag.score_threshold = ragScoreThreshold.value
  if (ragVectorWeight.value !== 0.6) {
    rag.vector_weight = ragVectorWeight.value
    rag.bm25_weight = ragBm25Weight.value
  }
  if (ragSource.value.trim()) rag.source = ragSource.value.trim()
  return rag
}

function runEventStatusLabel(status) {
  return { started: '已开始', succeeded: '已完成', failed: '失败', denied: '已拒绝', dry_run: '演练' }[status] || '未知状态'
}

/* 处理步骤分类：只根据步骤标题里的关键词推断「检索 / 工具 / 推理」，不改变 store 协议。 */
const STEP_KINDS = [
  { test: /检索|知识|引用|RAG|召回/i, tag: '检索', tone: 'info' },
  { test: /工具|调用|执行|脚本|诊断|巡检|检查/i, tag: '工具', tone: 'warning' },
  { test: /推理|分析|规划|思考|判断|生成/i, tag: '推理', tone: 'neutral' }
]
function stepKind(label = '') {
  return STEP_KINDS.find(kind => kind.test.test(label)) || { tag: '步骤', tone: 'neutral' }
}

// 运行诊断只展示本链路真实上报的字段；缺失就明确写“未记录”，不猜测 provider 或耗时。
const RAG_STATUS_LABELS = { ok: '正常（有命中）', empty: '无命中', disabled: '未启用' }
function effectiveProvider(message) {
  return message.metadata?.effective_provider || message.provider || message.providerKey || '未记录'
}
function degradationText(message) {
  const meta = message.metadata || {}
  if (meta.degraded === true) return `是 · 已回落到 ${meta.effective_provider || '降级模型'}`
  if (meta.degraded === false) return '否（真实模型可用）'
  return '未记录'
}
function retrievalText(message) {
  const meta = message.metadata || {}
  if (meta.rag_status) return `${RAG_STATUS_LABELS[meta.rag_status] || meta.rag_status}${Number.isFinite(meta.top_k) ? ` · top_k ${meta.top_k}` : ''}`
  if (meta.rag_enabled === false) return '未启用'
  return '未记录'
}
function citationCount(message) {
  return Array.isArray(message.citations) ? message.citations.length : 0
}
function inspectionText(message) {
  const inspection = message.metadata?.inspection
  if (!inspection?.status) return '未触发'
  return [inspection.status, inspection.severity, inspection.reason].filter(Boolean).join(' · ')
}
function formatDuration(ms) {
  return Number.isFinite(ms) ? `${Math.round(ms)} ms` : '未记录'
}

const copyFeedback = ref({})
const copyTimers = {}
async function copyDiagnostic(messageId, field, value) {
  if (!value) return
  const key = `${messageId}:${field}`
  window.clearTimeout(copyTimers[key])
  try {
    await navigator.clipboard.writeText(String(value))
    copyFeedback.value = { ...copyFeedback.value, [key]: 'copied' }
  } catch {
    copyFeedback.value = { ...copyFeedback.value, [key]: 'failed' }
  }
  copyTimers[key] = window.setTimeout(() => {
    const next = { ...copyFeedback.value }
    delete next[key]
    copyFeedback.value = next
    delete copyTimers[key]
  }, 1600)
}

watch([activeId, () => messages.value.length, sending], async () => {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
  adjustHeight()
}, { immediate: true })

watch(activeId, () => { visibleCount.value = MESSAGE_BATCH })

watch(accountEpoch, () => { drafts.value = {}; attachmentNotice.value = '' }, { flush: 'sync' })

onMounted(() => {
  speech = createSpeechInput({
    onTranscript: text => { draft.value = text; adjustHeight() },
    onStateChange: listening => {
      speechListening.value = listening
      if (listening) speechHint.value = ''
    },
    onError: message => { speechHint.value = message },
  })
  speechSupported.value = speech.supported
  window.addEventListener('keydown', focusShortcut)
  if (autoFocusAllowed()) focusComposer()
})

// 切换/新建会话后把焦点交回输入框；正在发送的会话切换不抢焦点（发送完成会自己回收）。
watch(activeId, (next, previous) => {
  if (next === previous || disposed || !autoFocusAllowed()) return
  focusComposer()
})

function toggleVoice() {
  if (!speech?.supported || sending.value || attachmentBusy.value || disposed) return
  speechHint.value = ''
  if (speechListening.value) speech.stop()
  else speech.start(draft.value)
}

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
  if (event.isComposing) return
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
    return
  }
  // Esc 退出输入：焦点交还消息区（而不是落到 body），键盘用户可以继续用方向键/PageDown 阅读。
  if (event.key === 'Escape' && !draft.value.trim() && messageList.value) {
    event.preventDefault()
    messageList.value.focus()
  }
}

function useQuickAction(prompt) {
  draft.value = prompt
  attachmentNotice.value = ''
  nextTick(() => { adjustHeight(); textareaRef.value?.focus() })
}

async function sendMessage() {
  const prompt = draft.value.trim()
  if (speechListening.value) speech?.stop()
  if (activeConversation.value?.remote) {
    const conversationId = activeId.value
    if (await attachmentComposer.value?.submit(prompt) && activeId.value === conversationId) { draft.value = ''; adjustHeight(true) }
    return
  }
  const images = attachmentComposer.value?.stagedImageNames?.() || []
  const text = prompt || (images.length ? '请分析这些图像证据，给出运维建议。' : '')
  if (!text || sending.value || !canSend.value || disposed) return
  attachmentNotice.value = ''
  draft.value = ''
  adjustHeight(true)
  const conversationId = activeId.value
  const generation = accountEpoch.value
  const success = await chatStore.sendMessageStreaming(text, { images, rag: buildRagPayload() })
  if (success) attachmentComposer.value?.clearStaged?.()
  if (!success && !disposed && accountEpoch.value === generation && (!conversationId || activeId.value === conversationId) && !draft.value) draft.value = prompt
  if (!disposed && (!conversationId || activeId.value === conversationId)) await focusComposer()
}

// focus() 在输入框仍处于 disabled 的同一帧会被浏览器忽略，因此等一帧再聚焦。
async function focusComposer() {
  await nextTick()
  if (disposed || sending.value || attachmentBusy.value) return
  await new Promise(resolve => requestAnimationFrame(resolve))
  if (!disposed && !sending.value && !attachmentBusy.value) textareaRef.value?.focus()
}

// 触屏设备聚焦会直接弹出软键盘，自动聚焦只在精确指针设备上启用。
function autoFocusAllowed() {
  return !window.matchMedia('(pointer: coarse)').matches
}

// Alt+C 聚焦输入框：避开已占用的 Ctrl/Cmd+K（命令面板）与 Alt+Left/Right（页面步进）。
function focusShortcut(event) {
  if (event.defaultPrevented || event.isComposing) return
  if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
  // 用 code 兜底：部分布局与 macOS Option+C 下 event.key 不是 "c"。
  if (event.code !== 'KeyC' && event.key.toLowerCase() !== 'c') return
  // 弹窗/抽屉/命令面板（原生 dialog[open]）打开时不抢焦点；在其他输入控件里编辑时也不打断。
  const modal = document.querySelector('[role="dialog"][aria-modal="true"], dialog[open]')
  if (modal && modal.getClientRects().length) return
  const editable = event.target?.closest?.('input, textarea, select, [contenteditable="true"]')
  if (editable && editable !== textareaRef.value) return
  event.preventDefault()
  focusComposer()
}

// 失败回答原地重试：消息条数不变，完成后把焦点还给输入框，保证键盘用户能继续操作。
async function retryMessage(messageId) {
  if (sending.value || disposed) return
  const conversationId = activeId.value
  await chatStore.retryMessageStreaming(messageId)
  if (disposed) return
  adjustHeight()
  if (!conversationId || activeId.value === conversationId) await focusComposer()
}

onBeforeUnmount(() => {
  disposed = true
  speech?.dispose()
  speech = null
  Object.values(copyTimers).forEach(timer => window.clearTimeout(timer))
  window.removeEventListener('keydown', focusShortcut)
})
</script>

<style scoped>
.ai-chat-panel { display: grid; gap: 14px; width: 100%; max-width: 860px; margin: 0 auto; }
.ai-chat-panel button svg { flex: 0 0 16px; width: 16px; height: 16px; }
.ai-chat-panel--compact { max-width: none; }
.ai-chat-messages { display: grid; gap: 10px; max-height: 420px; overflow-y: auto; padding: 2px; }
.ai-chat-earlier { justify-self: center; padding: 6px 14px; border: 1px solid var(--smart-border); border-radius: 999px; background: var(--smart-surface); color: var(--smart-muted); font-size: 12px; cursor: pointer; }
.ai-chat-earlier:hover { color: var(--smart-text); border-color: var(--smart-border-strong); }
.ai-chat-earlier:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.ai-chat-message { max-width: min(88%, 700px); padding: 12px 14px; border: 1px solid var(--smart-border); border-radius: 10px; background: color-mix(in srgb, var(--smart-surface) 88%, transparent); }
.ai-chat-message--user { justify-self: end; border-color: color-mix(in srgb, var(--smart-primary) 50%, var(--smart-border)); background: color-mix(in srgb, var(--smart-primary-soft, rgba(122,215,245,.12)) 72%, var(--smart-surface)); }
.ai-chat-message__meta { margin-bottom: 7px; color: var(--smart-primary-strong); font: 9px var(--font-mono); letter-spacing: .12em; }
.ai-chat-message p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--smart-text); font-size: 13px; line-height: 1.65; }
.ai-chat-message__error, .ai-chat-error { color: var(--smart-danger, #f08d9c) !important; }
/* 浅色主题下原错误色 #f08d9c 对比度不足，改用深红以满足 AA。 */
[data-theme='light'] .ai-chat-message__error, [data-theme='light'] .ai-chat-error { color: #b42318 !important; }
.ai-chat-retry-row { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.ai-chat-retry-hint { font-size: 11px; color: var(--smart-muted); }
.ai-chat-retry { min-height: 30px; padding: 4px 12px; border: 1px solid var(--smart-border-strong); border-radius: 7px; background: var(--smart-surface); color: var(--smart-text); font: inherit; font-size: 12px; cursor: pointer; }
.ai-chat-retry:hover { border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); }
.ai-chat-retry:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.ai-chat-retry:disabled { cursor: not-allowed; opacity: .6; }
.ai-chat-status--recovered { color: #4fb58b; }
[data-theme='light'] .ai-chat-status--recovered { color: #0f7b52; }
.ai-chat-status { margin: 8px 0 0 !important; padding: 6px 8px; border-radius: 6px; font-size: 11px !important; }
.ai-chat-status--degraded { color: var(--smart-warning, #d8ad67) !important; background: color-mix(in srgb, var(--smart-warning, #d8ad67) 12%, transparent); }
.ai-chat-status--rejected { color: var(--smart-danger, #f08d9c) !important; background: color-mix(in srgb, var(--smart-danger, #f08d9c) 12%, transparent); }
.ai-run-diagnostics { margin-top: 8px; border: 1px dashed var(--smart-border-strong); border-radius: 7px; background: color-mix(in srgb, var(--smart-surface) 64%, transparent); color: var(--smart-muted); }
.ai-run-diagnostics summary { cursor: pointer; padding: 6px 8px; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .08em; }
.ai-run-diagnostics dl { display: grid; gap: 4px; margin: 0; padding: 0 8px 6px; }
.ai-run-diagnostics dl div { display: grid; grid-template-columns: 56px minmax(0, 1fr); gap: 8px; font-size: 10px; line-height: 1.5; }
.ai-run-diagnostics dt { color: var(--smart-muted); }
.ai-run-diagnostics dd { margin: 0; overflow-wrap: anywhere; color: var(--smart-text); font-family: var(--font-mono); }
.ai-run-diagnostics__id { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.ai-run-diagnostics__copy { min-height: 22px; padding: 1px 7px; border: 1px solid var(--smart-border-strong); border-radius: 5px; background: transparent; color: var(--smart-primary-strong); font: inherit; font-size: 10px; cursor: pointer; }
.ai-run-diagnostics__copy:hover { color: var(--smart-text); border-color: var(--smart-primary-strong); }
.ai-run-diagnostics__copy:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 1px; }
.ai-run-diagnostics__feedback { color: var(--smart-muted); font-size: 10px; }
.ai-run-diagnostics__actions { padding: 0 8px 7px; }
.ai-run-diagnostics__link { display: inline-flex; align-items: center; min-height: 28px; padding: 3px 9px; border: 1px solid var(--smart-border-strong); border-radius: 6px; color: var(--smart-primary-strong); font-size: 10px; text-decoration: none; }
.ai-run-diagnostics__link:hover { color: var(--smart-text); border-color: var(--smart-primary-strong); }
.ai-run-diagnostics__link:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.ai-run-diagnostics__hint { padding: 0 8px 7px; color: var(--smart-muted) !important; font-size: 10px !important; }
.ai-chat-pending { display: flex; gap: 5px; align-items: center; min-height: 22px; }
.ai-chat-pending span { width: 5px; height: 5px; border-radius: 50%; background: var(--smart-primary-strong); animation: chat-pulse 1s infinite ease-in-out; }
.ai-chat-pending span:nth-child(2) { animation-delay: .14s; }.ai-chat-pending span:nth-child(3) { animation-delay: .28s; }
.ai-chat-empty { display: flex; align-items: center; gap: 14px; padding: 16px 2px 4px; color: var(--smart-muted); }
.ai-chat-empty__mark { display: grid; place-items: center; flex: 0 0 38px; height: 38px; border: 1px solid var(--smart-border-strong); border-radius: 10px; color: var(--smart-primary-strong); font: 11px var(--font-mono); }
.ai-chat-empty strong { display: block; color: var(--smart-text); font-size: 14px; font-weight: 500; }.ai-chat-empty p { margin: 5px 0 0; font-size: 12px; line-height: 1.6; }
.ai-chat-composer { border: 1px solid var(--smart-border-strong); border-radius: 12px; background: color-mix(in srgb, var(--smart-surface) 94%, transparent); box-shadow: 0 14px 34px rgba(0,0,0,.12); overflow: hidden; }
.ai-chat-composer.is-dragging { border-color: var(--smart-primary-strong); outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.ai-chat-composer:focus-within { border-color: var(--smart-primary-strong); box-shadow: 0 0 0 2px color-mix(in srgb, var(--smart-primary-strong) 45%, transparent), 0 14px 34px rgba(0,0,0,.12); }
.attachment-text-action { min-height: 32px; padding: 4px 9px; border: 1px solid var(--smart-border-strong); border-radius: 6px; background: var(--smart-surface); color: var(--smart-text); cursor: pointer; font: inherit; }.attachment-text-action:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.ai-chat-composer textarea { display: block; width: 100%; min-height: 60px; max-height: 200px; box-sizing: border-box; padding: 15px 16px 8px; border: 0; resize: none; overflow-y: auto; background: transparent; color: var(--smart-text); font: 13px/1.6 var(--font-cn); outline: none; }
.ai-chat-composer textarea::placeholder { color: var(--smart-muted); }.ai-chat-composer__footer { display: flex; align-items: center; justify-content: space-between; min-height: 48px; padding: 7px 10px; border-top: 1px solid var(--smart-border); }
.ai-chat-composer__tools { display: flex; align-items: center; gap: 5px; }.ai-chat-icon-button, .ai-chat-project, .ai-chat-send, .ai-chat-quick-actions button { border: 1px solid transparent; background: transparent; color: var(--smart-muted); cursor: pointer; transition: color var(--duration-fast), background-color var(--duration-fast), border-color var(--duration-fast); }
.ai-chat-icon-button { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 7px; }.ai-chat-icon-button:hover, .ai-chat-icon-button:focus-visible { color: var(--smart-text); background: var(--smart-primary-soft); }
.ai-chat-icon-button.is-recording { color: var(--smart-danger, #f08d9c); background: color-mix(in srgb, var(--smart-danger, #f08d9c) 14%, transparent); }
.ai-chat-icon-button.is-recording svg { animation: chat-pulse 1s infinite ease-in-out; }
.ai-chat-project { display: inline-flex; align-items: center; gap: 4px; min-height: 32px; padding: 0 9px; border-style: dashed; border-color: var(--smart-border); border-radius: 7px; font-size: 11px; }.ai-chat-project:hover, .ai-chat-project:focus-visible { color: var(--smart-text); border-color: var(--smart-border-strong); }
.ai-chat-send { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 8px; border-color: var(--smart-border); }.ai-chat-send:not(:disabled) { color: var(--smart-primary-foreground, #041018); background: var(--smart-primary); border-color: transparent; }.ai-chat-send:disabled { opacity: .42; cursor: not-allowed; }.ai-chat-send:focus-visible, .ai-chat-project:focus-visible, .ai-chat-quick-actions button:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.ai-chat-hint, .ai-chat-error { margin: 0; padding: 0 13px 9px; font-size: 11px; }.ai-chat-hint { color: var(--smart-muted); }
.ai-chat-quick-actions { display: flex; flex-wrap: wrap; gap: 7px; }.ai-chat-quick-actions button { min-height: 32px; padding: 0 10px; border-color: var(--smart-border); border-radius: 999px; font-size: 11px; }.ai-chat-quick-actions button:hover { color: var(--smart-text); background: var(--smart-surface); border-color: var(--smart-border-strong); }
.is-loading { animation: chat-spin 1s linear infinite; } @keyframes chat-spin { to { transform: rotate(360deg); } } @keyframes chat-pulse { 0%, 80%, 100% { opacity: .35; transform: scale(.8); } 40% { opacity: 1; transform: scale(1); } }
/* T20：处理过程升级为竖线时间线，步骤标签区分「检索 / 工具 / 推理」。 */
.ai-trace { margin: 0 0 8px; border: 1px solid var(--ds-hairline); border-radius: var(--ds-radius-md); background: color-mix(in srgb, var(--ds-surface-base) 70%, transparent); }
.ai-trace__head { display: flex; align-items: center; gap: 8px; padding: 8px 10px; list-style: none; cursor: pointer; }
.ai-trace__head::-webkit-details-marker { display: none; }
.ai-trace__title { color: var(--ds-color-muted); font: 9px var(--ds-font-mono); letter-spacing: .12em; text-transform: uppercase; }
.ai-trace__count { margin-left: auto; color: var(--ds-color-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.ai-trace__list { position: relative; display: grid; gap: 10px; margin: 0; padding: 4px 12px 12px 26px; list-style: none; }
.ai-trace__list::before { content: ''; position: absolute; left: 17px; top: 8px; bottom: 16px; width: 1px; background: var(--ds-color-border-strong); }
.ai-trace__step { position: relative; display: grid; gap: 2px; }
.ai-trace__marker { position: absolute; left: -13px; top: 5px; width: 7px; height: 7px; border-radius: 50%; border: 1px solid var(--ds-color-border-strong); background: var(--ds-surface-raised); }
.ai-trace__step.is-done .ai-trace__marker { border-color: var(--ds-semantic-success); background: var(--ds-semantic-success); }
.ai-trace__step.is-active .ai-trace__marker { border-color: var(--ds-semantic-info); background: var(--ds-semantic-info); animation: chat-pulse 1.2s infinite ease-in-out; }
.ai-trace__row { display: flex; align-items: center; gap: 6px; min-width: 0; }
.ai-trace__row strong { color: var(--ds-color-text); font-size: 12px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-trace__body p { margin: 2px 0 0; color: var(--ds-color-muted); font-size: 11px; line-height: 1.55; overflow-wrap: anywhere; }
.ai-cursor { display: inline-block; width: 6px; height: 1em; margin-left: 2px; vertical-align: text-bottom; background: var(--smart-primary-strong); animation: chat-blink 1s steps(2, start) infinite; }
@keyframes chat-blink { to { visibility: hidden; } }
.ai-chat-rag-debug { border-top: 1px solid var(--smart-border); padding: 8px 13px 10px; font-size: 11px; color: var(--smart-muted); }
.ai-chat-rag-debug summary { cursor: pointer; user-select: none; padding: 2px 0 8px; font: 10px var(--font-mono); letter-spacing: .14em; color: var(--smart-primary-strong); }
.ai-chat-rag-debug summary::-webkit-details-marker { display: none; }
.ai-chat-rag-debug summary::before { content: '+ '; }
.ai-chat-rag-debug[open] summary::before { content: '− '; }
.rag-debug-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 18px; }
.rag-debug-item { display: grid; gap: 4px; }
.rag-debug-item span { display: flex; justify-content: space-between; font: 10px var(--font-mono); letter-spacing: .08em; }
.rag-debug-item em { font-style: normal; color: var(--smart-primary-strong); }
.rag-debug-item input[type="range"] { width: 100%; accent-color: var(--smart-primary-strong); }
.rag-debug-item--source { grid-column: 1 / -1; }
.rag-debug-item--source input[type="text"] { width: 100%; padding: 5px 8px; border: 1px solid var(--smart-border); border-radius: 6px; background: var(--smart-surface); color: var(--smart-text); font: 12px var(--font-mono); }
.rag-debug-reset { margin-top: 8px; padding: 3px 9px; border: 1px solid var(--smart-border); border-radius: 6px; background: transparent; color: var(--smart-muted); cursor: pointer; font: 10px var(--font-mono); letter-spacing: .06em; }
.rag-debug-reset:hover { color: var(--smart-text); border-color: var(--smart-border-strong); }
@media (max-width: 600px) { .ai-chat-message { max-width: 94%; }.ai-chat-empty { align-items: flex-start; }.ai-chat-quick-actions { gap: 6px; }.ai-chat-quick-actions button { flex: 1 1 140px; }.rag-debug-grid { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { .ai-chat-pending span, .is-loading, .ai-chat-icon-button.is-recording svg, .ai-trace__step.is-active .ai-trace__marker { animation: none; } }
</style>
