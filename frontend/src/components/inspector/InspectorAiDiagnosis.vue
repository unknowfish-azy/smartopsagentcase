<template>
  <section class="ai-diagnosis" aria-label="AI 初诊事件">
    <header class="ai-diagnosis__head">
      <div>
        <h2>AI 初诊 · 待人工复核</h2>
        <p>告警触发时 Agent 只执行只读诊断，结论以 REVIEW 事件写回；人工确认前不会执行任何处置。</p>
      </div>
      <span class="ai-diagnosis__count">{{ items.length }} 条</span>
    </header>

    <p v-if="!items.length" class="ai-diagnosis__empty">
      暂无 AI 初诊事件（需模型可用且命中告警）。
    </p>

    <ul v-else class="ai-diagnosis__list">
      <li v-for="event in items" :key="event.id ?? `${event.taskId}-${event.at}`">
        <div class="ai-diagnosis__row">
          <InspectorSeverityTag :value="event.severity || 'INFO'" />
          <span class="ai-diagnosis__target">{{ event.target || event.taskId || '未标注目标' }}</span>
          <time class="ai-diagnosis__time">{{ formatTime(event.at ?? event.createdAt) }}</time>
        </div>
        <p class="ai-diagnosis__claim">{{ event.agentClaim || event.reason || 'Agent 未形成文字结论' }}</p>
        <p v-if="event.recommendation" class="ai-diagnosis__advice">{{ event.recommendation }}</p>
        <div class="ai-diagnosis__footer">
          <span class="ai-diagnosis__badge">REVIEW · 仅只读</span>
          <RouterLink
            v-if="event.id != null"
            class="ai-diagnosis__link"
            :to="`/inspector/events/${event.id}`"
          >查看事件详情</RouterLink>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import InspectorSeverityTag from './InspectorSeverityTag.vue'

const props = defineProps({
  events: { type: Array, default: () => [] }
})

const items = computed(() => props.events
  .filter(event => event?.status === 'REVIEW' && event?.requiresHuman === true)
  .slice(0, 3)
)

function formatTime(raw) {
  if (raw == null) return '—'
  const stamp = typeof raw === 'number' ? raw : Date.parse(raw)
  if (Number.isNaN(stamp)) return '—'
  try {
    return new Date(stamp).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
    })
  } catch {
    return '—'
  }
}
</script>

<style scoped>
.ai-diagnosis {
  display: grid;
  gap: 14px;
  padding: 20px;
  border: 1px solid var(--smart-border);
  border-radius: 12px;
  background: var(--smart-bg);
}

.ai-diagnosis__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.ai-diagnosis__head h2 {
  margin: 0;
  font-size: 16px;
}

.ai-diagnosis__head p {
  margin: 6px 0 0;
  color: var(--smart-muted);
  font-size: 13px;
}

.ai-diagnosis__count {
  flex: none;
  padding: 4px 10px;
  border: 1px solid var(--smart-border);
  border-radius: 999px;
  color: var(--smart-muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.ai-diagnosis__empty {
  margin: 0;
  color: var(--smart-muted);
  font-size: 13px;
}

.ai-diagnosis__list {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ai-diagnosis__list li {
  display: grid;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--smart-border);
  border-radius: 10px;
  background: var(--smart-surface, transparent);
}

.ai-diagnosis__row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ai-diagnosis__target {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--smart-primary-strong);
  font-family: var(--font-mono);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-diagnosis__time {
  flex: none;
  color: var(--smart-muted);
  font-size: 12px;
}

.ai-diagnosis__claim {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
}

.ai-diagnosis__advice {
  margin: 0;
  color: var(--smart-muted);
  font-size: 13px;
  line-height: 1.6;
}

.ai-diagnosis__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.ai-diagnosis__badge {
  padding: 3px 8px;
  border: 1px solid var(--smart-border);
  border-radius: 6px;
  color: var(--smart-muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.ai-diagnosis__link {
  color: var(--smart-primary-strong);
  font-size: 13px;
  text-decoration: none;
}

.ai-diagnosis__link:hover {
  text-decoration: underline;
}
</style>
