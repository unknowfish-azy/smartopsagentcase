<!--
  FieldSearch.vue — 知识空间场搜索浮层（B2）。
  Ctrl+K 唤起，输入实时过滤 737 条知识条目（标题/域名/内容），
  选中后聚焦对应平面并关闭。
-->
<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  query: { type: String, default: '' },
  results: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:query', 'select', 'close'])

const inputRef = ref(null)
const activeIndex = ref(0)

watch(() => props.results, () => { activeIndex.value = 0 })

// 打开时自动聚焦输入框
watch(inputRef, el => {
  if (el) nextTick(() => el.focus())
})

function onInput (e) {
  emit('update:query', e.target.value)
}
function onKeyDown (e) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, props.results.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const r = props.results[activeIndex.value]
    if (r) emit('select', r)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  }
}
</script>

<template>
  <div class="fs-overlay" @click.self="emit('close')">
    <div class="fs-panel" role="dialog" aria-label="搜索知识">
      <div class="fs-input-wrap">
        <span class="fs-icon" aria-hidden="true">⌕</span>
        <input
          ref="inputRef"
          type="text"
          class="fs-input"
          :value="query"
          placeholder="搜索知识条目（标题 / 域名 / 内容）…"
          @input="onInput"
          @keydown="onKeyDown"
        />
        <kbd class="fs-kbd">Esc</kbd>
      </div>

      <ul v-if="results.length" class="fs-results">
        <li
          v-for="(r, i) in results"
          :key="r.id"
          class="fs-item"
          :class="{ 'fs-item--active': i === activeIndex }"
          @click="emit('select', r)"
          @mouseenter="activeIndex = i"
        >
          <span class="fs-domain">{{ r.domain }}</span>
          <span class="fs-title">{{ r.title }}</span>
        </li>
      </ul>
      <p v-else-if="query" class="fs-empty">无匹配结果</p>
      <p v-else class="fs-hint">输入关键词开始搜索，↑↓ 选择，Enter 跳转</p>
    </div>
  </div>
</template>

<style scoped>
.fs-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 70;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 12vh;
}
.fs-panel {
  width: min(560px, 92vw);
  background: var(--ds-surface-raised, #14181f);
  border: 1px solid var(--ds-color-border);
  border-radius: 10px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  overflow: hidden;
  animation: fs-pop .18s ease;
}
@keyframes fs-pop {
  from { transform: translateY(-8px); opacity: 0; }
  to   { transform: translateY(0); opacity: 1; }
}
.fs-input-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--ds-color-border);
}
.fs-icon {
  color: var(--ds-accent, #7ad7f5);
  font-size: 18px;
}
.fs-input {
  flex: 1;
  border: 0;
  background: transparent;
  color: var(--ds-color-text);
  font: 14px var(--ds-font-cn);
  outline: none;
}
.fs-kbd {
  font: 10px var(--ds-font-mono);
  color: var(--ds-color-muted);
  padding: 2px 6px;
  border: 1px solid var(--ds-color-border);
  border-radius: 3px;
}
.fs-results {
  list-style: none;
  margin: 0;
  padding: 6px;
  max-height: 50vh;
  overflow-y: auto;
}
.fs-item {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 6px;
  cursor: pointer;
}
.fs-item--active,
.fs-item:hover {
  background: color-mix(in srgb, var(--ds-accent) 14%, transparent);
}
.fs-domain {
  color: var(--ds-accent, #7ad7f5);
  font: 10px var(--ds-font-mono);
  flex-shrink: 0;
  min-width: 64px;
}
.fs-title {
  color: var(--ds-color-text);
  font: 13px var(--ds-font-cn);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fs-empty,
.fs-hint {
  margin: 0;
  padding: 16px;
  color: var(--ds-color-muted);
  font: 12px var(--ds-font-cn);
  text-align: center;
}
</style>
