<template>
  <details class="knowledge-crawl">
    <summary class="crawl-heading">
      <span class="crawl-label">WEB CRAWL <span>网页抓取</span></span>
      <span class="crawl-note">按 URL 抓取同域静态页面，变更覆盖对应条目；展开后可创建或运行爬取源。</span>
    </summary>
    <form class="crawl-form" @submit.prevent="createSource">
      <label>仓库
        <select v-model="form.libraryId" required>
          <option value="" disabled>选择仓库</option>
          <option v-for="library in libraries" :key="library.id" :value="library.id">{{ library.name }}</option>
        </select>
      </label>
      <label>名称<input v-model="form.name" type="text" placeholder="例如：Nginx 官方文档" required /></label>
      <label class="crawl-wide">起始地址<input v-model="form.seedUrl" type="url" placeholder="https://example.com/docs" required /></label>
      <label>最多页数<input v-model.number="form.maxPages" type="number" min="1" max="50" /></label>
      <label>深度<input v-model.number="form.depth" type="number" min="0" max="2" /></label>
      <button class="crawl-primary" type="submit" :disabled="creating">{{ creating ? '创建中…' : '新建爬取源' }}</button>
    </form>
    <p v-if="error" class="crawl-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="crawl-notice" role="status">{{ notice }}</p>
    <table v-if="sources.length" class="crawl-table">
      <thead><tr><th>名称</th><th>起始地址</th><th>上次运行</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="source in sources" :key="source.id">
          <td><strong>{{ source.name }}</strong><small>{{ source.maxPages }} 页 / 深度 {{ source.depth }}</small></td>
          <td class="crawl-url">{{ source.seedUrl }}</td>
          <td><span>{{ formatTime(source.lastRunAt) }}</span><small :class="source.lastStatus === 'PARTIAL' ? 'crawl-warn' : ''">{{ source.lastStatus || '未运行' }}</small><small v-if="source.lastError" class="crawl-warn">{{ source.lastError }}</small></td>
          <td>
            <button type="button" :disabled="running === source.id" @click="run(source)">{{ running === source.id ? '抓取中…' : '立即抓取' }}</button>
            <p v-if="results[source.id]" class="crawl-result">{{ results[source.id] }}</p>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="crawl-empty">还没有爬取源。</p>
  </details>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { createKnowledgeCrawlSource, listKnowledgeCrawlSources, listKnowledgeLibraries, runKnowledgeCrawlSource } from '../../api/personalKnowledge.ts'

const unwrap = value => value?.data ?? value
const libraries = ref([])
const sources = ref([])
const results = reactive({})
const form = reactive({ libraryId: '', name: '', seedUrl: '', maxPages: 20, depth: 1 })
const creating = ref(false)
const running = ref(null)
const error = ref('')
const notice = ref('')

function formatTime(value) {
  if (!value) return '未运行'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

async function loadLibraries() {
  try {
    const result = unwrap(await listKnowledgeLibraries())
    libraries.value = Array.isArray(result) ? result : (result?.items || [])
  } catch (cause) {
    error.value = cause.message || '读取知识库列表失败'
  }
}

async function loadSources() {
  try {
    const result = unwrap(await listKnowledgeCrawlSources())
    sources.value = Array.isArray(result) ? result : (result?.items || [])
  } catch (cause) {
    error.value = cause.message || '读取爬取源失败'
  }
}

async function createSource() {
  if (!form.libraryId) { error.value = '请选择仓库'; return }
  creating.value = true
  try {
    unwrap(await createKnowledgeCrawlSource({
      libraryId: Number(form.libraryId),
      name: form.name,
      seedUrl: form.seedUrl,
      maxPages: form.maxPages,
      depth: form.depth
    }))
    form.name = ''
    form.seedUrl = ''
    notice.value = '爬取源已创建'
    error.value = ''
    await loadSources()
  } catch (cause) {
    error.value = cause.message || '创建爬取源失败'
  } finally {
    creating.value = false
  }
}

async function run(source) {
  running.value = source.id
  error.value = ''
  try {
    const result = unwrap(await runKnowledgeCrawlSource(source.id))
    results[source.id] = `新增 ${result.added} / 更新 ${result.updated} / 未变 ${result.unchanged} / 失败 ${result.failed}（共 ${result.pages} 页）`
    notice.value = `「${source.name}」抓取完成`
    await loadSources()
  } catch (cause) {
    error.value = cause.message || '抓取失败'
  } finally {
    running.value = null
  }
}

onMounted(() => {
  loadLibraries()
  loadSources()
})
</script>

<style scoped>
.knowledge-crawl { margin: 28px 0; padding: 18px; border: 1px solid var(--smart-border); background: var(--smart-surface); color: var(--smart-text); }
.crawl-heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 18px; cursor: pointer; list-style: none; }
.crawl-heading::-webkit-details-marker { display: none; }
.crawl-heading::before { content: '+'; color: var(--smart-primary-strong); font: 12px var(--font-mono); }
.knowledge-crawl[open] .crawl-heading::before { content: '−'; }
.crawl-label { margin: 0; color: var(--smart-primary-strong); font: var(--label-size) var(--font-mono); letter-spacing: .13em; }
.crawl-label span { margin-left: 8px; color: var(--smart-muted); font-family: var(--font-cn); letter-spacing: 0; }
.crawl-note { margin: 0; color: var(--smart-muted); font: 12px/1.7 var(--font-cn); }
.crawl-form { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-top: 16px; }
.crawl-form label { display: grid; gap: 6px; color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .1em; }
.crawl-form label.crawl-wide { flex: 1 1 280px; }
.crawl-form input, .crawl-form select { box-sizing: border-box; min-height: 38px; padding: 0 10px; border: 1px solid var(--smart-border-strong); border-radius: 0; background: var(--smart-surface); color: var(--smart-text); font: 12px var(--font-mono); outline: none; }
.crawl-form input:focus, .crawl-form select:focus { border-color: var(--smart-primary-strong); }
.crawl-form input[type="number"] { width: 90px; }
.crawl-primary, .crawl-table button { min-height: 38px; padding: 0 12px; border: 1px solid var(--smart-border-strong); border-radius: 0; background: transparent; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .06em; cursor: pointer; }
.crawl-primary { border-color: var(--smart-primary-strong); background: var(--smart-primary-strong); color: var(--smart-accent-foreground); }
.crawl-primary:disabled, .crawl-table button:disabled { opacity: .55; cursor: not-allowed; }
.crawl-table { width: 100%; margin-top: 18px; border-collapse: collapse; font: 12px var(--font-cn); }
.crawl-table th { padding: 8px 10px 8px 0; border-bottom: 1px solid var(--smart-border-strong); color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .1em; text-align: left; }
.crawl-table td { padding: 12px 10px 12px 0; border-bottom: 1px solid var(--smart-border); vertical-align: top; overflow-wrap: anywhere; }
.crawl-table td strong { display: block; font-weight: 400; }
.crawl-table td small { display: block; margin-top: 4px; color: var(--smart-muted); font: 10px var(--font-mono); overflow-wrap: anywhere; }
.crawl-url { color: var(--smart-muted); font: 10px/1.6 var(--font-mono); }
.crawl-table button { min-height: 32px; padding: 0 10px; }
.crawl-result { margin: 8px 0 0; color: var(--smart-primary-strong); font: 10px/1.6 var(--font-mono); }
.crawl-error { margin: 12px 0 0; color: var(--smart-danger); font-size: 12px; }
.crawl-notice { margin: 12px 0 0; color: var(--smart-primary-strong); font-size: 12px; }
.crawl-warn { color: var(--smart-danger) !important; }
.crawl-empty { margin: 18px 0 0; color: var(--smart-muted); font: 12px var(--font-cn); }
@media (max-width: 767px) { .crawl-form { display: grid; grid-template-columns: 1fr 1fr; } .crawl-form label.crawl-wide { grid-column: 1 / -1; } .crawl-form input, .crawl-form select { width: 100%; } .crawl-form button { grid-column: 1 / -1; } .crawl-table { display: block; overflow-x: auto; } }
</style>
