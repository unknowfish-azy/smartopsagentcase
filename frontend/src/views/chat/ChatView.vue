<template>
  <div class="chat-page">
    <div v-if="!mobile" class="chat-page__sidebar"><ChatHistory /></div>
    <section class="chat-page__main" aria-label="当前会话">
      <header class="chat-page__header">
        <button v-if="mobile" ref="historyTrigger" type="button" class="chat-page__history-toggle" aria-label="打开历史会话" :aria-expanded="historyOpen" @click="historyOpen = true"><Operation :size="18" aria-hidden="true" /></button>
        <div><p class="eyebrow">AI CONVERSATION</p><h1>{{ activeConversation?.title || 'AI 对话' }}</h1></div>
        <span class="chat-page__badge">{{ sending ? '正在回复…' : '智维 Agent' }}</span>
        <XiaoyuChatAvatar />
      </header>
      <p v-if="storageWarning" class="chat-page__warning" role="alert">{{ storageWarning }}</p>
      <p v-if="remoteError" class="chat-page__warning" role="alert">{{ remoteError }} <button type="button" @click="retryAttachments">重试附件历史</button></p>
      <AiChatPanel class="chat-page__conversation" />
      <p class="chat-page__disclaimer">AI 回答仅供参考，执行运维操作前请核对环境与风险。</p>
    </section>
    <el-drawer v-model="historyOpen" append-to-body title="历史会话" direction="ltr" size="min(320px, calc(100vw - 24px))" class="chat-history-drawer" @closed="historyTrigger?.focus()">
      <ChatHistory v-if="mobile && historyOpen" @selected="historyOpen = false" />
    </el-drawer>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { Operation } from '@element-plus/icons-vue'
import AiChatPanel from '../../components/ai/AiChatPanel.vue'
import ChatHistory from '../../components/ai/ChatHistory.vue'
import XiaoyuChatAvatar from '../../components/chat/XiaoyuChatAvatar.vue'
import { useAiChatStore } from '../../stores/aiChat.js'

const store = useAiChatStore()
store.syncAccount()
const { activeConversation, sending, storageWarning, remoteError, accountEpoch } = storeToRefs(store)
watch(accountEpoch, () => store.loadRemoteConversations(), { immediate: true })
async function retryAttachments() { await store.loadRemoteConversations(); if (activeConversation.value?.backed) await store.loadRemoteDetail(activeConversation.value.id) }
const viewport = window.matchMedia('(max-width: 1023px)')
const mobile = ref(viewport.matches)
const historyOpen = ref(false)
const historyTrigger = ref(null)
function updateViewport(event) {
  mobile.value = event.matches
  if (!event.matches) historyOpen.value = false
}
viewport.addEventListener('change', updateViewport)
onBeforeUnmount(() => viewport.removeEventListener('change', updateViewport))
</script>

<style scoped>
.chat-page { display: grid; grid-template-columns: 248px minmax(0, 1fr); height: max(560px, calc(100dvh - 200px)); max-width: 1440px; margin: 20px auto 0; overflow: hidden; border: 1px solid var(--smart-border-strong); border-radius: 16px; background: var(--smart-bg); color: var(--smart-text); }
.chat-page__sidebar { min-height: 0; border-right: 1px solid var(--smart-border-strong); }
.chat-page__main { display: flex; flex-direction: column; min-width: 0; min-height: 0; padding: 24px 28px 14px; }
.chat-page__header { display: flex; align-items: center; gap: 12px; padding-bottom: 20px; border-bottom: 1px solid var(--smart-border); }
.chat-page__header > div { min-width: 0; }
.chat-page__header .eyebrow { margin: 0 0 8px; color: var(--smart-muted); font-size: 10px; }
.chat-page__header h1 { margin: 0; font-size: 20px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-page__badge { margin-left: auto; white-space: nowrap; color: var(--smart-primary-strong); font-size: 11px; }
.chat-page__history-toggle { display: grid; place-items: center; flex: 0 0 44px; height: 44px; border: 1px solid var(--smart-border-strong); border-radius: 8px; background: var(--smart-surface); color: var(--smart-text); cursor: pointer; }
.chat-page__history-toggle:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.chat-page__history-toggle svg { width: 18px; height: 18px; }
.chat-page__warning { color: var(--smart-danger); font-size: 12px; line-height: 1.6; }
.chat-page__conversation { display: flex; flex: 1; flex-direction: column; min-height: 0; padding-top: 20px; }
.chat-page__conversation :deep(.ai-chat-messages) { flex: 1; min-height: 0; max-height: none; align-content: start; padding: 4px 4px 12px; }
.chat-page__conversation :deep(.ai-chat-empty) { flex: 1; justify-content: center; padding-bottom: 24px; }
.chat-page__conversation :deep(.ai-chat-composer) { flex-shrink: 0; }
.chat-page__disclaimer { margin: 14px 0 0; color: var(--smart-muted); text-align: center; font-size: 11px; line-height: 1.6; }
:global(.chat-history-drawer) { background: var(--smart-surface); color: var(--smart-text); }
:global(.chat-history-drawer .el-drawer__body) { padding: 0; overflow: hidden; }
:global(.chat-history-drawer .el-drawer__header) { margin-bottom: 0; color: var(--smart-text); }
@media (max-width: 1100px) { .chat-page { grid-template-columns: 220px minmax(0, 1fr); } .chat-page__main { padding: 20px 18px 14px; } }
@media (max-width: 1023px) { .chat-page { grid-template-columns: minmax(0, 1fr); margin-top: 12px; height: max(530px, calc(100dvh - 170px)); border-radius: 12px; } .chat-page__main { padding: 16px 12px 12px; } .chat-page__header { gap: 10px; padding-bottom: 14px; } .chat-page__header h1 { font-size: 17px; } .chat-page__badge { display: none; } .chat-page__conversation :deep(textarea) { font-size: 16px; } }
</style>
