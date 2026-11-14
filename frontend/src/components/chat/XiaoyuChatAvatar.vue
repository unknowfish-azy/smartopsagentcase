<template>
  <div class="xiaoyu-chat-avatar" aria-label="小鱼头像">
    <!-- 64px 圆形头像按钮 -->
    <button
      class="xiaoyu-chat-avatar__btn"
      type="button"
      :title="`小鱼 · ${stateLabel}`"
      @click="drawerOpen = true"
    >
      <svg viewBox="0 0 64 64" class="xiaoyu-chat-avatar__ring" aria-hidden="true">
        <circle cx="32" cy="32" r="30" fill="none" stroke="url(#ringGrad)" stroke-width="1.5" />
        <defs>
          <linearGradient id="ringGrad" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stop-color="#2496ed" />
            <stop offset="100%" stop-color="#7ad7f5" />
          </linearGradient>
        </defs>
      </svg>
      <!-- 圆形 canvas 占位（Drawer 里才真正挂载 AgentPersona） -->
      <span class="xiaoyu-chat-avatar__orb" aria-hidden="true">
        <span class="orb-core"></span>
      </span>
      <span class="xiaoyu-chat-avatar__pulse" :data-active="companionStates.whale !== 'IDLE'"></span>
    </button>

    <el-drawer
      v-model="drawerOpen"
      direction="rtl"
      size="min(300px, calc(100vw - 24px))"
      append-to-body
      :show-close="true"
      class="xiaoyu-chat-drawer"
      @closed="disposePersona"
    >
      <template #header>
        <div class="xiaoyu-chat-drawer__head">
          <span class="xiaoyu-chat-drawer__eyebrow">XIAOYU</span>
          <strong>小鱼</strong>
          <button type="button" class="xiaoyu-chat-drawer__pill" :title="`点击切换状态（演示） · ${stateLabel}`" @click="cycleDemoState">{{ stateLabel }}</button>
        </div>
      </template>

      <div class="xiaoyu-chat-drawer__body">
        <!-- 半身 220px，Drawer 打开时才挂载 AgentPersona，点击让小鱼开口说话 -->
        <button type="button" class="xiaoyu-chat-drawer__stage" :title="点击让小鱼说话" @click="speakGreeting">
          <AgentPersona
            v-if="drawerOpen"
            ref="personaRef"
            :state="personaState"
            mode="vrm"
          />
        </button>

        <p class="xiaoyu-chat-drawer__bubble">{{ bubbleText }}</p>

        <!-- 快捷对话输入（发完跳到 Chat 主区，让小鱼接话） -->
        <form class="xiaoyu-chat-drawer__input" @submit.prevent="onSend">
          <input
            v-model="input"
            type="text"
            maxlength="100"
            placeholder="跟小鱼说点什么…（回车发送）"
            @keydown.enter.exact.prevent="onSend"
          />
          <button type="submit" class="xiaoyu-chat-drawer__send" :disabled="!input.trim() || sending">
            {{ sending ? '…' : '发送' }}
          </button>
        </form>

        <div class="xiaoyu-chat-drawer__quicks">
          <RouterLink to="/health" class="xiaoyu-chat-drawer__link">
            <span>一键体检</span><i>→</i>
          </RouterLink>
          <RouterLink to="/knowledge" class="xiaoyu-chat-drawer__link">
            <span>读取知识库</span><i>→</i>
          </RouterLink>
          <RouterLink to="/sentinel/alerts" class="xiaoyu-chat-drawer__link">
            <span>告警中心</span><i>→</i>
          </RouterLink>
        </div>

        <dl class="xiaoyu-chat-drawer__stats">
          <div><dt>RAG</dt><dd>{{ ragTotal }} 条</dd></div>
          <div><dt>对话</dt><dd>{{ agentStats.conversations }}</dd></div>
          <div><dt>技能</dt><dd>{{ agentStats.skills }}</dd></div>
        </dl>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElDrawer } from 'element-plus'
import { useCompanionStore } from '../../stores/companion.js'
import { useAiChatStore } from '../../stores/aiChat.js'
import AgentPersona from '../persona/AgentPersona.vue'

const router = useRouter()
const companion = useCompanionStore()
const aiChat = useAiChatStore()

const drawerOpen = ref(false)
const personaRef = ref(null)
const input = ref('')
const sending = ref(false)

const companionStates = computed(() => companion.states ?? { whale: 'IDLE' })

const personaState = computed(() => {
  const whale = companionStates.value.whale
  if (whale === 'DEGRADED') return 'warning'
  if (whale === 'CRITICAL') return 'error'
  return 'idle'
})

const STATE_LABELS = {
  idle: '待机', thinking: '思考中', executing: '执行中',
  observing: '观察', warning: '告警', error: '故障', recovering: '恢复中'
}
const stateLabel = computed(() => STATE_LABELS[personaState.value] ?? '待机')

const bubbleText = computed(() => {
  switch (personaState.value) {
    case 'warning': return '有活跃告警，我来帮你看看'
    case 'error': return '故障排查中，需要你关注'
    default: return '我在，说吧'
  }
})

const ragTotal = ref(284)
const agentStats = ref({ conversations: 156, skills: 8 })

/** 演示模式：点击 pill cycle 状态 */
const DEMO_STATE_ORDER = ['idle', 'thinking', 'observing', 'executing', 'warning', 'error', 'recovering']
const demoIdx = ref(0)
function cycleDemoState() {
  demoIdx.value = (demoIdx.value + 1) % DEMO_STATE_ORDER.length
  const next = DEMO_STATE_ORDER[demoIdx.value]
  personaRef.value?.setState?.(next, { fade: 350 })
  personaRef.value?.speakText?.(STATE_LABELS[next] ?? next)
}

/** 点击 3D 舞台让小鱼开口说话 */
const GREETINGS = {
  idle: ['我在，说吧。', '系统正常，随时待命。', '嗨～'],
  warning: ['有活跃告警。', '需要你关注一下。', '我注意到了异常。'],
  error: ['故障排查中。', '正在定位。', '需要协助吗？'],
  observing: ['观察中。', '巡检进行中。', '一切还好。'],
  thinking: ['让我想想。', '分析中…', '稍等。'],
  executing: ['执行中…', '处理中。', '马上好。'],
  recovering: ['恢复中…', '快好了。', '清理现场。']
}
function speakGreeting() {
  const pool = GREETINGS[personaState.value] ?? GREETINGS.idle
  const text = pool[Math.floor(Math.random() * pool.length)]
  personaRef.value?.speakText?.(text)
}

/** Drawer 里发完快捷对话 → 跳到 Chat 主区 */
async function onSend() {
  const text = input.value.trim()
  if (!text || sending.value) return
  sending.value = true
  try {
    await aiChat.sendMessage(text)
    input.value = ''
    drawerOpen.value = false
    router.push('/chat')
  } finally {
    sending.value = false
  }
}

/** Drawer 关闭时 dispose canvas，省资源 */
function disposePersona() {
  personaRef.value?.dispose?.()
}

watch(drawerOpen, (open) => { if (!open) disposePersona() })
onBeforeUnmount(disposePersona)
</script>

<style scoped>
.xiaoyu-chat-avatar { position: relative; }

.xiaoyu-chat-avatar__btn {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  border: none;
  background: var(--ds-color-surface-base, #1a1f2e);
  cursor: pointer;
  padding: 0;
  display: grid;
  place-items: center;
  overflow: hidden;
  transition: transform var(--ds-duration-micro, .15s) var(--ds-ease-out);
}
.xiaoyu-chat-avatar__btn:hover { transform: scale(1.05); }

.xiaoyu-chat-avatar__ring {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  pointer-events: none;
}

.xiaoyu-chat-avatar__orb {
  position: absolute; inset: 8px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 30%,
    rgba(122, 215, 245, .6),
    rgba(36, 150, 237, .25) 55%,
    rgba(36, 150, 237, .05) 80%);
  display: grid; place-items: center;
}
.xiaoyu-chat-avatar__orb::after {
  content: '🐟';
  font-size: 22px;
  opacity: .7;
}

.xiaoyu-chat-avatar__pulse {
  position: absolute; inset: 4px;
  border-radius: 50%;
  border: 1.5px solid transparent;
  pointer-events: none;
  transition: border-color .3s;
}
.xiaoyu-chat-avatar__pulse[data-active="true"] {
  border-color: rgba(255, 180, 84, .5);
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: .7; }
  50% { transform: scale(1.08); opacity: 1; }
}

/* Drawer 内部 */
:deep(.xiaoyu-chat-drawer .el-drawer__body) {
  padding: 0;
  background: var(--ds-color-surface-base, #1a1f2e);
  color: var(--ds-color-text, #e8e8ee);
}
:deep(.xiaoyu-chat-drawer .el-drawer__header) {
  margin-bottom: 0;
  padding: 16px 20px;
  border-bottom: 1px solid var(--ds-hairline, rgba(255,255,255,.06));
}

.xiaoyu-chat-drawer__head { display: flex; align-items: center; gap: 8px; }
.xiaoyu-chat-drawer__eyebrow {
  font: 9px var(--ds-font-mono, monospace);
  letter-spacing: .1em;
  color: var(--ds-color-muted, #6b7280);
  margin-right: 2px;
}
.xiaoyu-chat-drawer__pill {
  margin-left: auto;
  padding: 2px 10px;
  font: 9.5px var(--ds-font-mono, monospace);
  letter-spacing: .1em;
  background: var(--ds-pill-info-bg, rgba(36,150,237,.12));
  color: var(--ds-color-primary, #2496ed);
  border: 1px solid transparent;
  border-radius: 999px;
  cursor: pointer;
  transition: border-color .15s, background .15s;
}
.xiaoyu-chat-drawer__pill:hover {
  border-color: var(--ds-color-primary, #2496ed);
  background: color-mix(in srgb, var(--ds-color-primary) 14%, transparent);
}

.xiaoyu-chat-drawer__body { padding: 20px; display: grid; gap: 14px; }

.xiaoyu-chat-drawer__stage {
  display: block;
  aspect-ratio: 9 / 11;
  max-height: 220px;
  border-radius: var(--ds-radius-md, 10px);
  background:
    radial-gradient(120% 90% at 50% 100%, rgba(36, 150, 237, .18), transparent 62%),
    var(--ds-color-surface-base, #1a1f2e);
  overflow: hidden;
  position: relative;
  border: none;
  padding: 0;
  cursor: pointer;
  transition: box-shadow .15s, transform .15s;
}
.xiaoyu-chat-drawer__stage:hover {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--ds-color-primary) 40%, transparent);
}
.xiaoyu-chat-drawer__stage:active { transform: scale(.98); }

.xiaoyu-chat-drawer__bubble {
  margin: 0;
  padding: 10px 14px;
  border-radius: var(--ds-radius-md, 10px);
  background: var(--ds-pill-info-bg, rgba(36,150,237,.08));
  border-left: 2px solid var(--ds-color-primary, #2496ed);
  font-size: var(--ds-type-body-caption-size, 13px);
  line-height: var(--ds-line-height-base, 1.5);
  color: var(--ds-color-text, #e8e8ee);
}

/* Drawer 内快捷对话输入 */
.xiaoyu-chat-drawer__input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px;
}
.xiaoyu-chat-drawer__input input {
  padding: 8px 10px;
  border: 1px solid var(--ds-hairline, rgba(255,255,255,.08));
  border-radius: var(--ds-radius-md, 10px);
  background: var(--ds-color-surface-base, #1a1f2e);
  color: var(--ds-color-text, #e8e8ee);
  font-size: 12.5px;
  font-family: inherit;
  outline: none;
  transition: border-color .15s;
}
.xiaoyu-chat-drawer__input input:focus {
  border-color: var(--ds-color-primary, #2496ed);
}
.xiaoyu-chat-drawer__send {
  padding: 0 14px;
  border: 1px solid var(--ds-color-primary, #2496ed);
  border-radius: var(--ds-radius-md, 10px);
  background: var(--ds-color-primary, #2496ed);
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity .15s;
}
.xiaoyu-chat-drawer__send:disabled {
  opacity: .4;
  cursor: not-allowed;
}

.xiaoyu-chat-drawer__quicks {
  display: grid; gap: 4px;
}
.xiaoyu-chat-drawer__link {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px;
  border: 1px solid var(--ds-hairline, rgba(255,255,255,.06));
  border-radius: var(--ds-radius-sm, 6px);
  color: var(--ds-color-muted, #9ca3af);
  text-decoration: none;
  font-size: 12.5px;
  transition: all .15s;
}
.xiaoyu-chat-drawer__link:hover {
  border-color: var(--ds-color-primary, #2496ed);
  color: var(--ds-color-primary, #2496ed);
}
.xiaoyu-chat-drawer__link i { font-style: normal; opacity: .5; }

.xiaoyu-chat-drawer__stats {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;
  margin: 0; padding-top: 10px;
  border-top: 1px solid var(--ds-hairline, rgba(255,255,255,.06));
}
.xiaoyu-chat-drawer__stats div {
  display: grid; gap: 2px; text-align: center;
}
.xiaoyu-chat-drawer__stats dt {
  font: 9px var(--ds-font-mono, monospace);
  letter-spacing: .1em;
  color: var(--ds-color-muted, #6b7280);
  text-transform: uppercase;
}
.xiaoyu-chat-drawer__stats dd {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ds-color-text, #e8e8ee);
}
</style>
