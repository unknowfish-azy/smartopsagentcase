<template>
  <section class="shared-knowledge">
    <header class="page-header">
      <div>
        <p class="eyebrow">SHARED KNOWLEDGE · 全员只读</p>
        <h1>共享知识</h1>
        <p class="muted">来自聊天反馈的复核结论，经人工审核后才在这里对所有用户可见。未审核内容不会出现在本页面。</p>
      </div>
      <button type="button" class="ghost" :disabled="loading" @click="load">{{ loading ? '读取中…' : '刷新' }}</button>
    </header>
    <nav class="zone-tabs" aria-label="Knowledge zones">
      <RouterLink class="zone-tab" to="/knowledge/space">系统知识库</RouterLink>
      <RouterLink class="zone-tab" to="/knowledge/personal">我的知识库</RouterLink>
      <RouterLink class="zone-tab active" to="/knowledge/shared">共享知识</RouterLink>
      <RouterLink class="zone-tab" to="/knowledge/review">待审核候选</RouterLink>
    </nav>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="loading && !items.length" class="empty">正在读取共享知识…</div>
    <div v-else-if="!items.length" class="empty">还没有审核通过的共享知识。聊天反馈复核后需人工审核才会发布到这里。</div>
    <div v-else class="entry-grid">
      <article v-for="item in items" :key="item.id" class="entry" tabindex="0" @click="active = item" @keydown.enter="active = item">
        <h2>{{ item.title }}</h2>
        <p>{{ item.summary || '—' }}</p>
        <small>{{ item.sourceType }} · 发布于 {{ item.publishedAt }}</small>
      </article>
    </div>
    <section v-if="active" class="detail" aria-label="共享知识详情">
      <header><h2>{{ active.title }}</h2><button type="button" aria-label="关闭详情" @click="active = null">×</button></header>
      <div class="markdown" v-html="renderMarkdown(active.contentMarkdown || '')"></div>
      <p v-if="active.citationsJson" class="citations">检索引用：{{ active.citationsJson }}</p>
      <p v-else class="citations">无可展示的真实引用。</p>
    </section>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { listSharedKnowledge } from '../../api/chatFeedback.ts'
import { renderMarkdown } from '../../components/ai/markdown.js'
/* v-html 后代不吃 scoped 属性，必须引入全局 markdown.css（346ab03 的同款修复） */
import '../../components/ai/markdown.css'

const items = ref([]), active = ref(null), loading = ref(false), error = ref('')
const unwrap = response => response?.data ?? response
async function load() {
  loading.value = true; error.value = ''
  try {
    const data = unwrap(await listSharedKnowledge(100))
    items.value = Array.isArray(data) ? data : (data?.items || [])
  } catch (cause) { error.value = cause.message || '读取共享知识失败' }
  finally { loading.value = false }
}
onMounted(load)
</script>

<style scoped>
.shared-knowledge { color: var(--smart-text); }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 18px; }
.eyebrow { margin: 0 0 8px; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .14em; }
h1 { margin: 0; font-size: 26px; font-weight: 500; }
h2 { margin: 0; font-size: 15px; font-weight: 500; }
.muted { color: var(--smart-muted); font-size: 12px; }
.ghost, .detail header button { min-height: 30px; padding: 3px 10px; border: 1px solid var(--smart-border); border-radius: 6px; background: transparent; color: var(--smart-muted); cursor: pointer; }
.zone-tabs { display: flex; gap: 16px; flex-wrap: wrap; margin: 18px 0; border-bottom: 1px solid var(--smart-border); }
.zone-tab { padding: 8px 0; color: var(--smart-muted); font-size: 13px; text-decoration: none; }
.zone-tab.active { color: var(--smart-primary-strong); border-bottom: 2px solid currentColor; }
.entry-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.entry { padding: 14px; border: 1px solid var(--smart-border); border-radius: 8px; background: var(--smart-surface); cursor: pointer; }
.entry p { margin: 8px 0; color: var(--smart-muted); font-size: 12px; line-height: 1.6; }
.entry small { color: var(--smart-muted); font: 10px var(--font-mono); }
.empty, .error { padding: 28px; text-align: center; color: var(--smart-muted); border: 1px dashed var(--smart-border); border-radius: 8px; }
.error { color: var(--ds-semantic-danger); }
.detail { margin-top: 18px; padding: 18px; border: 1px solid var(--smart-border); border-radius: 10px; background: var(--smart-surface); }
.detail header { display: flex; justify-content: space-between; align-items: center; }
.markdown { margin-top: 12px; font-size: 13px; line-height: 1.7; }
.citations { margin: 14px 0 0; color: var(--smart-muted); font: 10px/1.6 var(--font-mono); overflow-wrap: anywhere; }
</style>
