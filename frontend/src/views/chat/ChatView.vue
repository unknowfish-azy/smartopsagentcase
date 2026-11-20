<template>
  <div class="chat-page" :class="{ 'chat-page--agent': chatMode === 'agent' }">
    <div v-if="!mobile" class="chat-page__sidebar"><ChatHistory /></div>
    <section class="chat-page__main" aria-label="当前会话">
      <header class="chat-page__header">
        <button v-if="mobile" ref="historyTrigger" type="button" class="chat-page__history-toggle" aria-label="打开历史会话" :aria-expanded="historyOpen" @click="historyOpen = true"><Operation :size="18" aria-hidden="true" /></button>
        <div class="chat-page__title">
          <p class="eyebrow">AI CONVERSATION</p>
          <h1>{{ activeConversation?.title || 'AI 对话' }}</h1>
        </div>

        <!-- 模式分段控件：Chat 聊天 / Agent 智能体 -->
        <div class="chat-mode-switch" role="tablist" aria-label="对话模式切换">
          <button type="button" role="tab" :aria-selected="chatMode === 'chat'" class="chat-mode-switch__btn" :data-active="chatMode === 'chat'" @click="chatMode = 'chat'">
            <ChatDotRound :size="13" /> 聊天
          </button>
          <button type="button" role="tab" :aria-selected="chatMode === 'agent'" class="chat-mode-switch__btn" :data-active="chatMode === 'agent'" @click="chatMode = 'agent'">
            <Promotion :size="13" /> 智能体
          </button>
        </div>

        <span class="chat-page__badge">
          <template v-if="chatMode === 'agent'">
            <span class="badge-pulse" aria-hidden="true"></span> 已接管后台
          </template>
          <template v-else>{{ sending ? '正在回复…' : '智维 Agent' }}</template>
        </span>
        <XiaoyuChatAvatar :mode="chatMode" />
      </header>

      <!-- Agent 模式下的接管状态条 -->
      <div v-if="chatMode === 'agent'" class="chat-page__agent-bar" role="status">
        <span class="agent-bar__dot"></span>
        <span>智能体已接管后台，可执行巡检 / 诊断 / 变更操作</span>
        <span class="agent-bar__lock" title="加锁资源不会被修改">
          <Lock :size="12" /> 加锁资源只读
        </span>
      </div>

      <p v-if="storageWarning" class="chat-page__warning" role="alert">{{ storageWarning }}</p>
      <p v-if="remoteError" class="chat-page__warning" role="alert">{{ remoteError }} <button type="button" @click="retryAttachments">重试附件历史</button></p>
      <AiChatPanel class="chat-page__conversation" :agent-mode="chatMode === 'agent'" compact />
      <p class="chat-page__disclaimer">
        <template v-if="chatMode === 'agent'">Agent 模式会按指令执行真实运维操作，敏感环境请先在演练区验证。</template>
        <template v-else>AI 回答仅供参考，执行运维操作前请核对环境与风险。</template>
      </p>
    </section>
    <el-drawer v-model="historyOpen" append-to-body title="历史会话" direction="ltr" size="min(320px, calc(100vw - 24px))" class="chat-history-drawer" @closed="historyTrigger?.focus()">
      <ChatHistory v-if="mobile && historyOpen" @selected="historyOpen = false" />
    </el-drawer>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { Operation, ChatDotRound, Promotion, Lock } from '@element-plus/icons-vue'
import AiChatPanel from '../../components/ai/AiChatPanel.vue'
import ChatHistory from '../../components/ai/ChatHistory.vue'
import XiaoyuChatAvatar from '../../components/chat/XiaoyuChatAvatar.vue'
import { useAiChatStore } from '../../stores/aiChat.js'
import { useVoiceActionBus } from '../../components/persona/voiceActionRegistry.js'

const chatMode = ref('chat') // 'chat' | 'agent'

const store = useAiChatStore()
store.syncAccount()
const { activeConversation, sending, storageWarning, remoteError, accountEpoch } = storeToRefs(store)
watch(accountEpoch, () => store.loadRemoteConversations(), { immediate: true })
async function retryAttachments() { await store.loadRemoteConversations(); if (activeConversation.value?.backed) await store.loadRemoteDetail(activeConversation.value.id) }

// 语音控屏：找最后一条 AI 回复来复制
async function copyLastReply() {
  const messages = store.activeConversation?.messages ?? []
  const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant' && !m.pending)
  if (!lastAssistant?.content) return
  try { await navigator.clipboard.writeText(lastAssistant.content) } catch { /* 剪贴板不可用 */ }
}

const viewport = window.matchMedia('(max-width: 1023px)')
const mobile = ref(viewport.matches)
const historyOpen = ref(false)
const historyTrigger = ref(null)
function updateViewport(event) {
  mobile.value = event.matches
  if (!event.matches) historyOpen.value = false
}
viewport.addEventListener('change', updateViewport)

onMounted(() => {
  // 语音控屏：注册 Chat 页面的按钮级意图 handler
  const bus = useVoiceActionBus()
  _voiceUnregister = [
    bus.register('chat.clear', () => store.clearConversation()),
    bus.register('chat.copy', () => copyLastReply()),
  ]
})
onBeforeUnmount(() => {
  viewport.removeEventListener('change', updateViewport)
  if (_voiceUnregister) _voiceUnregister.forEach(fn => fn())
})
let _voiceUnregister = null
</script>

<style scoped>
/* 聊天容器撑满父级：不再硬卡 560px 或 1440px，让 main-content 的 flex 链自然延伸 */
.chat-page { display: grid; grid-template-columns: 260px minmax(0, 1fr); height: 100%; min-height: 0; overflow: hidden; background: var(--smart-bg); color: var(--smart-text); }
.chat-page__sidebar { min-height: 0; border-right: 1px solid var(--smart-border-strong); overflow-y: auto; }
.chat-page__main { display: flex; flex-direction: column; min-width: 0; min-height: 0; padding: 6px 18px 4px; }
.chat-page__header { display: flex; align-items: center; gap: 10px; padding-bottom: 6px; border-bottom: 1px solid var(--smart-border); flex-wrap: wrap; }
.chat-page__header > div { min-width: 0; }
.chat-page__title { min-width: 0; }
.chat-page__header .eyebrow { margin: 0 0 3px; color: var(--smart-muted); font-size: 9px; letter-spacing: .08em; }
.chat-page__header h1 { margin: 0; font-size: 16px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-page__badge { margin-left: auto; white-space: nowrap; color: var(--smart-primary-strong); font-size: 11px; display: inline-flex; align-items: center; gap: 6px; }
.badge-pulse { width: 6px; height: 6px; border-radius: 50%; background: var(--smart-primary-strong); animation: agent-badge-pulse 1.6s ease-in-out infinite; }
@keyframes agent-badge-pulse { 0%, 100% { opacity: .45; transform: scale(.85); } 50% { opacity: 1; transform: scale(1.15); } }

.chat-page__history-toggle { display: grid; place-items: center; flex: 0 0 44px; height: 44px; border: 1px solid var(--smart-border-strong); border-radius: 8px; background: var(--smart-surface); color: var(--smart-text); cursor: pointer; }
.chat-page__history-toggle:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.chat-page__history-toggle svg { width: 18px; height: 18px; }

/* ===== 模式分段控件 ===== */
.chat-mode-switch { display: inline-flex; align-items: center; padding: 2px; border: 1px solid var(--smart-border-strong); border-radius: 8px; background: var(--smart-surface); gap: 2px; }
.chat-mode-switch__btn { display: inline-flex; align-items: center; gap: 4px; min-height: 26px; padding: 0 10px; border: 0; border-radius: 6px; background: transparent; color: var(--smart-muted); font: 10.5px var(--font-cn); cursor: pointer; transition: color .15s, background-color .15s; white-space: nowrap; }
.chat-mode-switch__btn svg { flex: 0 0 13px; }
.chat-mode-switch__btn:hover { color: var(--smart-text); }
.chat-mode-switch__btn[data-active='true'] {
  background: var(--smart-primary);
  color: var(--smart-primary-foreground, #041018);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--smart-primary) 35%, transparent);
}
.chat-mode-switch__btn:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }

/* ===== Agent 模式接管状态条 ===== */
.chat-page__agent-bar { display: flex; align-items: center; gap: 8px; margin-top: 8px; padding: 6px 12px; border: 1px solid color-mix(in srgb, var(--smart-primary) 40%, var(--smart-border)); border-radius: 8px; background: color-mix(in srgb, var(--smart-primary) 10%, var(--smart-surface)); color: var(--smart-text); font-size: 11px; }
.agent-bar__dot { flex: 0 0 7px; width: 7px; height: 7px; border-radius: 50%; background: var(--smart-primary-strong); box-shadow: 0 0 0 3px color-mix(in srgb, var(--smart-primary-strong) 30%, transparent); animation: agent-badge-pulse 1.8s ease-in-out infinite; }
.agent-bar__lock { margin-left: auto; display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border: 1px dashed var(--smart-border-strong); border-radius: 5px; color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .05em; }

.chat-page__warning { color: var(--smart-danger); font-size: 12px; line-height: 1.6; }
.chat-page__conversation { display: flex; flex: 1; flex-direction: column; min-height: 0; padding-top: 4px; }
.chat-page__conversation :deep(.ai-chat-messages) { flex: 1; min-height: 0; max-height: none; align-content: start; padding: 4px 4px 12px; }
.chat-page__conversation :deep(.ai-chat-empty) { flex: 1; justify-content: center; padding-bottom: 24px; }
.chat-page__conversation :deep(.ai-chat-composer) { flex-shrink: 0; }
.chat-page__disclaimer { display: none; }

/* Agent 模式下给对话区一个微妙的主色强调边 */
.chat-page--agent .chat-page__conversation :deep(.ai-chat-composer) { border-color: color-mix(in srgb, var(--smart-primary) 55%, var(--smart-border-strong)); }
.chat-page--agent .chat-page__conversation :deep(.ai-chat-message--assistant) { border-color: color-mix(in srgb, var(--smart-primary) 30%, var(--smart-border)); }

:global(.chat-history-drawer) { background: var(--smart-surface); color: var(--smart-text); }
:global(.chat-history-drawer .el-drawer__body) { padding: 0; overflow: hidden; }
:global(.chat-history-drawer .el-drawer__header) { margin-bottom: 0; color: var(--smart-text); }

@media (max-width: 1100px) { .chat-page { grid-template-columns: 220px minmax(0, 1fr); } .chat-page__main { padding: 16px 18px 10px; } }
@media (max-width: 1023px) {
  .chat-page { grid-template-columns: minmax(0, 1fr); height: 100%; }
  .chat-page__main { padding: 14px 12px 10px; }
  .chat-page__header { gap: 10px; padding-bottom: 12px; }
  .chat-page__header h1 { font-size: 16px; }
  .chat-page__badge { display: none; }
  .chat-mode-switch__btn { padding: 0 9px; font-size: 10.5px; }
  .chat-page__conversation :deep(textarea) { font-size: 16px; }
}
@media (max-width: 560px) {
  .chat-mode-switch { order: 3; flex-basis: 100%; justify-content: center; }
  .agent-bar__lock { display: none; }
}
</style>
