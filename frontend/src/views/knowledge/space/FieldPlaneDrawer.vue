<!--
  FieldPlaneDrawer.vue — 知识平面详情侧拉抽屉（B1）。
  点击平面后从右侧滑出，展示 entry 标题、域名、类型、内容片段、证据数。
  Esc 或点击关闭按钮关闭。
-->
<script setup>
import { computed } from 'vue'

const props = defineProps({
  entry: { type: Object, required: true },
  domain: { type: Object, default: null },
  evidenceCount: { type: Number, default: 0 }
})

const emit = defineEmits(['close'])

const contentPreview = computed(() => {
  const c = String(props.entry?.content || '')
  return c.length > 600 ? c.slice(0, 600) + '…' : c
})

const entryType = computed(() => props.entry?.type || 'KNOWLEDGE')
</script>

<template>
  <div class="fpd-overlay" @click.self="emit('close')">
    <aside class="fpd-drawer" role="dialog" aria-label="知识条目详情">
      <header class="fpd-head">
        <div>
          <span class="fpd-domain">{{ domain?.label || entry.domain || '—' }}</span>
          <span class="fpd-type">{{ entryType }}</span>
        </div>
        <button type="button" class="fpd-close" aria-label="关闭" @click="emit('close')">✕</button>
      </header>

      <h2 class="fpd-title">{{ entry.title || '未命名条目' }}</h2>

      <div class="fpd-meta">
        <span>ID：{{ entry.id }}</span>
        <span>证据：{{ evidenceCount }} 条</span>
      </div>

      <div class="fpd-content">
        <h3>内容摘要</h3>
        <p>{{ contentPreview || '（无内容）' }}</p>
      </div>

      <footer class="fpd-foot">
        <span class="fpd-hint">按 Esc 关闭 · 点击平面外区域关闭</span>
      </footer>
    </aside>
  </div>
</template>

<style scoped>
.fpd-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 60;
  display: flex;
  justify-content: flex-end;
}
.fpd-drawer {
  width: min(420px, 90vw);
  height: 100%;
  background: var(--ds-surface-raised, #14181f);
  border-left: 1px solid var(--ds-color-border);
  display: flex;
  flex-direction: column;
  animation: fpd-slide-in .25s ease;
  overflow: hidden;
}
@keyframes fpd-slide-in {
  from { transform: translateX(100%); }
  to   { transform: translateX(0); }
}
.fpd-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--ds-color-border);
}
.fpd-domain {
  color: var(--ds-accent, #7ad7f5);
  font: 11px var(--ds-font-mono);
  letter-spacing: 0.06em;
  margin-right: 8px;
}
.fpd-type {
  color: var(--ds-color-muted);
  font: 10px var(--ds-font-mono);
  padding: 2px 6px;
  border: 1px solid var(--ds-color-border);
  border-radius: 3px;
}
.fpd-close {
  width: 28px;
  height: 28px;
  border: 1px solid var(--ds-color-border);
  border-radius: 50%;
  background: transparent;
  color: var(--ds-color-muted);
  cursor: pointer;
  font-size: 13px;
  transition: all .15s;
}
.fpd-close:hover {
  border-color: var(--ds-accent);
  color: var(--ds-accent);
}
.fpd-title {
  margin: 16px;
  color: var(--ds-color-text);
  font: 600 17px/1.5 var(--ds-font-cn);
}
.fpd-meta {
  display: flex;
  gap: 16px;
  padding: 0 16px 12px;
  color: var(--ds-color-muted);
  font: 11px var(--ds-font-mono);
  border-bottom: 1px solid var(--ds-color-border);
}
.fpd-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.fpd-content h3 {
  margin: 0 0 8px;
  color: var(--ds-color-muted);
  font: 500 11px var(--ds-font-mono);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.fpd-content p {
  margin: 0;
  color: var(--ds-color-text);
  font: 13px/1.7 var(--ds-font-cn);
  white-space: pre-wrap;
  word-break: break-word;
}
.fpd-foot {
  padding: 10px 16px;
  border-top: 1px solid var(--ds-color-border);
}
.fpd-hint {
  color: var(--ds-color-muted);
  font: 10px var(--ds-font-mono);
  opacity: 0.7;
}
</style>
