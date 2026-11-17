<template>
  <section class="persona-view">
    <header class="persona-view__head">
      <p class="persona-view__eyebrow">AGENT PERSONA / 小鱼 · 3D 化身</p>
      <h1 class="persona-view__title">小鱼</h1>
      <p class="persona-view__desc">
        继鲸（基础设施）、蛛（集群）、水母（Agent 觉察）之后的第四个生命体：Agent 的人格化身。
        她与控制台共用同一个 Agent 大脑——同一模型、同一知识库检索、同一份对话记忆。
        这里的提问走真实对话链路，说话时驱动口型与状态机，但不进入执行闭环，不代为执行任何变更。
      </p>
    </header>

    <div class="persona-view__stage">
      <AgentPersona
        ref="personaRef"
        :state="personaState"
        @ready="onReady"
        @error="onError"
        @context-lost="onLost"
      />
    </div>

    <section class="persona-view__chat" aria-label="与 Agent 对话">
      <div class="persona-view__chat-head">
        <p class="persona-view__states-label">与 Agent 对话</p>
        <span class="persona-view__pill" :data-tone="chatTone">{{ CHAT_PHASE_LABELS[phase] }}</span>
      </div>

      <ol v-if="messages.length" class="persona-view__messages">
        <li
          v-for="message in messages"
          :key="message.id"
          class="persona-view__message"
          :class="[`is-${message.role}`, { 'is-error': message.error }]"
        >
          <p class="persona-view__message-role">
            {{ message.role === 'user' ? '你' : '小鱼' }}
            <span v-if="message.citations" class="persona-view__message-meta">
              引用 {{ message.citations }} 条证据
            </span>
          </p>
          <p class="persona-view__message-body">{{ message.content || '…' }}</p>
        </li>
      </ol>
      <p v-else class="persona-view__note">
        问一句运维问题试试，比如「nginx 502 怎么排查？」。回答会逐字显示，同时驱动口型。
      </p>

      <form class="persona-view__composer" @submit.prevent="sendMessage">
        <label class="persona-view__composer-label" for="persona-chat-input">输入问题</label>
        <textarea
          id="persona-chat-input"
          v-model="draft"
          class="persona-view__composer-input"
          rows="2"
          maxlength="2000"
          :disabled="busy"
          placeholder="例如：nginx 502 怎么排查？"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <p v-if="notice" class="persona-view__notice" role="alert">{{ notice }}</p>
        <div class="persona-view__composer-actions">
          <button type="submit" class="persona-view__state-button" :disabled="busy || !draft.trim()">
            发送
          </button>
          <button type="button" class="persona-view__state-button" :disabled="!busy" @click="stopReply">
            停止
          </button>
        </div>
      </form>

      <p class="persona-view__note">
        口型按流式文字近似推进（<strong>不是音频同步</strong>），说完即闭嘴；
        空输入与超长输入在本地拦下，不发请求。
      </p>
    </section>

    <dl class="persona-view__stats">
      <div class="persona-view__stat">
        <dt>渲染状态</dt>
        <dd><span class="persona-view__pill" :data-tone="statusTone">{{ statusText }}</span></dd>
      </div>
      <div class="persona-view__stat">
        <dt>会话状态</dt>
        <dd>{{ CHAT_PHASE_LABELS[phase] }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>Draw call</dt>
        <dd>{{ stats?.drawCalls ?? '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>几何 / 贴图</dt>
        <dd>{{ stats ? `${stats.geometries} / ${stats.textures}` : '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>帧时（P50 / P90）</dt>
        <dd>{{ stats ? `${stats.frameP50Ms} / ${stats.frameP90Ms} ms` : '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>首帧</dt>
        <dd>{{ stats ? `${stats.firstFrameMs} ms` : '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>模型传输</dt>
        <dd>{{ stats?.modelBytes ? `${(stats.modelBytes / 1048576).toFixed(1)} MB` : '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>JS 堆</dt>
        <dd>{{ stats?.heapMB ? `${stats.heapMB} MB` : '不可读' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>像素比</dt>
        <dd>{{ stats?.pixelRatio ?? '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>降级</dt>
        <dd>{{ stats?.degraded ? '已降级（慢帧持续 2s）' : '正常' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>状态通道</dt>
        <dd>文本 + 色彩（非仅 3D）</dd>
      </div>
    </dl>

    <p class="persona-view__note">
      占位模型：Sendagaya Shino（CC0，VRoid 官方示例）。许可与出处见
      <code>/avatar/sendagaya-shino/model.LICENSE.txt</code> 与 <code>model.SOURCE.txt</code>。
      该模型 15MB / 17 材质，超出正式预算，仅用于打通链路，不作为性能基线。
    </p>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import AgentPersona from '../../components/persona/AgentPersona.vue'
import {
  CHAT_PHASE_LABELS,
  createSpeechPump,
  normalizeChatMessage,
  personaStateForChat
} from '../../components/persona/personaChat.js'
import { fetchChatRunToken } from '../../api/chatRunToken.ts'
import { streamChat } from '../../api/stream.ts'

// phase: idle | connecting | streaming | error（错误保持到下一次发送，便于看清失败）
const phase = ref('idle')
const draft = ref('')
const messages = ref([])
const notice = ref('')
const status = ref('loading')
const stats = ref(null)
const errorMessage = ref('')
const personaRef = ref(null)

let statsTimer = 0
let controller = null

const busy = computed(() => phase.value === 'connecting' || phase.value === 'streaming')
const personaState = computed(() => personaStateForChat(phase.value, { renderStatus: status.value }))
const chatTone = computed(() => {
  if (phase.value === 'error') return 'danger'
  if (phase.value === 'connecting') return 'warning'
  if (phase.value === 'streaming') return 'success'
  return 'neutral'
})

const statusText = computed(() => {
  if (status.value === 'ready') return '加载完成'
  if (status.value === 'error') return `加载失败：${errorMessage.value}`
  if (status.value === 'lost') return '上下文丢失，已降级'
  return '加载中'
})

const statusTone = computed(() => {
  if (status.value === 'ready') return 'success'
  if (status.value === 'error') return 'danger'
  if (status.value === 'lost') return 'warning'
  return 'neutral'
})

const speechPump = createSpeechPump({
  speakText: (text, options) => personaRef.value?.speakText?.(text, options),
  seekSpeech: (index) => personaRef.value?.seekSpeech?.(index),
  stopSpeaking: () => personaRef.value?.stopSpeaking?.()
})

function onReady(payload) {
  status.value = 'ready'
  stats.value = payload
  startStatsPolling()
}

function onError(error) {
  stopStatsPolling()
  status.value = 'error'
  errorMessage.value = error?.message ?? '未知错误'
}

function onLost() {
  stopStatsPolling()
  status.value = 'lost'
}

/** 每秒拉一次遥测：帧时 / 降级是持续变化的，只在 ready 时取一次会失真 */
function startStatsPolling() {
  stopStatsPolling()
  statsTimer = setInterval(() => {
    const snapshot = personaRef.value?.readStats?.()
    if (snapshot) stats.value = snapshot
  }, 1000)
}

function stopStatsPolling() {
  if (statsTimer) clearInterval(statsTimer)
  statsTimer = 0
}

const unwrap = (value) => value?.data ?? value

async function sendMessage() {
  if (busy.value) return
  const checked = normalizeChatMessage(draft.value)
  notice.value = ''
  if (!checked.ok) {
    notice.value = checked.reason === 'too-long' ? '消息不能超过 2000 字符。' : '先输入一个问题再发送。'
    return
  }

  // 用 reactive 包住助手消息：流式增量要逐字触发更新，直接改 push 进去的
  // 原始对象不会让 Vue 的代理感知。
  const reply = reactive({ id: crypto.randomUUID(), role: 'assistant', content: '' })
  messages.value.push(
    { id: crypto.randomUUID(), role: 'user', content: checked.text },
    reply
  )
  draft.value = ''
  phase.value = 'connecting'
  controller = new AbortController()
  let text = ''

  try {
    // 与控制台同一条链路：Java 签发短时 run 令牌，ai-service 只信令牌主体。
    const issued = unwrap(await fetchChatRunToken())
    if (typeof issued?.runToken !== 'string' || !issued.runToken) {
      throw new Error('聊天鉴权令牌签发失败，请刷新页面后重试。')
    }
    await streamChat(checked.text, {
      signal: controller.signal,
      onToken: (delta) => {
        if (!delta) return
        text += delta
        reply.content = text
        if (phase.value !== 'streaming') phase.value = 'streaming'
        // 边收边推进口型：重建时间线后跳到已播位置，避免每个 token 都从头动嘴。
        speechPump.push(text)
      },
      onDone: (payload) => {
        // 部分后端不逐 token，done 里带一次性完整答案；取更长的一份，不以空 delta 覆盖。
        if (typeof payload?.answer === 'string' && payload.answer.length > text.length) {
          text = payload.answer
          reply.content = text
        }
        reply.citations = Array.isArray(payload?.citations) ? payload.citations.length : 0
        phase.value = 'idle'
      }
    }, {
      runToken: issued.runToken,
      correlation: { request_id: crypto.randomUUID(), task_id: crypto.randomUUID() },
      context: { path: window.location.pathname, section: 'AGENT PERSONA / 人格化身' }
    })
  } catch (error) {
    if (error?.name === 'AbortError') {
      reply.content = text || '已停止。'
      phase.value = 'idle'
    } else {
      reply.error = true
      reply.content = [text, error?.message || '暂时无法连接 AI 服务，请确认 ai-service 已启动。']
        .filter(Boolean)
        .join('\n\n')
      phase.value = 'error'
    }
    speechPump.stop()
  } finally {
    controller = null
  }
}

function stopReply() {
  controller?.abort()
}

onBeforeUnmount(() => {
  stopStatsPolling()
  controller?.abort()
  speechPump.stop()
})
</script>

<style scoped>
.persona-view {
  display: grid;
  gap: var(--ds-space-6);
  max-width: 720px;
  margin: 0 auto;
  padding: var(--ds-space-8) var(--ds-space-4);
}

.persona-view__head {
  display: grid;
  gap: var(--ds-space-2);
}

.persona-view__eyebrow {
  margin: 0;
  font-size: var(--ds-type-overline-size);
  font-weight: var(--ds-type-overline-weight);
  letter-spacing: .18em;
  color: var(--ds-color-primary-strong);
}

.persona-view__title {
  margin: 0;
  font-size: var(--ds-type-h1-size);
  font-weight: var(--ds-type-h1-weight);
  color: var(--ds-color-text);
}

.persona-view__desc {
  margin: 0;
  font-size: var(--ds-type-body-size);
  line-height: var(--ds-line-height-base);
  color: var(--ds-color-muted);
}

.persona-view__chat {
  display: grid;
  gap: var(--ds-space-2);
}

.persona-view__chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-2);
}

.persona-view__states-label {
  margin: 0;
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
}

.persona-view__messages {
  display: grid;
  gap: var(--ds-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 320px;
  overflow-y: auto;
}

.persona-view__message {
  display: grid;
  gap: 2px;
  padding: var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-card);
}

.persona-view__message.is-user {
  border-color: var(--ds-color-border-strong);
}

.persona-view__message.is-error {
  border-color: color-mix(in srgb, var(--smart-danger) 45%, transparent);
}

.persona-view__message-role {
  margin: 0;
  display: flex;
  align-items: baseline;
  gap: var(--ds-space-2);
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
}

.persona-view__message-meta {
  font-size: 11px;
  color: var(--ds-color-primary-strong);
}

.persona-view__message-body {
  margin: 0;
  font-size: var(--ds-type-body-size);
  line-height: var(--ds-line-height-base);
  color: var(--ds-color-text);
  white-space: pre-wrap;
  word-break: break-word;
}

.persona-view__composer {
  display: grid;
  gap: var(--ds-space-2);
}

.persona-view__composer-label {
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
}

.persona-view__composer-input {
  width: 100%;
  padding: var(--ds-space-2) var(--ds-space-3);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-card);
  color: var(--ds-color-text);
  font: inherit;
  line-height: var(--ds-line-height-base);
  resize: vertical;
}

.persona-view__composer-input:disabled {
  opacity: .6;
  cursor: not-allowed;
}

.persona-view__composer-actions {
  display: flex;
  gap: var(--ds-space-2);
}

.persona-view__notice {
  margin: 0;
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-danger);
}

.persona-view__state-button {
  padding: var(--ds-space-1) var(--ds-space-3);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-pill);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: var(--ds-type-caption-size);
  cursor: pointer;
  transition: color .18s ease, border-color .18s ease;
}

.persona-view__state-button:hover:not(:disabled) {
  color: var(--ds-color-text);
}

.persona-view__state-button:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.persona-view__state-button.is-active {
  color: var(--ds-color-primary-strong);
  border-color: var(--ds-color-primary-strong);
}

.persona-view__stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--ds-space-3);
  margin: 0;
  padding: var(--ds-space-4);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-card);
}

.persona-view__stat dt {
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
}

.persona-view__stat dd {
  margin: var(--ds-space-1) 0 0;
  font-size: var(--ds-font-md);
  color: var(--ds-color-text);
  font-variant-numeric: var(--ds-type-num);
}

.persona-view__pill {
  display: inline-block;
  padding: 2px var(--ds-space-2);
  border-radius: var(--ds-radius-pill);
  font-size: var(--ds-type-caption-size);
  border: 1px solid var(--ds-color-border-strong);
  color: var(--ds-color-muted);
}

.persona-view__pill[data-tone='success'] {
  color: var(--ds-color-success);
  border-color: color-mix(in srgb, var(--smart-success) 45%, transparent);
}

.persona-view__pill[data-tone='warning'] {
  color: var(--ds-color-warning);
  border-color: color-mix(in srgb, var(--smart-warning) 45%, transparent);
}

.persona-view__pill[data-tone='danger'] {
  color: var(--ds-color-danger);
  border-color: color-mix(in srgb, var(--smart-danger) 45%, transparent);
}

.persona-view__note {
  margin: 0;
  font-size: var(--ds-type-caption-size);
  line-height: var(--ds-line-height-base);
  color: var(--ds-color-muted);
}

.persona-view__note code {
  font-size: 12px;
  color: var(--ds-color-primary-strong);
}
</style>
