<template>
  <Teleport to="body">
    <div class="acd">
    <transition name="acd-fade">
      <section
        v-if="open"
        class="acd-panel"
        role="dialog"
        aria-label="页面侧翼 Agent"
        aria-modal="false"
      >
        <header class="acd-head">
          <div class="acd-head__text">
            <strong>{{ heading }}</strong>
            <small>{{ sectionLabel }}</small>
          </div>
          <div class="acd-head__actions">
            <button type="button" class="acd-ledger" @click="ledgerOpen = true">信任账本</button>
            <button type="button" class="acd-close" aria-label="关闭侧翼面板" @click="open = false">×</button>
          </div>
        </header>

        <p class="acd-entity">
          本页实体：<code>{{ entityLabel }}</code>
        </p>

        <div class="acd-suggestions">
          <button
            v-for="item in activeSuggestions"
            :key="item"
            type="button"
            :disabled="sending"
            @click="send(item)"
          >
            {{ item }}
          </button>
        </div>

        <form class="acd-composer" @submit.prevent="send()">
          <textarea
            v-model="draft"
            rows="3"
            maxlength="2000"
            :disabled="sending"
            placeholder="带着本页实体提问，例如：这条告警的指标和影响面是什么？"
            aria-label="侧翼提问内容"
          ></textarea>
          <button type="submit" class="acd-send" :disabled="sending || !draft.trim()">
            {{ sending ? '思考中…' : '发送' }}
          </button>
        </form>

        <ol v-if="thinking.length" class="acd-thinking" aria-label="Agent 处理过程">
          <li v-for="(step, index) in thinking" :key="index">{{ step.label }}</li>
        </ol>

        <div v-if="answer" class="acd-answer">
          <p>{{ answer }}<span v-if="sending" class="acd-cursor" aria-hidden="true"></span></p>
        </div>

        <p v-if="error" class="acd-error" role="alert">{{ error }}</p>

        <SecurityBriefCard v-if="brief" :brief="brief" />

        <p class="acd-foot">
          侧翼只上报本页结构化上下文（路径/栏目/实体），不抓取页面 DOM；回答仅作建议，不自动执行写操作。
        </p>
      </section>
    </transition>

    <button
      type="button"
      class="acd-launcher"
      :class="{ 'is-open': open }"
      :aria-expanded="open"
      aria-label="打开页面侧翼 Agent"
      @click="toggle"
    >
      <span class="acd-launcher__mark" aria-hidden="true">AI</span>
      <span>问 Agent</span>
    </button>

    <TrustLedgerDrawer v-model="ledgerOpen" />
    </div>
  </Teleport>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { buildPageContext } from '../../domain/chat/pageContext.js'
import { fetchChatRunToken } from '../../api/chatRunToken.ts'
import { streamChat } from '../../api/stream.ts'
import SecurityBriefCard from './SecurityBriefCard.vue'
import TrustLedgerDrawer from './TrustLedgerDrawer.vue'

const props = defineProps({
  /** 本页当前实体：{ type, id }，type 取自 pageContext 白名单。 */
  entity: { type: Object, default: null },
  /** 白名单只读摘要；只上报，不进提示词。 */
  snapshot: { type: Object, default: null },
  /** 附加预置问题；缺省按实体类型给出方案 §5.3 的入口文案。 */
  suggestions: { type: Array, default: () => [] },
  /** 栏目覆盖；缺省取路由 meta.section。 */
  section: { type: String, default: '' },
  heading: { type: String, default: '页面侧翼 · 问 Agent' },
})

const route = useRoute()
const open = ref(false)
const ledgerOpen = ref(false)
const draft = ref('')
const sending = ref(false)
const answer = ref('')
const brief = ref(null)
const error = ref('')
const thinking = ref([])

const DEFAULT_SUGGESTIONS = {
  alert: ['解释这条告警并给出处置建议'],
  event: ['这条事件根因是什么？'],
  doc: ['这条内容能入库吗？'],
  finding: ['这个 CVE 影响哪些资产？先修哪个？'],
  incident: ['这个事件影响哪些资产？先处理哪个？'],
  device: ['接管前风险自查'],
  server: ['这台机器为什么慢？'],
  connection: ['这个连接为什么限流？'],
  diagnostic: ['把这次诊断沉淀成 Runbook'],
}

const pageContext = computed(() =>
  buildPageContext(route, {
    entity: props.entity,
    snapshot: props.snapshot,
    section: props.section,
  }),
)

const entityLabel = computed(() =>
  props.entity && props.entity.id ? `${props.entity.type}:${props.entity.id}` : '未选择实体（按当前页面提问）',
)

const sectionLabel = computed(() => pageContext.value?.section || props.section || '当前页面')

const activeSuggestions = computed(() => {
  const provided = Array.isArray(props.suggestions)
    ? props.suggestions.filter(item => typeof item === 'string' && item.trim())
    : []
  if (provided.length) return provided.slice(0, 4)
  const byType = DEFAULT_SUGGESTIONS[props.entity?.type]
  return (byType || ['这个页面现在有什么风险？']).slice(0, 4)
})

function toggle() {
  open.value = !open.value
}

function resetRun() {
  answer.value = ''
  brief.value = null
  error.value = ''
  thinking.value = []
}

async function send(preset) {
  if (sending.value) return
  const prompt = String(preset ?? draft.value ?? '').trim().slice(0, 2000)
  if (!prompt) {
    error.value = '请输入要问 Agent 的内容。'
    return
  }
  draft.value = prompt
  resetRun()
  sending.value = true
  try {
    const response = await fetchChatRunToken()
    const issued = response?.data ?? response
    const runToken = issued?.runToken
    if (!runToken) throw new Error('聊天鉴权令牌签发失败，请刷新页面后重试。')

    await streamChat(
      prompt,
      {
        onThinking: step => {
          if (step?.label) thinking.value = [...thinking.value, step]
        },
        onToken: delta => {
          if (delta) answer.value += delta
        },
        onDone: payload => {
          // 只展示服务端真实返回的简报；兼容顶层与 metadata 两种承载位置，缺失即不展示。
          brief.value = payload?.security_brief || payload?.metadata?.security_brief || null
        },
        onError: err => {
          error.value = err?.message || 'AI 服务返回错误'
        },
      },
      {
        context: pageContext.value || undefined,
        runToken,
        correlation: {
          request_id: crypto.randomUUID(),
          task_id: `copilot:${props.entity?.type || 'page'}:${props.entity?.id || route.path}`,
        },
      },
    )
  } catch (err) {
    error.value = err?.message || '暂时无法连接 AI 服务，请确认 ai-service 已启动。'
  } finally {
    sending.value = false
  }
}
</script>

<style scoped>
.acd {
  position: relative;
  z-index: 1600;
}

.acd-launcher {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 1600;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border: 1px solid var(--ds-color-border-strong, rgba(159, 190, 207, .34));
  border-radius: var(--ds-radius-pill, 999px);
  background: var(--ds-surface-overlay, #1b212a);
  color: var(--ds-color-text, #e8f2f7);
  font-size: var(--ds-font-sm, 13px);
  cursor: pointer;
  box-shadow: var(--ds-elevation-2, 0 4px 16px rgba(0, 0, 0, .35));
}

.acd-launcher:hover,
.acd-launcher.is-open {
  border-color: var(--ds-color-primary-strong, #7ad7f5);
  color: var(--ds-color-primary-strong, #7ad7f5);
}

.acd-launcher__mark {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--ds-color-primary, #2496ed);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .04em;
}

.acd-panel {
  position: fixed;
  right: 24px;
  bottom: 78px;
  z-index: 1600;
  width: min(380px, calc(100vw - 32px));
  max-height: 72vh;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--ds-color-border-strong, rgba(159, 190, 207, .34));
  border-radius: var(--ds-radius-lg, 12px);
  background: var(--ds-surface-overlay, #1b212a);
  color: var(--ds-color-text, #e8f2f7);
  box-shadow: var(--ds-elevation-3, 0 12px 32px rgba(0, 0, 0, .42));
  font-size: var(--ds-font-sm, 13px);
}

.acd-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.acd-head__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.acd-head__text small {
  color: var(--ds-color-muted, #92a6b5);
  font-size: 12px;
}

.acd-head__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.acd-ledger {
  padding: 3px 8px;
  border: 1px solid var(--ds-hairline, rgba(255, 255, 255, .16));
  border-radius: var(--ds-radius-sm, 6px);
  background: transparent;
  color: var(--ds-color-muted, #92a6b5);
  font-size: 12px;
  cursor: pointer;
}

.acd-ledger:hover {
  border-color: var(--ds-semantic-info, #58a6ff);
  color: var(--ds-semantic-info, #58a6ff);
}

.acd-close {
  border: none;
  background: transparent;
  color: var(--ds-color-muted, #92a6b5);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}

.acd-entity {
  margin: 0;
  color: var(--ds-color-muted, #92a6b5);
  font-size: 12px;
}

.acd-entity code {
  color: var(--ds-color-primary-strong, #7ad7f5);
  font-family: var(--ds-font-mono, monospace);
}

.acd-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.acd-suggestions button {
  padding: 4px 10px;
  border: 1px solid var(--ds-color-border, rgba(159, 190, 207, .18));
  border-radius: var(--ds-radius-pill, 999px);
  background: var(--ds-surface-raised, #151a21);
  color: var(--ds-color-text, #e8f2f7);
  font-size: 12px;
  cursor: pointer;
}

.acd-suggestions button:hover:not(:disabled) {
  border-color: var(--ds-color-primary-strong, #7ad7f5);
}

.acd-composer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.acd-composer textarea {
  width: 100%;
  resize: vertical;
  padding: 8px;
  border: 1px solid var(--ds-color-border, rgba(159, 190, 207, .18));
  border-radius: var(--ds-radius-md, 8px);
  background: var(--ds-surface-base, #0e1116);
  color: var(--ds-color-text, #e8f2f7);
  font: inherit;
}

.acd-send {
  align-self: flex-end;
  padding: 6px 16px;
  border: none;
  border-radius: var(--ds-radius-md, 8px);
  background: var(--ds-color-primary, #2496ed);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.acd-send:disabled {
  opacity: .55;
  cursor: not-allowed;
}

.acd-thinking {
  margin: 0;
  padding-left: 18px;
  color: var(--ds-color-muted, #92a6b5);
  font-size: 12px;
}

.acd-answer p {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.acd-cursor {
  display: inline-block;
  width: 7px;
  height: 15px;
  margin-left: 2px;
  background: var(--ds-color-primary-strong, #7ad7f5);
  animation: acd-blink 1s steps(2) infinite;
  vertical-align: text-bottom;
}

.acd-error {
  margin: 0;
  color: var(--ds-semantic-danger, #f85149);
}

.acd-foot {
  margin: 0;
  color: var(--ds-color-muted, #92a6b5);
  font-size: 11px;
}

.acd-fade-enter-active,
.acd-fade-leave-active {
  transition: opacity var(--ds-duration-micro, 150ms) var(--ds-ease-out, ease-out),
    transform var(--ds-duration-micro, 150ms) var(--ds-ease-out, ease-out);
}

.acd-fade-enter-from,
.acd-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

@keyframes acd-blink {
  50% { opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .acd-cursor { animation: none; }
  .acd-fade-enter-active,
  .acd-fade-leave-active { transition: none; }
}
</style>
