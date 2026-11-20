<template>
  <section class="unified-retrieval">
    <header class="page-header">
      <div>
        <p class="eyebrow">UNIFIED RETRIEVAL · P0-1 统一语义检索</p>
        <h1>统一检索</h1>
        <p class="muted">聚合情景记忆 / 个人知识库 / 共享知识库三源召回，支持集合路由、相关度×置信度排序、低置信度拒答。</p>
      </div>
    </header>

    <!-- 搜索表单 -->
    <section class="search-panel">
      <div class="search-form">
        <input v-model="query" class="search-input" placeholder="输入检索文本，如：nginx 502" @keyup.enter="onSearch" />
        <button type="button" class="btn btn--primary" :disabled="searching || !query.trim()" @click="onSearch">
          {{ searching ? '检索中…' : '检索' }}
        </button>
      </div>
      <div class="search-options">
        <label class="option">
          <input type="checkbox" value="MEMORY" v-model="selectedCollections" />
          <span>情景记忆</span>
        </label>
        <label class="option">
          <input type="checkbox" value="PERSONAL_KNOWLEDGE" v-model="selectedCollections" />
          <span>个人知识</span>
        </label>
        <label class="option">
          <input type="checkbox" value="SHARED_KNOWLEDGE" v-model="selectedCollections" />
          <span>共享知识</span>
        </label>
        <span class="option-sep">|</span>
        <label class="option">
          <span>返回条数</span>
          <input type="number" v-model.number="limit" min="1" max="50" class="limit-input" />
        </label>
      </div>
    </section>

    <!-- 结果 -->
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="!searched" class="empty">输入关键词开始检索</div>
    <div v-else-if="result?.lowConfidence" class="empty empty--warn">
      <strong>低置信度拒答</strong>
      <p>所有结果的相关度×置信度低于阈值 0.15，未返回任何结果。这是 P0-1 的安全机制：检索证据不等于事实，不确定时明确说不知道。</p>
    </div>
    <div v-else-if="!result?.items?.length" class="empty">没有匹配的检索结果</div>

    <div v-else class="results">
      <div class="results__meta">
        <span>共 {{ result.items.length }} 条结果</span>
        <span class="results__status">{{ result.status }}</span>
      </div>
      <article v-for="item in result.items" :key="item.collection + '-' + item.id" class="result-card">
        <header class="result-card__head">
          <span class="collection-tag" :class="'collection-tag--' + item.collection.toLowerCase().replace('_', '-')">
            {{ collectionLabel(item.collection) }}
          </span>
          <span class="result-card__id">#{{ item.id }}</span>
          <span class="result-card__source">{{ item.sourceType }}</span>
          <div class="result-card__scores">
            <span class="score" title="相关度">R {{ (item.relevance * 100).toFixed(0) }}%</span>
            <span class="score" title="置信度">C {{ (item.confidence * 100).toFixed(0) }}%</span>
            <span class="score score--final" title="最终得分">{{ (item.relevance * item.confidence).toFixed(3) }}</span>
          </div>
        </header>
        <h3 class="result-card__title">{{ item.title }}</h3>
        <p class="result-card__snippet">{{ item.snippet }}</p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { unifiedSearch } from '../../api/p0Modules.ts'

const query: any= ref(''), searching = ref(false), searched = ref(false), error = ref(''), result: any = ref<any>(null)
const selectedCollections: any= ref(['MEMORY', 'PERSONAL_KNOWLEDGE', 'SHARED_KNOWLEDGE'])
const limit: any= ref(10)
const unwrap: any= (r: any) => r?.data ?? r

async function onSearch(): Promise<any> {
  if (!query.value.trim()) return
  searching.value = true; error.value = ''; searched.value = true
  try {
    const data: any= unwrap(await unifiedSearch(
      query.value,
      selectedCollections.value.length ? selectedCollections.value : undefined,
      limit.value
    ))
    result.value = data
  } catch (cause: any) {
    error.value = cause.message || '检索失败'
    result.value = null
  } finally { searching.value = false }
}

function collectionLabel(c: any) {
  return ({ MEMORY: '情景记忆', PERSONAL_KNOWLEDGE: '个人知识', SHARED_KNOWLEDGE: '共享知识' } as any)[c] || c
}
</script>

<style scoped>
.unified-retrieval { color: var(--smart-text); }
.page-header { margin-bottom: 18px; }
.eyebrow { margin: 0 0 8px; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .14em; }
.muted { color: var(--smart-muted); font-size: 12px; }

.search-panel { padding: 16px; border: 1px solid var(--smart-border); border-radius: 8px; background: var(--smart-surface); margin-bottom: 18px; }
.search-form { display: flex; gap: 8px; margin-bottom: 12px; }
.search-input { flex: 1; padding: 10px 14px; background: transparent; border: 1px solid var(--smart-border); border-radius: 6px; color: var(--smart-text); font-size: 14px; }
.search-input:focus { outline: none; border-color: var(--smart-primary-strong); }
.btn { padding: 10px 22px; border: 1px solid transparent; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn--primary { background: var(--smart-primary-strong); color: #fff; }
.btn--primary:hover:not(:disabled) { filter: brightness(1.1); }

.search-options { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; font-size: 12px; color: var(--smart-muted); }
.option { display: flex; align-items: center; gap: 5px; cursor: pointer; }
.option input[type="checkbox"] { cursor: pointer; }
.option-sep { color: var(--smart-border); }
.limit-input { width: 60px; padding: 4px 8px; background: transparent; border: 1px solid var(--smart-border); border-radius: 4px; color: var(--smart-text); font: 11px var(--font-mono); }

.empty, .error { padding: 28px; text-align: center; color: var(--smart-muted); border: 1px dashed var(--smart-border); border-radius: 8px; }
.error { color: var(--ds-semantic-danger); border-color: var(--ds-semantic-danger); }
.empty--warn { background: rgba(255, 180, 0, .05); border-color: rgba(255, 180, 0, .3); color: #ffb400; }
.empty--warn strong { display: block; margin-bottom: 8px; font-size: 14px; }
.empty--warn p { margin: 0; font-size: 12px; line-height: 1.6; color: var(--smart-muted); }

.results__meta { display: flex; justify-content: space-between; margin-bottom: 12px; font: 11px var(--font-mono); color: var(--smart-muted); }
.results__status { color: var(--smart-primary-strong); }

.results { display: flex; flex-direction: column; gap: 12px; }
.result-card { padding: 14px 16px; border: 1px solid var(--smart-border); border-radius: 8px; background: var(--smart-surface); }
.result-card__head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; font: 10px var(--font-mono); color: var(--smart-muted); }
.collection-tag { padding: 2px 8px; border-radius: 4px; letter-spacing: .06em; }
.collection-tag--memory { background: rgba(100, 150, 255, .15); color: #6496ff; }
.collection-tag--personal-knowledge { background: rgba(0, 200, 150, .15); color: #00c896; }
.collection-tag--shared-knowledge { background: rgba(200, 100, 255, .15); color: #c864ff; }
.result-card__id { color: var(--smart-muted); }
.result-card__source { padding: 2px 6px; background: var(--smart-border); border-radius: 3px; }
.result-card__scores { margin-left: auto; display: flex; gap: 8px; }
.score { font: 10px var(--font-mono); color: var(--smart-muted); }
.score--final { color: var(--smart-primary-strong); font-weight: 600; }

.result-card__title { margin: 0 0 6px; font-size: 14px; color: var(--smart-text); }
.result-card__snippet { margin: 0; font-size: 12px; color: var(--smart-muted); line-height: 1.6; }
</style>
