<template>
  <nav class="space-switcher" aria-label="工作空间切换">
    <RouterLink :to="personalTarget" :aria-current="!team ? 'page' : undefined" :class="{ selected: !team }">个人空间</RouterLink>
    <RouterLink :to="teamTarget" :aria-current="team ? 'page' : undefined" :class="{ selected: team }">团队空间</RouterLink>
  </nav>
</template>
<script setup>
import { computed, reactive, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

const STORAGE_KEY = 'smartops:space-routes'
const route = useRoute()
const team = computed(() => route.meta.space === 'team')
const lastPaths = reactive({ personal: '/', team: '/teams' })

try {
  const saved = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || '{}')
  if (typeof saved.personal === 'string' && saved.personal.startsWith('/')) lastPaths.personal = saved.personal
  if (typeof saved.team === 'string' && saved.team.startsWith('/teams')) lastPaths.team = saved.team
} catch {}

const personalTarget = computed(() => team.value ? lastPaths.personal : route.fullPath)
const teamTarget = computed(() => team.value ? route.fullPath : lastPaths.team)

watch(() => route.fullPath, fullPath => {
  lastPaths[team.value ? 'team' : 'personal'] = fullPath
  try { window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(lastPaths)) } catch {}
}, { immediate: true })
</script>
<style scoped>
.space-switcher{display:flex;gap:4px;padding:3px;border:1px solid var(--smart-border);border-radius:10px;background:var(--smart-surface);flex-shrink:0}
.space-switcher a{display:flex;align-items:center;justify-content:center;min-height:38px;padding:4px 12px;border-radius:7px;color:var(--smart-muted);text-decoration:none;font-size:13px;font-weight:600;white-space:nowrap}
.space-switcher a.selected{color:var(--smart-primary-strong);background:var(--smart-surface-soft,var(--smart-bg));box-shadow:inset 0 0 0 1px var(--smart-border)}
.space-switcher a:focus-visible{outline:2px solid var(--smart-primary-strong);outline-offset:2px}
</style>
