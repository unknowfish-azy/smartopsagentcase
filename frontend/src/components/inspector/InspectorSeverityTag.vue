<template><span class="severity" :class="level.toLowerCase()">{{ level }}</span></template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ value: { type: String, default: 'INFO' } })
const level = computed(() => props.value || 'INFO')
</script>
<style scoped>
.severity{display:inline-flex;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:700;background:var(--ds-pill-info-bg);color:var(--smart-muted)}.warning,.warn{background:var(--ds-pill-warning-bg);color:var(--ds-semantic-warning)}.high{background:var(--ds-pill-danger-bg);color:var(--ds-semantic-danger)}.critical,.violation,.rejected{background:var(--ds-pill-danger-bg);color:var(--ds-semantic-danger)}.pass,.info{background:var(--ds-pill-success-bg);color:var(--ds-semantic-success)}
</style>
