<template>
  <!-- 窄屏退化（门禁 4）：<768px 时工坊退化为工位状态列表 -->
  <div class="ws-fallback" role="list" aria-label="Agent 工坊 · 工位状态">
    <p class="ws-fallback-note">
      窄屏视图 · ISO WORKSHOP 退化为列表
      <span v-if="rehearsal" class="ws-fallback-badge">REHEARSAL · 演练构成</span>
    </p>
    <ul>
      <li v-for="tool in tools" :key="tool.en" role="listitem">
        <span
          class="ws-lamp"
          :class="{ 'is-on': lampOf(tool).on }"
          :data-tone="tool.tone"
          aria-hidden="true"
        ></span>
        <span class="ws-name">
          <b>{{ tool.cn }}</b>
          <i>{{ tool.en }}</i>
        </span>
        <span class="ws-event">{{ lampOf(tool).text }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
const props = defineProps({
  tools: { type: Array, required: true },
  /** deskActivity(loops) 的结果 */
  activity: { type: Array, default: () => [] },
  /** 数据源非 live 时整列呈演练态 */
  rehearsal: { type: Boolean, default: false }
})

function lampOf(tool) {
  const id = String(tool.en || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  const hit = props.activity.find(item => item.deskId === id)
  if (props.rehearsal || !hit) return { on: false, text: '空闲 · 无事件' }
  return {
    on: true,
    text: `${hit.loopId} · ${hit.stage}${Number.isFinite(hit.durationMs) ? ` · ${(hit.durationMs / 1000).toFixed(1)}s` : ''}`
  }
}
</script>

<style scoped>
.ws-fallback {
  width: 100%;
  border: 1px solid var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  border-radius: var(--ds-radius-sm, 4px);
  padding: 12px;
  background: var(--ds-surface-raised, #151A21);
}

.ws-fallback-note {
  margin: 0 0 10px;
  color: var(--fab-paper-46, rgba(232, 242, 247, 0.46));
  font: 9px/1.5 var(--fab-mono, ui-monospace, monospace);
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.ws-fallback-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 6px;
  border: 1px solid color-mix(in srgb, var(--fab-plum, #a383a6) 50%, transparent);
  border-radius: 2px;
  color: var(--fab-plum, #a383a6);
}

.ws-fallback ul {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.ws-fallback li {
  display: grid;
  grid-template-columns: 14px 1fr auto;
  align-items: center;
  gap: 8px;
}

.ws-lamp {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
}
.ws-lamp[data-tone='sage'].is-on { background: var(--fab-sage, #8bcfb4); }
.ws-lamp[data-tone='clay'].is-on { background: var(--fab-clay, #2496ed); }
.ws-lamp[data-tone='butter'].is-on { background: var(--fab-butter, #d9b96d); }
.ws-lamp[data-tone='apricot'].is-on { background: var(--fab-apricot, #7ad7f5); }
.ws-lamp[data-tone='gaze'].is-on { background: var(--fab-gaze, #7ad7f5); }
.ws-lamp[data-tone='plum'].is-on { background: var(--fab-plum, #9b8cf0); }

.ws-name b {
  display: block;
  color: var(--fab-paper, #e8f2f7);
  font: 11px/1.3 var(--fab-mono, ui-monospace, monospace);
}
.ws-name i {
  display: block;
  color: var(--fab-paper-46, rgba(232, 242, 247, 0.46));
  font: 8px/1.3 var(--fab-mono, ui-monospace, monospace);
  font-style: normal;
  letter-spacing: 0.12em;
}

.ws-event {
  color: var(--fab-paper-72, rgba(232, 242, 247, 0.72));
  font: 9px/1.4 var(--fab-mono, ui-monospace, monospace);
}
</style>
