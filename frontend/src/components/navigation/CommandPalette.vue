<template>
  <button class="nav-discovery-trigger" type="button" aria-label="搜索页面" @click="open">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg>
    <span>寻找下一站</span><kbd>⌘ / Ctrl K</kbd>
  </button>
  <dialog ref="dialog" class="nav-discovery" aria-labelledby="discovery-title" @close="afterClose" @click="backdrop" @keydown="keys">
    <header><div><small>SMARTOPS / NAVIGATION INDEX</small><h2 id="discovery-title">你想去哪里？</h2></div><button type="button" aria-label="关闭页面搜索" @click="close">Esc</button></header>
    <div class="nav-discovery-search"><span aria-hidden="true">↳</span><input ref="input" v-model="query" aria-label="搜索页面名称" placeholder="搜索页面、工具或英文名称…" autocomplete="off" role="combobox" aria-controls="discovery-results" aria-expanded="true" :aria-activedescendant="results.length ? `discovery-${selected}` : undefined" /></div>
    <div class="nav-discovery-meta"><span>{{ query ? '搜索结果' : (recentPaths.length ? '最近访问优先' : '可访问页面') }}</span><span>{{ results.length }} DESTINATIONS</span></div>
    <div id="discovery-results" class="nav-discovery-results" role="listbox" aria-label="页面结果">
      <div v-for="(item, index) in results" :id="`discovery-${index}`" :key="item.to" role="option" :aria-selected="selected === index" class="nav-discovery-result" :class="{ 'is-selected': selected === index }" @mousemove="selected = index" @click="go(item)">
        <span class="nav-discovery-index">{{ String(index + 1).padStart(2, '0') }}</span><div><strong>{{ item.title }}<em v-if="item.recent" class="nav-discovery-recent">RECENT</em></strong><small>{{ item.group }} / {{ item.label }}</small></div><span class="nav-discovery-arrow" aria-hidden="true">↗</span>
      </div>
      <p v-if="!results.length" class="nav-discovery-empty">没有匹配页面，试试“知识”或“模型”。</p>
    </div>
    <footer><span>↑ ↓ 选择 · Enter 前往</span><span>ESC 返回工作台</span></footer>
    <p v-if="failure" role="alert">{{ failure }}</p>
  </dialog>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { rememberRecentPath, restoreRecentPaths, searchEntries } from '../../navigation/navigationDiscovery.js'
const props = defineProps({ entries: { type: Array, required: true } })
const router = useRouter()
const dialog = ref(null), input = ref(null), query = ref(''), selected = ref(0), failure = ref('')
const recentPaths = ref([])
const results = computed(() => {
  const matches = searchEntries(props.entries, query.value)
  if (query.value.trim()) return matches
  const byPath = new Map(props.entries.map(item => [item.to, item]))
  const recent = recentPaths.value.map(path => byPath.get(path)).filter(Boolean)
  return [
    ...recent.map(item => ({ ...item, recent: true })),
    ...matches.filter(item => !recentPaths.value.includes(item.to))
  ]
})
let origin
watch(results, () => { selected.value = 0 })
async function open() {
  if (dialog.value.open) return
  origin = document.activeElement
  query.value = ''; failure.value = ''; selected.value = 0
  recentPaths.value = restoreRecentPaths(localStorage.getItem('smartops:palette-recent'), props.entries)
  dialog.value.showModal()
  await nextTick(); input.value?.focus()
}
function close() { dialog.value?.close() }
function afterClose() { if (origin?.isConnected) origin.focus() }
function backdrop(event) { if (event.target === dialog.value) { const r = dialog.value.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) close() } }
async function go(item) {
  try {
    localStorage.setItem('smartops:palette-recent', rememberRecentPath(localStorage.getItem('smartops:palette-recent'), item.to, props.entries))
    await router.push(item.to); close()
  } catch { failure.value = '页面跳转失败，请重试。' }
}
async function keys(event) {
  if (event.isComposing) return
  if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
    event.preventDefault()
    if (!results.value.length) return
    selected.value = (selected.value + (event.key === 'ArrowDown' ? 1 : -1) + results.value.length) % results.value.length
    await nextTick(); document.getElementById(`discovery-${selected.value}`)?.scrollIntoView({ block: 'nearest' })
  } else if (event.key === 'Enter' && event.target === input.value && results.value[selected.value]) {
    event.preventDefault(); go(results.value[selected.value])
  }
}
function shortcut(event) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !event.isComposing) {
    // 只拦"可见"的遮罩/对话框：聊天页的 Element Plus 抽屉常驻 DOM（display:none），
    // 若只看 aria-modal 属性存在会永远打不开命令面板。
    const blocker = document.querySelector('dialog[open], [aria-modal="true"]')
    if (!dialog.value.open && blocker && blocker.getClientRects().length) return
    event.preventDefault(); dialog.value.open ? close() : open()
  }
}
onMounted(() => window.addEventListener('keydown', shortcut))
onBeforeUnmount(() => { window.removeEventListener('keydown', shortcut); close() })
</script>
<style scoped>
.nav-discovery-trigger { display:flex; align-items:center; gap:10px; min-height:44px; padding:8px 12px; border:1px solid var(--smart-border); background:var(--smart-surface); color:var(--smart-text); border-radius:4px; cursor:pointer; white-space:nowrap; }
.nav-discovery-trigger svg { width:17px; height:17px; fill:none; stroke:currentColor; stroke-width:1.5; }
.nav-discovery-trigger span { font-size:12px; }
kbd { font:9px var(--font-mono); color:var(--smart-muted); border-left:1px solid var(--smart-border); padding-left:10px; }
.nav-discovery { width:min(680px,calc(100vw - 32px)); max-height: min(740px,85dvh); padding:0; margin:8dvh auto auto; border:1px solid var(--smart-border); border-top:2px solid var(--smart-primary-strong); border-radius:4px; background:var(--smart-surface); color:var(--smart-text); box-shadow:0 32px 100px #0008; }
.nav-discovery::backdrop { background:#02070cc9; }
.nav-discovery header { display:flex; justify-content:space-between; align-items:center; padding:28px 28px 20px; }
.nav-discovery header small { font:9px var(--font-mono); letter-spacing:.15em; color:var(--smart-primary-strong); }
.nav-discovery h2 { margin:12px 0 0; font-size:30px; font-weight:500; }
.nav-discovery header button { min-width:44px; min-height:44px; color:var(--smart-muted); border:1px solid var(--smart-border); background:transparent; border-radius:4px; }
.nav-discovery-search { display:flex; gap:16px; align-items:center; margin:0 28px; border-bottom:1px solid var(--smart-primary-strong); }
.nav-discovery-search>span { color:var(--smart-primary-strong); font-size:26px; }
.nav-discovery input { width:100%; min-height:56px; border:0; background:transparent; color:var(--smart-text); font:16px var(--font-cn); outline-offset:-2px; }
.nav-discovery-meta,.nav-discovery footer { display:flex; justify-content:space-between; gap:12px; padding:18px 28px; color:var(--smart-muted); font:10px var(--font-mono); }
.nav-discovery-results { max-height:42dvh; overflow:auto; padding:0 12px 12px; }
.nav-discovery-result { display:grid; grid-template-columns:38px 1fr 24px; align-items:center; gap:12px; padding:14px 16px; min-height:64px; border-left:2px solid transparent; cursor:pointer; transition:background 140ms; }
.nav-discovery-result:hover,.nav-discovery-result.is-selected { background:var(--smart-primary-soft); border-left-color:var(--smart-primary-strong); }
.nav-discovery-index { color:var(--smart-muted); font:10px var(--font-mono); }
.nav-discovery-result strong { font-size:14px; font-weight:500; }
.nav-discovery-recent { margin-left:8px; padding:2px 5px; border:1px solid var(--smart-primary-strong); border-radius:2px; color:var(--smart-primary-strong); font:8px var(--font-mono); font-style:normal; letter-spacing:.08em; vertical-align:2px; }
.nav-discovery-result small { display:block; margin-top:5px; font:9px var(--font-mono); color:var(--smart-muted); }
.nav-discovery-arrow { color:var(--smart-primary-strong); }
.nav-discovery footer { border-top:1px solid var(--smart-border); }
.nav-discovery-empty { padding:30px 16px; color:var(--smart-muted); }
@media(max-width:767px) { .nav-discovery-trigger kbd,.nav-discovery-trigger span { display:none; } .nav-discovery header { padding:20px; } .nav-discovery h2 { font-size:24px; } }
@media(prefers-reduced-motion:reduce) { * { transition:none!important; } }
</style>
