<template>
  <div class="scholar-page">
    <header class="scholar-head">
      <p class="scholar-eyebrow">REVIEW BUILDER / 综述生成器</p>
      <h1>综述生成器</h1>
      <p class="scholar-lede">
        选定一组文档，把它们组装成一份<strong>带引用编号的研究综述</strong>：主题脉络 → 正文节选 → 高频命令 → 引用表。
        综述由快照<strong>结构化组装而成，不是大模型生成</strong>；每个 [n] 都能回查语料路径，可一键导出 markdown。
      </p>
    </header>

    <div class="scholar-main">
      <section class="scholar-panel scholar-picker" aria-label="选择文档">
        <h2>1 · 圈定综述范围</h2>
        <div class="scholar-picker__row">
          <select v-model="courseId" class="scholar-select" aria-label="按课程筛选">
            <option value="">全部课程</option>
            <option v-for="course in snapshot.courses" :key="course.id" :value="course.id">{{ course.label }}</option>
          </select>
          <input v-model="filter" class="scholar-input" type="search" placeholder="筛选文档标题…" aria-label="筛选文档标题" />
          <button class="scholar-btn scholar-btn--ghost" type="button" @click="selectAll">全选可见</button>
          <button class="scholar-btn scholar-btn--ghost" type="button" @click="docIds = []">清空</button>
        </div>
        <p class="scholar-meta scholar-muted">已选 {{ docIds.length }} 篇 · 可见 {{ visibleDocs.length }} 篇</p>
        <ul class="scholar-docs">
          <li v-for="doc in visibleDocs" :key="doc.id">
            <label class="scholar-doc" :class="{ 'scholar-doc--on': docIds.includes(doc.id) }">
              <input v-model="docIds" type="checkbox" :value="doc.id" />
              <span class="scholar-doc__title">{{ doc.title }}</span>
              <span class="scholar-muted scholar-doc__meta">{{ formatChars(doc.chars) }}</span>
            </label>
          </li>
        </ul>
      </section>

      <section class="scholar-panel scholar-controls" aria-label="生成综述">
        <h2>2 · 生成</h2>
        <input v-model="topic" class="scholar-input" type="text" placeholder="综述标题，例如：GPU 性能优化专题" aria-label="综述标题" />
        <button class="scholar-btn" type="button" :disabled="docIds.length === 0" @click="generate">组装综述（{{ docIds.length }} 篇）</button>
        <p v-if="review" class="scholar-meta">
          已生成：<strong>{{ review.overview.documents }}</strong> 篇 · {{ formatChars(review.overview.chars) }} ·
          {{ review.overview.sections }} 节 · 引用 {{ review.references.length }} 条
        </p>
        <template v-if="review">
          <button class="scholar-btn scholar-btn--ghost" type="button" @click="copyMarkdown">{{ copied ? '已复制 ✓' : '复制 markdown' }}</button>
          <button class="scholar-btn scholar-btn--ghost" type="button" @click="downloadMarkdown">下载 .md 文件</button>
          <p v-if="copyError" class="scholar-meta">复制失败（{{ copyError }}），请改用下载。</p>
        </template>
      </section>
    </div>

    <div v-if="review" class="scholar-review">
      <article class="scholar-panel">
        <h2>{{ review.topic || '研究综述' }}</h2>
        <p class="scholar-meta scholar-muted">
          覆盖 {{ review.overview.documents }} 篇文档 · {{ formatChars(review.overview.chars) }} ·
          代码块 {{ review.overview.codeBlocks }} 个。结构化组装，非大模型生成。
        </p>
      </article>

      <article v-for="thread in review.threads" :key="thread.n" class="scholar-panel">
        <h3><span class="scholar-cite">[{{ thread.n }}]</span> {{ thread.title }}</h3>
        <ul class="scholar-headings">
          <li v-for="heading in thread.headings" :key="heading">{{ heading }}</li>
        </ul>
        <blockquote v-for="quote in thread.quotes" :key="quote.text" class="scholar-quote">
          <strong>{{ quote.text }}</strong>
          <p>{{ quote.excerpt }}</p>
        </blockquote>
      </article>

      <div class="scholar-two-col">
        <article v-if="review.commands.length" class="scholar-panel">
          <h2>高频命令</h2>
          <ul class="scholar-cmds">
            <li v-for="cmd in review.commands" :key="cmd.cmd"><code class="scholar-mono">{{ cmd.cmd }}</code><span class="scholar-muted">×{{ cmd.count }}</span></li>
          </ul>
        </article>
        <article class="scholar-panel">
          <h2>引用表</h2>
          <ol class="scholar-refs">
            <li v-for="ref in review.references" :key="ref.n">
              <strong>{{ ref.title }}</strong>
              <span class="scholar-muted"><code class="scholar-mono">{{ ref.path }}</code> · {{ ref.course }}</span>
            </li>
          </ol>
        </article>
      </div>
    </div>

    <div v-else class="scholar-empty">
      <h3>还没有综述</h3>
      <p>左侧圈定 1-20 篇文档，起个标题，点「组装综述」。不选文档时按钮不可用——综述必须有真实引用范围。</p>
    </div>

    <footer class="scholar-foot">
      综述来源：<code class="scholar-mono">atlasDistilled.json</code>。组装规则：每篇取前 4 个标题 + 前 2 段节选，命令按出现次数聚合，引用编号与文档顺序一致。
    </footer>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import snapshot from '../atlas/atlasDistilled.json'
import { buildReview, reviewToMarkdown } from '../../domain/scholar/scholarEngine.js'

const MAX_REVIEW_DOCS = 20

const courseId = ref('')
const filter = ref('')
const docIds = ref([])
const topic = ref('')
const review = ref(null)
const copied = ref(false)
const copyError = ref('')

const visibleDocs = computed(() => {
  const keyword = filter.value.trim().toLowerCase()
  return snapshot.documents.filter(doc => {
    if (courseId.value && doc.courseId !== courseId.value) return false
    if (keyword && !doc.title.toLowerCase().includes(keyword)) return false
    return true
  })
})

const formatChars = chars => chars >= 10000 ? `${(chars / 10000).toFixed(1)} 万字` : `${chars} 字`

function selectAll() {
  docIds.value = visibleDocs.value.slice(0, MAX_REVIEW_DOCS).map(doc => doc.id)
}

function generate() {
  const picked = docIds.value.slice(0, MAX_REVIEW_DOCS)
  review.value = buildReview(snapshot, { docIds: picked, topic: topic.value.trim() })
  copied.value = false
  copyError.value = ''
}

function currentMarkdown() {
  return reviewToMarkdown(review.value)
}

async function copyMarkdown() {
  try {
    await navigator.clipboard.writeText(currentMarkdown())
    copied.value = true
    copyError.value = ''
    setTimeout(() => { copied.value = false }, 2000)
  } catch (error) {
    copyError.value = error?.message ?? '剪贴板不可用'
  }
}

function downloadMarkdown() {
  const blob = new Blob([currentMarkdown()], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `review-${Date.now()}.md`
  anchor.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.scholar-page { display: grid; gap: 16px; color: var(--smart-text, #1f2937); padding-bottom: 32px; }
.scholar-eyebrow { margin: 0 0 4px; font-size: 12px; font-weight: 700; letter-spacing: .08em; color: var(--smart-primary-strong, #2563eb); }
.scholar-head h1, .scholar-panel h2 { margin: 0 0 8px; font-size: 22px; }
.scholar-panel h2 { font-size: 16px; }
.scholar-panel h3 { margin: 0 0 8px; font-size: 15px; }
.scholar-lede { margin: 0; max-width: 880px; font-size: 13.5px; line-height: 1.8; color: var(--smart-muted, #6b7280); }
.scholar-mono { font-family: var(--font-mono, Consolas, monospace); font-size: 11.5px; background: rgba(37, 99, 235, .08); padding: 1px 6px; border-radius: 4px; }
.scholar-muted { color: var(--smart-muted, #6b7280); }

.scholar-panel { border: 1px solid var(--smart-border, #e5e7eb); border-radius: 12px; background: var(--smart-surface, #fff); padding: 14px 16px; display: grid; gap: 10px; align-content: start; }
.scholar-main { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px; align-items: start; }
.scholar-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.scholar-picker__row { display: flex; gap: 8px; flex-wrap: wrap; }
.scholar-select, .scholar-input { padding: 7px 10px; border: 1px solid var(--smart-border, #e5e7eb); border-radius: 8px; background: var(--smart-surface, #fff); color: inherit; font-size: 13px; }
.scholar-select:focus-visible, .scholar-input:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 1px; }
.scholar-input { flex: 1; min-width: 140px; }
.scholar-btn { padding: 7px 16px; border: 0; border-radius: 8px; background: var(--smart-primary-strong, #2563eb); color: #fff; font-size: 13px; cursor: pointer; }
.scholar-btn--ghost { background: none; border: 1px solid var(--smart-border, #e5e7eb); color: var(--smart-text, #1f2937); }
.scholar-btn:disabled { opacity: .45; cursor: not-allowed; }
.scholar-meta { margin: 0; font-size: 12px; }

.scholar-docs { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; max-height: 420px; overflow-y: auto; }
.scholar-doc { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border: 1px solid transparent; border-radius: 8px; cursor: pointer; font-size: 13px; }
.scholar-doc:hover { border-color: var(--smart-border, #e5e7eb); }
.scholar-doc--on { background: rgba(37, 99, 235, .07); border-color: rgba(37, 99, 235, .3); }
.scholar-doc__title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scholar-doc__meta { font-size: 11.5px; }

.scholar-review { display: grid; gap: 12px; }
.scholar-cite { font-family: var(--font-mono, Consolas, monospace); color: var(--smart-primary-strong, #2563eb); }
.scholar-headings { margin: 0; padding-left: 18px; font-size: 13px; color: var(--smart-muted, #6b7280); display: grid; gap: 3px; }
.scholar-quote { margin: 0; border-left: 3px solid var(--smart-primary-strong, #2563eb); background: rgba(37, 99, 235, .05); border-radius: 0 8px 8px 0; padding: 8px 12px; }
.scholar-quote strong { font-size: 12.5px; }
.scholar-quote p { margin: 4px 0 0; font-size: 12.5px; line-height: 1.7; color: var(--smart-muted, #6b7280); }
.scholar-cmds { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; font-size: 13px; }
.scholar-cmds li { display: flex; justify-content: space-between; gap: 10px; }
.scholar-refs { margin: 0; padding-left: 20px; display: grid; gap: 8px; font-size: 13px; }
.scholar-refs span { display: block; font-size: 12px; }

.scholar-empty { border: 1px dashed var(--smart-border, #e5e7eb); border-radius: 12px; padding: 24px; text-align: center; }
.scholar-empty p { margin: 0 auto; max-width: 560px; font-size: 13px; color: var(--smart-muted, #6b7280); line-height: 1.8; }
.scholar-foot { border-top: 1px solid var(--smart-border, #e5e7eb); padding-top: 12px; font-size: 12px; color: var(--smart-muted, #6b7280); }

@media (max-width: 960px) {
  .scholar-main, .scholar-two-col { grid-template-columns: 1fr; }
}
</style>
