<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div v-if="open" class="assistant-root" role="dialog" aria-modal="true" aria-labelledby="assistant-title">
        <div class="assistant-backdrop" @click="emit('close')"></div>
        <aside class="assistant">
          <header class="assistant-head">
            <div>
              <p class="assistant-eyebrow">PLATFORM ASSISTANT · 只读建议</p>
              <h3 id="assistant-title">巡检平台助手</h3>
            </div>
            <div class="assistant-head-actions">
              <button type="button" class="icon-btn" title="清空会话" @click="reset">清空</button>
              <button type="button" class="icon-btn" title="关闭" @click="emit('close')">×</button>
            </div>
          </header>

          <div class="assistant-context">
            <span class="context-label">当前上下文</span>
            <p>{{ contextSummary || '尚未选择设备' }}</p>
          </div>

          <div ref="scrollEl" class="assistant-thread">
            <div v-if="!messages.length" class="assistant-welcome">
              <p>我会结合当前设备遥测、任务与预警给出排查建议，不会直接下发控制指令。</p>
              <div class="quick-list">
                <button v-for="item in QUICK_PROMPTS" :key="item" type="button" class="quick-btn" @click="ask(item)">
                  {{ item }}
                </button>
              </div>
            </div>
            <article
              v-for="(message, index) in messages"
              :key="index"
              class="message"
              :class="[message.role, { error: message.error }]"
            >
              <span class="message-role">{{ message.role === 'user' ? '我' : '助手' }}</span>
              <p class="message-text">{{ message.content }}</p>
              <AssistantRetrievalChain
                v-if="message.role === 'assistant' && message.citations?.length"
                :stages="chainStages(message)"
                hint="本地知识库"
              />
            </article>
          </div>

          <div class="assistant-input">
            <textarea
              v-model="draft"
              rows="3"
              maxlength="500"
              placeholder="例如：电量 18% 还能执行当前路线吗？"
              @keydown.enter.exact.prevent="send()"
            ></textarea>
            <div class="input-actions">
              <router-link to="/log-diagnosis" class="diag-link" @click="emit('close')">打开日志诊断 →</router-link>
              <button type="button" class="send-btn" :disabled="!canSend" @click="send">
                {{ sending ? '思考中…' : '发送' }}
              </button>
            </div>
          </div>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { sendAssistantChat } from '../../api/assistant.ts'
import AssistantRetrievalChain from '../ai/AssistantRetrievalChain.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  contextSummary: { type: String, default: '' },
  contextPayload: { type: String, default: '' },
  deviceName: { type: String, default: '' }
})

const emit = defineEmits(['close'])

const QUICK_PROMPTS = [
  '当前设备状态是否正常？',
  '给出下一步操作建议',
  '解释最近一次预警',
  '任务失败应该怎么排查？'
]

const messages = ref([])
const draft = ref('')
const sending = ref(false)
const scrollEl = ref(null)

const canSend = computed(() => draft.value.trim().length > 0 && !sending.value)

function scrollToEnd() {
  nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  })
}

watch(() => props.open, (value) => {
  if (value) scrollToEnd()
})

function reset() {
  messages.value = []
  draft.value = ''
}

function ask(question) {
  draft.value = question
  send()
}

function buildHistory() {
  return messages.value
    .filter(message => !message.error && !message.pending)
    .slice(-6)
    .map(message => ({ role: message.role, content: message.content.slice(0, 1200) }))
}

// 链路阶段全部来自后端真实返回：引用段数、来源篇数与模型名，没有就退化为 0。
function chainStages(message) {
  const citations = Array.isArray(message.citations) ? message.citations : []
  const sources = new Set(
    citations.map(item => item?.source || item?.title).filter(value => typeof value === 'string' && value.trim())
  )
  return [
    { key: 'recall', label: '本地召回', value: `${citations.length} 段`, note: '内建知识索引' },
    { key: 'source', label: '来源', value: `${sources.size} 篇`, note: '可追溯引用' },
    { key: 'model', label: '生成', value: message.model || '智维 Mini', note: '只读建议' }
  ]
}

async function send() {
  const question = draft.value.trim()
  if (!question || sending.value) return
  draft.value = ''
  messages.value.push({ role: 'user', content: question })
  const pending = { role: 'assistant', content: '正在结合当前遥测分析…', pending: true }
  messages.value.push(pending)
  scrollToEnd()
  sending.value = true
  try {
    const context = (props.contextPayload || '').slice(0, 1400)
    const composed = context
      ? `以下是巡检控制台的真实上下文（只读，不可编造）：\n${context}\n\n问题：${question}`
      : question
    const history = buildHistory()
    const response = await sendAssistantChat({ providerKey: 'mini', message: composed, history })
    const data = response?.data ?? response ?? {}
    const content = data.content
    if (typeof content !== 'string' || !content.trim()) {
      throw new Error('助手已响应，但没有返回可显示的内容')
    }
    pending.content = content.trim()
    pending.model = typeof data.model === 'string' ? data.model : ''
    pending.citations = Array.isArray(data.citations) ? data.citations : []
    pending.pending = false
  } catch (error) {
    pending.pending = false
    pending.error = true
    pending.content = error?.message || '暂时无法连接助手，请稍后重试'
  } finally {
    sending.value = false
    scrollToEnd()
  }
}
</script>

<style scoped>
.assistant-root {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  justify-content: flex-end;
}

.assistant-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(3, 8, 14, 0.55);
  backdrop-filter: blur(2px);
}

.assistant {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(430px, 92vw);
  height: 100%;
  border-left: 1px solid var(--ds-color-border);
  background: var(--ds-color-surface);
  box-shadow: -18px 0 40px rgba(0, 0, 0, 0.35);
}

.assistant-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ds-space-2);
  padding: var(--ds-space-4);
  border-bottom: 1px solid var(--ds-color-border);
}

.assistant-eyebrow {
  margin: 0 0 2px;
  color: var(--ds-color-muted);
  font-size: 10px;
  letter-spacing: 0.12em;
}

.assistant-head h3 {
  margin: 0;
  font-size: var(--ds-font-md);
}

.assistant-head-actions {
  display: flex;
  gap: 4px;
}

.icon-btn {
  min-width: 26px;
  height: 26px;
  padding: 0 8px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-sm);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  cursor: pointer;
}

.icon-btn:hover {
  border-color: var(--ds-color-primary);
  color: var(--ds-color-text);
}

.assistant-context {
  padding: 10px var(--ds-space-4);
  border-bottom: 1px solid var(--ds-color-border);
  background: var(--ds-color-surface-raised);
}

.context-label {
  color: var(--ds-color-muted);
  font-size: 10px;
  letter-spacing: 0.08em;
}

.assistant-context p {
  margin: 3px 0 0;
  color: var(--ds-color-text);
  font-size: var(--ds-font-xs);
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.assistant-thread {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: var(--ds-space-4);
  overflow-y: auto;
}

.assistant-welcome {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-3);
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  line-height: 1.7;
}

.assistant-welcome p {
  margin: 0;
}

.quick-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.quick-btn {
  padding: 8px 10px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-size: var(--ds-font-xs);
  text-align: left;
  cursor: pointer;
}

.quick-btn:hover {
  border-color: var(--ds-color-primary);
}

.message {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-width: 92%;
}

.message.user {
  align-self: flex-end;
  align-items: flex-end;
}

.message.assistant {
  align-self: flex-start;
}

.message-role {
  color: var(--ds-color-muted);
  font-size: 9px;
}

.message-text {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-size: var(--ds-font-xs);
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.message.user .message-text {
  border-color: rgba(36, 150, 237, 0.35);
  background: rgba(36, 150, 237, 0.12);
}

.message.error .message-text {
  border-color: rgba(224, 100, 110, 0.4);
  color: #ff9aa4;
}

.assistant-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--ds-space-3) var(--ds-space-4) var(--ds-space-4);
  border-top: 1px solid var(--ds-color-border);
}

.assistant-input textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-family: inherit;
  font-size: var(--ds-font-xs);
  line-height: 1.6;
  resize: vertical;
}

.assistant-input textarea:focus {
  outline: none;
  border-color: var(--ds-color-primary);
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-2);
}

.diag-link {
  color: var(--ds-color-primary);
  font-size: 10px;
  text-decoration: none;
}

.send-btn {
  padding: 7px 18px;
  border: 0;
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-primary);
  color: #04121e;
  font-size: var(--ds-font-xs);
  font-weight: 600;
  cursor: pointer;
}

.send-btn:disabled {
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-muted);
  cursor: not-allowed;
}

.drawer-enter-active,
.drawer-leave-active {
  transition: opacity var(--ds-duration-base) ease;
}

.drawer-enter-active .assistant,
.drawer-leave-active .assistant {
  transition: transform var(--ds-duration-base) ease;
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}

.drawer-enter-from .assistant,
.drawer-leave-to .assistant {
  transform: translateX(24px);
}
</style>
