<template>
  <section class="list-panel" aria-label="运行记录列表">
    <div v-if="guideMode" class="guide-banner" role="note">
      <strong>当前显示演示数据</strong>
      <span>仅用于了解运行证据，不来自真实环境，不写入数据库，也不计入运行统计。</span>
    </div>
    <header class="panel-title">
      <div>
        <p class="eyebrow">RECORDS</p>
        <h2>执行记录</h2>
      </div>
      <span>{{ page.total }} 条<span v-if="guideMode">（演示）</span>
      </span>
    </header>
    <div v-if="loading && !page.items.length" class="state">正在读取运行记录…</div>
    <div v-else-if="!page.items.length" class="state">
      <strong>暂无匹配记录</strong>
      <p>远程工具执行完成后，记录会自动保存在这里。</p>
    </div>
    <button v-for="run in page.items" :key="run.id" class="run-row" :class="{ active: selectedId === run.id }" type="button" @click="$emit('select', run.id)">
      <span class="row-top">
        <b>{{ run.toolId }}</b>
        <i :class="runStatusClass(run.status)">{{ run.isGuide ? '演示数据' : runStatusLabel(run.status) }}</i>
      </span>
      <code>{{ run.traceId }}</code>
      <span class="row-meta">
        <time>{{ formatRunTime(run.startedAt) }}</time>
        <span>{{ formatDuration(run.startedAt, run.endedAt) }}</span>
      </span>
      <small>{{ run.commandCount }} 条命令<span v-if="run.failedCommandCount"> · {{ run.failedCommandCount }} 条失败</span>
      </small>
    </button>
    <footer v-if="page.total > page.pageSize" class="pagination">
      <button :disabled="page.page <= 1" @click="$emit('load', page.page - 1)">上一页</button>
      <span>第 {{ page.page }} / {{ totalPages }} 页</span>
      <button :disabled="page.page >= totalPages" @click="$emit('load', page.page + 1)">下一页</button>
    </footer>
  </section>
</template>

<script setup>
import { formatDuration, formatRunTime, runStatusClass, runStatusLabel } from './operationRunHistory.js'

defineProps({
  page: { type: Object, required: true },
  loading: { type: Boolean, default: false },
  guideMode: { type: Boolean, default: false },
  selectedId: { type: [Number, String], default: null },
  totalPages: { type: Number, default: 1 }
})
defineEmits(['select', 'load'])
</script>

<style scoped>
.list-panel {
  min-width: 0;
  border: 1px solid var(--smart-border);
  border-radius: 12px;
  background: var(--smart-surface);
  min-height: 0;
  overflow: hidden auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}
.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 20px;
  border-bottom: 1px solid var(--smart-border);
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--smart-surface);
}
.eyebrow {
  margin: 0 0 9px;
  color: var(--smart-primary-strong);
  font: 10px var(--font-mono);
  letter-spacing: .14em;
}
h2 {
  margin: 0;
  font-weight: 560;
}
.panel-title h2 {
  font-size: 18px;
}
.panel-title>span {
  color: var(--smart-muted);
  font-size: 11px;
}
.state {
  padding: 60px 24px;
  text-align: center;
  color: var(--smart-muted);
  font-size: 12px;
}
.state strong {
  color: var(--smart-text);
  font-size: 14px;
}
.guide-banner {
  display: grid;
  gap: 5px;
  padding: 12px 20px;
  border-bottom: 1px solid color-mix(in srgb,#d69a50 45%,var(--smart-border));
  background: color-mix(in srgb,#d69a50 8%,var(--smart-surface));
  font-size: 11px;
}
.guide-banner strong {
  color: #d69a50;
}
.guide-banner span {
  color: var(--smart-muted);
  line-height: 1.5;
}
.run-row {
  display: block;
  width: 100%;
  padding: 17px 20px;
  border: 0;
  border-bottom: 1px solid var(--smart-border);
  text-align: left;
  color: var(--smart-text);
  background: transparent;
  cursor: pointer;
  transition: background 150ms;
}
.run-row:hover,.run-row.active {
  background: color-mix(in srgb,var(--smart-primary-strong) 9%,transparent);
}
.run-row.active {
  box-shadow: inset 3px 0 var(--smart-primary-strong);
}
.row-top,.row-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}
.status {
  font-style: normal;
  font-size: 10px;
  border: 1px solid currentColor;
  border-radius: 999px;
  padding: 4px 8px;
}
.status-unknown {
  color: var(--smart-muted);
}
.status-success {
  color: #4fb58b;
}
.status-failed {
  color: #e06b72;
}
.status-running {
  color: #d69a50;
}
/* 浅色主题下原高饱和色对比度不足 4.5:1，改用深一档同色系（axe color-contrast 复核通过）。 */
[data-theme='light'] .status-success { color: #0f7b52; }
[data-theme='light'] .status-failed { color: #b42318; }
[data-theme='light'] .status-running { color: #8a5a11; }
[data-theme='light'] .guide-banner strong { color: #8a5a11; }
.status-cancelled {
  color: var(--smart-muted);
}
.run-row>code {
  display: block;
  margin: 11px 0;
  color: var(--smart-muted);
  font: 11px var(--font-mono);
  overflow-wrap: anywhere;
}
.row-meta,.run-row small {
  color: var(--smart-muted);
  font-size: 10px;
}
.run-row small {
  display: block;
  margin-top: 8px;
}
.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px;
}
.pagination button {
  min-height: 40px;
  border: 1px solid var(--smart-border);
  border-radius: 8px;
  padding: 6px 10px;
  color: var(--smart-text);
  background: var(--smart-surface);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  min-height: 34px;
}
.pagination span {
  font-size: 10px;
  color: var(--smart-muted);
}
button:disabled {
  opacity: .45;
  cursor: wait;
}
button:focus-visible {
  outline: 2px solid var(--smart-primary-strong);
  outline-offset: 3px;
}
.list-panel > footer.pagination {
  position: sticky;
  bottom: 0;
  z-index: 2;
  border-top: 1px solid var(--smart-border);
  background: var(--smart-surface);
}
@media (max-width: 800px) {
  .list-panel {
    overflow: visible;
  }
  .panel-title, .list-panel > footer.pagination {
    position: static;
  }
}
@media(prefers-reduced-motion:reduce) {
  .run-row {
    transition: none;
  }
}
</style>
