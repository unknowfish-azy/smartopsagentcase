<template><div class="summary"><article v-for="item in items" :key="item.key"><span>{{ item.label }}</span><strong>{{ summary[item.key] ?? 0 }}</strong></article></div></template>
<script setup>
defineProps({ summary: { type: Object, default: () => ({}) } })
const items=[['total','Total'],['pass','PASS'],['warning','WARN'],['high','HIGH'],['critical','CRITICAL']].map(([key,label])=>({key,label}))
</script>
<style scoped>
.summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.summary article {
  padding: 18px;
  background: var(--smart-bg);
  border: 1px solid var(--smart-border);
  border-radius: 8px;
}

.summary span {
  display: block;
  color: var(--smart-muted);
  font-size: 12px;
}

.summary strong {
  display: block;
  margin-top: 8px;
  color: var(--smart-primary-strong);
  font-family: var(--font-mono);
  font-size: 28px;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 800px) {
  .summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
