<template>
  <aside class="chat-history" aria-label="历史会话">
    <div class="chat-history__heading"><span>会话空间</span><span>{{ conversations.length }}</span></div>
    <button type="button" class="chat-history__new" @click="create"><Plus :size="16" aria-hidden="true" />新建对话</button>
    <label class="chat-history__search"><Search :size="16" aria-hidden="true" /><input v-model="query" type="search" placeholder="搜索会话" aria-label="搜索历史会话" /></label>
    <div class="chat-history__list">
      <section v-for="group in groups" :key="group.label" class="chat-history__group" :aria-label="group.label">
        <h2>{{ group.label }}</h2>
        <div v-for="conversation in group.items" :key="conversation.id" class="chat-history__item" :class="{ 'is-active': activeId === conversation.id }">
          <button type="button" class="chat-history__select" :aria-current="activeId === conversation.id ? 'true' : undefined" :title="conversation.title" @click="select(conversation.id)">
            <ChatDotRound :size="16" aria-hidden="true" /><span>{{ conversation.title }}</span><span v-if="conversation.messages.some(message => message.pending)" class="chat-history__pending" aria-label="正在回复">·</span>
          </button>
          <el-dropdown trigger="click" popper-class="chat-history-menu" @command="command => manage(command, conversation)">
            <button type="button" class="chat-history__more" :aria-label="`管理会话：${conversation.title}`"><MoreFilled :size="16" aria-hidden="true" /></button>
            <template #dropdown><el-dropdown-menu><el-dropdown-item command="rename">重命名</el-dropdown-item><el-dropdown-item command="delete">删除会话</el-dropdown-item></el-dropdown-menu></template>
          </el-dropdown>
        </div>
      </section>
      <p v-if="!groups.length" class="chat-history__empty">{{ query ? '没有找到匹配的会话' : '还没有历史会话，开始聊聊吧。' }}</p>
    </div>
    <p class="chat-history__note">普通文本记录保存在当前浏览器。附件会话保存在服务器，仅当前账号可见，不自动共享到团队。</p>
  </aside>
</template>

<script setup>
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessageBox } from 'element-plus/es/components/message-box/index.mjs'
import 'element-plus/es/components/message-box/style/css.mjs'
import { ChatDotRound, MoreFilled, Plus, Search } from '@element-plus/icons-vue'
import { useAiChatStore } from '../../stores/aiChat.js'
import { groupConversations } from '../../domain/chat/history.ts'

const emit = defineEmits(['selected'])
const store = useAiChatStore()
const { conversations, activeId } = storeToRefs(store)
const query = ref('')
const groups = computed(() => groupConversations(conversations.value, query.value))

function create() {
  query.value = ''
  store.newConversation()
  emit('selected')
}

function select(id) {
  store.selectConversation(id)
  emit('selected')
}

async function manage(command, conversation) {
  try {
    if (command === 'rename') {
      const result = await ElMessageBox.prompt('给这段会话起一个容易找到的名字', '重命名会话', {
        customClass: 'chat-history-dialog', inputValue: conversation.title, confirmButtonText: '保存', cancelButtonText: '取消',
        inputValidator: value => Boolean(value?.trim() && value.trim().length <= 80) || '请输入 1–80 个字符'
      })
      await store.renameConversation(conversation.id, result.value)
    } else if (command === 'delete') {
      await ElMessageBox.confirm(`确定删除“${conversation.title}”？${conversation.remote ? '服务器会话及附件将一并删除，备份按保留策略清理。' : '聊天记录将从当前浏览器移除。'}无法撤销。`, '删除会话', {
        customClass: 'chat-history-dialog', confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning'
      })
      await store.deleteConversation(conversation.id)
    }
  } catch {}
}
</script>

<style scoped>
:global(.chat-history-dialog), :global(.chat-history-menu), :global(.chat-history-drawer) {
  --el-bg-color: var(--smart-surface); --el-bg-color-overlay: var(--smart-surface); --el-fill-color-blank: var(--smart-surface);
  --el-text-color-primary: var(--smart-text); --el-text-color-regular: var(--smart-text); --el-text-color-secondary: var(--smart-muted); --el-text-color-placeholder: var(--smart-muted);
  --el-border-color: var(--smart-border-strong); --el-border-color-light: var(--smart-border); --el-border-color-lighter: var(--smart-border);
  --el-color-primary: var(--smart-primary-strong); --el-color-primary-light-9: var(--smart-primary-soft); --el-color-primary-light-3: var(--smart-primary);
  --el-fill-color-light: var(--smart-primary-soft);
}
:global(.chat-history-dialog .el-button--primary) { color: var(--smart-primary-foreground); background: var(--smart-primary); border-color: var(--smart-primary); }
.chat-history { display: flex; flex-direction: column; gap: 16px; height: 100%; min-height: 0; padding: 20px 14px; box-sizing: border-box; color: var(--smart-text); background: var(--smart-surface); }
.chat-history__heading { display: flex; justify-content: space-between; align-items: center; padding: 0 6px; font-size: 13px; font-weight: 600; }
.chat-history__heading > span:last-child { color: var(--smart-muted); font: 11px var(--font-mono); }
.chat-history button { font-family: inherit; cursor: pointer; }
.chat-history svg { flex: 0 0 16px; width: 16px; height: 16px; }
.chat-history__new { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; border: 1px solid var(--smart-border-strong); border-radius: 9px; background: var(--smart-primary-soft); color: var(--smart-primary-strong); font-size: 13px; font-weight: 600; }
.chat-history__search { display: flex; align-items: center; gap: 8px; padding: 0 10px; min-height: 42px; border: 1px solid var(--smart-border); border-radius: 8px; color: var(--smart-muted); background: var(--smart-bg); }
.chat-history__search input { width: 100%; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--smart-text); font: 13px var(--font-cn); }
.chat-history__search input::placeholder { color: var(--smart-muted); }
.chat-history__search:focus-within { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.chat-history__list { flex: 1; min-height: 0; overflow-y: auto; scrollbar-width: thin; }
.chat-history__group + .chat-history__group { margin-top: 20px; }
.chat-history__group h2 { margin: 0 8px 8px; color: var(--smart-muted); font-size: 11px; font-weight: 500; }
.chat-history__item { display: flex; align-items: center; border: 1px solid transparent; border-radius: 8px; margin-bottom: 4px; }
.chat-history__item:hover { background: var(--smart-primary-soft); }
.chat-history__item.is-active { background: var(--smart-primary-soft); border-color: var(--smart-border-strong); }
.chat-history__select { display: flex; align-items: center; gap: 9px; flex: 1; min-width: 0; min-height: 44px; padding: 8px; border: 0; border-radius: 7px; background: transparent; color: var(--smart-text); text-align: left; font-size: 13px; }
.chat-history__select > svg { flex-shrink: 0; color: var(--smart-muted); }
.chat-history__select > span:first-of-type { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-history__pending { color: var(--smart-primary-strong); font-size: 24px; }
.chat-history__more { display: grid; place-items: center; width: 36px; height: 44px; padding: 0; border: 0; border-radius: 7px; background: transparent; color: var(--smart-muted); }
.chat-history__more:hover { color: var(--smart-text); background: var(--smart-bg); }
.chat-history button:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: -2px; }
.chat-history__empty, .chat-history__note { color: var(--smart-muted); font-size: 12px; line-height: 1.7; }
.chat-history__empty { padding: 12px 8px; }
.chat-history__note { padding: 14px 6px 0; margin: 0; border-top: 1px solid var(--smart-border); font-size: 11px; }
@media (max-width: 767px) { .chat-history__search input { font-size: 16px; } .chat-history__more { width: 44px; } }
</style>
