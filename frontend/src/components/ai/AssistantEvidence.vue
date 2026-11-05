<template>
  <div v-if="message.providerName || message.model || message.citations?.length" class="assistant-evidence">
    <p v-if="message.providerName || message.model" class="assistant-evidence__provider">{{ message.providerName }}<span v-if="message.model"> · {{ message.model }}</span></p>
    <details v-if="message.citations?.length">
      <summary>参考来源（{{ message.citations.length }} 段 / {{ citationGroups.length }} 篇）</summary>
      <ul>
        <li v-for="group in citationGroups" :key="group.key">
          <strong>{{ group.title }}</strong>
          <span v-if="group.count > 1" class="assistant-evidence__count">{{ group.count }} 段命中</span>
          <span v-if="group.source" class="assistant-evidence__source">{{ group.source }}</span>
          <p v-if="group.snippet">{{ group.snippet }}</p>
        </li>
      </ul>
    </details>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ message: { type: Object, required: true } })

// 同一篇资料的多段引用合并成一条，避免“参考来源 5”全指向同一个文件。
const citationGroups = computed(() => {
  const groups = new Map()

  for (const citation of props.message.citations || []) {
    const key = citation.source || citation.title || `citation-${citation.citation_id ?? groups.size}`
    const existing = groups.get(key)

    if (existing) {
      existing.count += 1
      continue
    }

    groups.set(key, {
      key,
      title: citation.title || '参考资料',
      source: citation.source || '',
      snippet: citation.snippet || '',
      count: 1
    })
  }

  return [...groups.values()]
})
</script>

<style scoped>
.assistant-evidence { min-width: 0; margin-top: 8px; font-size: 11px; line-height: 1.6; color: var(--smart-muted); overflow-wrap: anywhere; white-space: normal; }
.assistant-evidence p { margin: 4px 0; white-space: pre-wrap; }
.assistant-evidence summary { display: list-item; min-height: 32px; cursor: pointer; color: var(--smart-primary-strong); }
.assistant-evidence summary:focus-visible { outline: 2px solid var(--smart-primary-strong); }
.assistant-evidence ul { margin: 0; padding-left: 16px; }
.assistant-evidence li + li { margin-top: 8px; }
.assistant-evidence__count { margin-left: 6px; color: var(--smart-muted); }
.assistant-evidence__source { display: block; }
</style>
