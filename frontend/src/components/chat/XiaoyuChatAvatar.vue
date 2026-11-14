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
          <span class="xiaoyu-chat-drawer__pill">{{ stateLabel }}</span>
        </div>
      </template>

      <div class="xiaoyu-chat-drawer__body">
        <!-- 半身 220px，Drawer 打开时才挂载 AgentPersona，关闭时自动 dispose -->
        <AgentPersona
          v-if="drawerOpen"
          ref="personaRef"
          :state="personaState"
          mode="vrm"
          class="xiaoyu-chat-drawer__stage"
        />

        <p class="xiaoyu-chat-drawer__bubble">{{ bubbleText }}</p>

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
import { computed, ref } from 'vue'
import { ElDrawer } from 'element-plus'
import { useCompanionStore } from '../../stores/companion.js'
import AgentPersona from '../persona/AgentPersona.vue'

const companion = useCompanionStore()
const drawerOpen = ref(false)

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
  border-radius: 999px;
}

.xiaoyu-chat-drawer__body { padding: 20px; display: grid; gap: 14px; }

.xiaoyu-chat-drawer__stage {
  aspect-ratio: 9 / 11;
  max-height: 220px;
  border-radius: var(--ds-radius-md, 10px);
  background:
    radial-gradient(120% 90% at 50% 100%, rgba(36, 150, 237, .18), transparent 62%),
    var(--ds-color-surface-base, #1a1f2e);
  overflow: hidden;
  position: relative;
}

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
