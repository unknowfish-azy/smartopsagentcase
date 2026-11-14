<template>
  <article class="ops-card xiaoyu-card" aria-label="小鱼 · 3D 化身面板">
    <header class="ops-card__head">
      <div class="ops-card__titles">
        <span class="u-overline">XIAOYU · 智能体化身</span>
        <h3 class="u-section">小鱼</h3>
      </div>
      <span class="xiaoyu-state-pill" :data-state="personaState">{{ personaStateLabel }}</span>
    </header>

    <div class="xiaoyu-body">
      <!-- 3D 半身舞台：竖版 16:10 裁剪，只露上半身 -->
      <div class="xiaoyu-stage" aria-label="小鱼 3D 形象">
        <AgentPersona
          ref="personaRef"
          :state="personaState"
          mode="vrm"
          quality="auto"
        />
      </div>

      <div class="xiaoyu-side">
        <!-- 当前状态 + 情境一句话 -->
        <p class="xiaoyu-bubble">{{ bubbleText }}</p>

        <!-- 快捷对话输入 -->
        <form class="xiaoyu-input" @submit.prevent="onSend">
          <textarea
            v-model="input"
            rows="2"
            maxlength="200"
            placeholder="跟小鱼说点什么…（回车发送）"
            @keydown.enter.exact.prevent="onSend"
          ></textarea>
          <button type="submit" class="xiaoyu-send" :disabled="!input.trim() || sending">
            {{ sending ? '思考中…' : '发送 →' }}
          </button>
        </form>

        <!-- 3 个快捷按钮 -->
        <div class="xiaoyu-quicks">
          <button type="button" class="xiaoyu-quick" @click="$router.push('/health')">一键体检</button>
          <button type="button" class="xiaoyu-quick" @click="$router.push('/knowledge')">读取知识库</button>
          <button type="button" class="xiaoyu-quick" @click="goExplainAlerts">解释告警</button>
        </div>

        <!-- RAG + Agent 训练 双行指标 -->
        <div class="xiaoyu-metrics">
          <div class="xiaoyu-metric">
            <span class="xiaoyu-metric-label">RAG</span>
            <strong>{{ ragTotal }}</strong>
            <span class="xiaoyu-metric-hint">知识条目</span>
          </div>
          <div class="xiaoyu-metric">
            <span class="xiaoyu-metric-label">训练</span>
            <strong>{{ agentStats.conversations }}</strong>
            <span class="xiaoyu-metric-hint">对话历史</span>
          </div>
          <div class="xiaoyu-metric">
            <span class="xiaoyu-metric-label">技能</span>
            <strong>{{ agentStats.skills }}</strong>
            <span class="xiaoyu-metric-hint">可用</span>
          </div>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AgentPersona from '../persona/AgentPersona.vue'
import { useCompanionStore } from '../../stores/companion.js'
import { useAiChatStore } from '../../stores/aiChat.js'

const router = useRouter()
const companion = useCompanionStore()
const aiChat = useAiChatStore()

const personaRef = ref(null)
const input = ref('')
const sending = ref(false)

/** 七状态映射：whale 状态 → personaStates profile key */
const personaState = computed(() => {
  const whale = companion.states.whale
  if (whale === 'DEGRADED') return 'warning'
  if (whale === 'CRITICAL') return 'error'
  if (whale === 'UNKNOWN') return 'idle'
  return 'idle'
})

const STATE_LABELS = {
  idle: '待机',
  thinking: '思考中',
  executing: '执行中',
  observing: '观察',
  warning: '告警',
  error: '故障',
  recovering: '恢复中'
}
const personaStateLabel = computed(() => STATE_LABELS[personaState.value] ?? '待机')

const bubbleText = computed(() => {
  const alerts = companion.contextSnapshot?.activeFault?.title
  switch (personaState.value) {
    case 'warning': return alerts ? `有活跃告警：${alerts.slice(0, 30)}` : '注意：需要你关注'
    case 'error': return '故障正在排查中'
    default: return '你好，今天想让我做什么？'
  }
})

/** RAG 知识条目数 — 读 localStorage 缓存 + mock 兜底（真实接入后替换） */
const ragTotal = ref(0)

/** Agent 训练统计 — mock，真实接入后替换成 modelGovernance 接口 */
const agentStats = ref({ conversations: 156, skills: 8, lastFineTune: '3 天前' })

async function loadRag() {
  try {
    const raw = localStorage.getItem('smartops_rag_stats')
    if (raw) {
      const data = JSON.parse(raw)
      ragTotal.value = Number(data.total) || 0
      return
    }
  } catch {}
  ragTotal.value = 284 // mock fallback
}

async function onSend() {
  const text = input.value.trim()
  if (!text || sending.value) return
  sending.value = true
  try {
    await aiChat.sendMessage(text)
    input.value = ''
    router.push('/chat')
  } finally {
    sending.value = false
  }
}

function goExplainAlerts() {
  router.push({ path: '/sentinel/alerts', query: { focus: 'active' } })
}

/** 让小鱼随状态切换姿态 */
watch(personaState, (state) => {
  personaRef.value?.setState?.(state, { fade: 350 })
})

onMounted(() => {
  loadRag()
})
onBeforeUnmount(() => {
  personaRef.value?.dispose?.()
})
</script>

<style scoped>
.xiaoyu-card {
  display: grid;
  gap: 12px;
}

.xiaoyu-body {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

/* 3D 半身舞台：竖版裁剪，只露上半身 */
.xiaoyu-stage {
  aspect-ratio: 9 / 12;
  border-radius: var(--ds-radius-md);
  overflow: hidden;
  background:
    radial-gradient(120% 90% at 50% 100%, rgba(36, 150, 237, .18), transparent 62%),
    var(--ds-color-surface-base);
  position: relative;
  isolation: isolate;
}
.xiaoyu-stage :deep(.persona) {
  padding: 0;
  border: none;
  background: none;
  /* 舞台居中裁剪，让 sendagaya-shino 上半身正好露在竖框里 */
  transform: translateY(-6%);
}
.xiaoyu-stage :deep(.webgl-host) { max-width: none; }

/* 状态气泡 */
.xiaoyu-bubble {
  margin: 0 0 10px;
  padding: 10px 14px;
  border-radius: var(--ds-radius-md);
  background: var(--ds-pill-info-bg);
  color: var(--ds-color-text);
  font-size: var(--ds-type-body-caption-size);
  line-height: var(--ds-line-height-base);
  border-left: 2px solid var(--ds-color-primary);
}

/* 快捷对话 */
.xiaoyu-input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  margin-bottom: 10px;
}
.xiaoyu-input textarea {
  resize: none;
  padding: 8px 10px;
  border: 1px solid var(--ds-hairline);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-base);
  color: var(--ds-color-text);
  font-size: var(--ds-type-body-caption-size);
  line-height: var(--ds-line-height-base);
  font-family: inherit;
}
.xiaoyu-input textarea:focus {
  outline: none;
  border-color: var(--ds-color-primary);
}
.xiaoyu-send {
  padding: 0 14px;
  border: 1px solid var(--ds-color-primary);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-primary);
  color: #fff;
  font-size: var(--ds-type-caption-size);
  font-weight: 500;
  cursor: pointer;
}
.xiaoyu-send:disabled {
  opacity: .5;
  cursor: not-allowed;
}

/* 3 个快捷按钮 */
.xiaoyu-quicks {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 12px;
}
.xiaoyu-quick {
  padding: 7px 10px;
  border: 1px solid var(--ds-hairline);
  border-radius: var(--ds-radius-sm);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: 11.5px;
  cursor: pointer;
  transition: border-color var(--ds-duration-micro) var(--ds-ease-out),
              color var(--ds-duration-micro) var(--ds-ease-out),
              background var(--ds-duration-micro) var(--ds-ease-out);
}
.xiaoyu-quick:hover {
  border-color: var(--ds-color-primary);
  color: var(--ds-color-primary);
  background: color-mix(in srgb, var(--ds-color-primary) 6%, transparent);
}

/* 指标行 */
.xiaoyu-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--ds-hairline);
}
.xiaoyu-metric {
  display: grid;
  gap: 2px;
  padding: 6px 8px;
  border-radius: var(--ds-radius-sm);
  background: color-mix(in srgb, var(--ds-color-text) 3%, transparent);
  text-align: left;
}
.xiaoyu-metric-label {
  font: 9px/1 var(--ds-font-mono);
  color: var(--ds-color-muted);
  letter-spacing: .1em;
  text-transform: uppercase;
}
.xiaoyu-metric strong {
  font-size: var(--ds-type-body-size);
  font-weight: 600;
  color: var(--ds-color-text);
}
.xiaoyu-metric-hint {
  font-size: 10.5px;
  color: var(--ds-color-muted);
}

.xiaoyu-state-pill {
  padding: 3px 10px;
  font: 9.5px var(--ds-font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  border-radius: var(--ds-radius-pill);
  background: var(--ds-pill-info-bg);
  color: var(--ds-color-primary);
}
.xiaoyu-state-pill[data-state="warning"] { background: color-mix(in srgb, #ffb454 16%, transparent); color: #ffb454; }
.xiaoyu-state-pill[data-state="error"]    { background: color-mix(in srgb, #ff6b6b 16%, transparent); color: #ff6b6b; }
.xiaoyu-state-pill[data-state="recovering"] { background: color-mix(in srgb, #5fd3a5 16%, transparent); color: #5fd3a5; }

@media (max-width: 1024px) {
  .xiaoyu-body { grid-template-columns: 140px minmax(0, 1fr); }
}
@media (max-width: 640px) {
  .xiaoyu-body { grid-template-columns: 1fr; }
  .xiaoyu-stage { aspect-ratio: 9 / 16; max-width: 140px; margin: 0 auto; }
}
</style>
