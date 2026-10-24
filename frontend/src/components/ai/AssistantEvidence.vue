<template>
  <div v-if="message.providerName || message.model || message.citations?.length" class="assistant-evidence">
    <p v-if="message.providerName || message.model" class="assistant-evidence__provider">{{ message.providerName }}<span v-if="message.model"> · {{ message.model }}</span></p>
    <details v-if="message.citations?.length">
      <summary>参考来源（{{ message.citations.length }}）</summary>
      <ul>
        <li v-for="(citation, index) in message.citations" :key="index">
          <strong>{{ citation.title || citation.id || '参考资料' }}</strong>
          <span v-if="citation.source" class="assistant-evidence__source">{{ citation.source }}</span>
          <p v-if="citation.snippet">{{ citation.snippet }}</p>
        </li>
      </ul>
    </details>
  </div>
</template>

<script setup>
defineProps({ message: { type: Object, required: true } })
</script>

<style scoped>
.assistant-evidence { min-width: 0; margin-top: 8px; font-size: 11px; line-height: 1.6; color: var(--smart-muted); overflow-wrap: anywhere; white-space: normal; }
.assistant-evidence p { margin: 4px 0; white-space: pre-wrap; }
.assistant-evidence summary { display: list-item; min-height: 32px; cursor: pointer; color: var(--smart-primary-strong); }
.assistant-evidence summary:focus-visible { outline: 2px solid var(--smart-primary-strong); }
.assistant-evidence ul { margin: 0; padding-left: 16px; }
.assistant-evidence li + li { margin-top: 8px; }
.assistant-evidence__source { display: block; }
</style>
