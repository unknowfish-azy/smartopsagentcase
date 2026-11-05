<template>
  <nav v-if="tabs.length" ref="root" class="admin-tabs" aria-label="已打开的标签页" @keydown="onKeydown">
    <div v-for="(tab, index) in tabs" :key="tab.path" class="admin-tab" :class="{ 'is-active': route.path === tab.path }">
      <RouterLink :to="tab.path" class="admin-tab-link" :tabindex="index === focusIndex ? 0 : -1" :aria-current="route.path === tab.path ? 'page' : undefined" @click="focusIndex = index">
        <span class="admin-tab-label">{{ tab.title }}</span>
      </RouterLink>
      <button v-if="tab.closable" type="button" class="admin-tab-close" :aria-label="`关闭标签页：${tab.title}`" @click.prevent.stop="close(tab)">×</button>
    </div>
  </nav>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { currentSession } from '../../security/session.js'
import { restoreTabPaths } from '../../navigation/navigationDiscovery.js'
import { adminTitle } from '../../adminNav.js'
const route = useRoute()
const router = useRouter()
const root = ref(null)
const tabs = ref([])
// 单一 Tab 停靠点（roving tabindex）：Tab 键只进入一次，方向键在标签之间移动焦点。
const focusIndex = ref(0)
const storageKey = computed(() => currentSession.value?.id != null ? `smartops:admin-tabs:${currentSession.value.id}` : null)
function restore() {
  let raw = null
  try { if (storageKey.value) raw = localStorage.getItem(storageKey.value) } catch {}
  tabs.value = restoreTabPaths(raw, adminTitle).map(path => ({ path, title: adminTitle[path], closable: path !== '/admin' }))
  sync()
}
function persist() {
  try { if (storageKey.value) localStorage.setItem(storageKey.value, JSON.stringify(tabs.value.map(tab => tab.path))) } catch {}
}
watch(storageKey, restore, { immediate: true })
watch(tabs, persist, { deep: true })

function sync() {
  const base = route.path.split('?')[0]
  if (!adminTitle[base]) return // 非菜单页面（如登录/账户安全）不进标签
  if (!tabs.value.some(tab => tab.path === base)) {
    tabs.value.push({ path: base, title: adminTitle[base], closable: base !== '/admin' })
  }
  const active = tabs.value.findIndex(tab => tab.path === base)
  if (active >= 0) focusIndex.value = active
}

function close(tab) {
  const index = tabs.value.findIndex(item => item.path === tab.path)
  if (index < 0) return
  tabs.value.splice(index, 1)
  if (route.path === tab.path) {
    const next = tabs.value[Math.max(0, index - 1)] || tabs.value[0]
    if (next) router.replace(next.path)
  }
  nextTick(() => root.value?.querySelectorAll('.admin-tab-link')[focusIndex.value]?.focus())
}

function onKeydown(event) {
  const links = Array.from(root.value?.querySelectorAll('.admin-tab-link') || [])
  const index = links.indexOf(event.target)
  if (index < 0) return
  let next = null
  if (event.key === 'ArrowRight') next = (index + 1) % links.length
  else if (event.key === 'ArrowLeft') next = (index - 1 + links.length) % links.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = links.length - 1
  if (next === null) return
  event.preventDefault()
  focusIndex.value = next
  links[next].focus()
}

watch(() => route.fullPath, sync, { immediate: true })
</script>

<style scoped>
.admin-tabs { gap:4px; }
.admin-tab { border-radius:4px 4px 0 0; border-bottom:2px solid transparent; }
.admin-tab.is-active { border-bottom-color:var(--smart-primary-strong); }
.admin-tab-label { font-size:12px; }
</style>
