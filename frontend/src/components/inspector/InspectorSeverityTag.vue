<template><span class="severity" :class="level.toLowerCase()">{{ level }}</span></template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ value: { type: String, default: 'INFO' } })
const level = computed(() => props.value || 'INFO')
</script>
<style scoped>
.severity{display:inline-flex;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:700;background:#e2e8f0;color:#334155}.warning,.warn{background:#fef3c7;color:#92400e}.high{background:#ffedd5;color:#9a3412}.critical,.violation,.rejected{background:#fee2e2;color:#991b1b}.pass,.info{background:#dcfce7;color:#166534}
</style>
