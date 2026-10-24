<template>
  <nav class="space-switcher" aria-label="工作空间切换">
    <RouterLink to="/" :aria-current="!team ? 'page' : undefined" :class="{ selected: !team }">个人空间</RouterLink>
    <RouterLink to="/teams" :aria-current="team ? 'page' : undefined" :class="{ selected: team }">团队空间</RouterLink>
  </nav>
</template>
<script setup>
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
const route = useRoute()
const team = computed(() => route.meta.space === 'team')
</script>
<style scoped>
.space-switcher{display:flex;gap:4px;padding:3px;border:1px solid var(--smart-border);border-radius:10px;background:var(--smart-surface);flex-shrink:0}
.space-switcher a{display:flex;align-items:center;justify-content:center;min-height:38px;padding:4px 12px;border-radius:7px;color:var(--smart-muted);text-decoration:none;font-size:13px;font-weight:600;white-space:nowrap}
.space-switcher a.selected{color:var(--smart-primary-strong);background:var(--smart-surface-soft,var(--smart-bg));box-shadow:inset 0 0 0 1px var(--smart-border)}
.space-switcher a:focus-visible{outline:2px solid var(--smart-primary-strong);outline-offset:2px}
</style>
