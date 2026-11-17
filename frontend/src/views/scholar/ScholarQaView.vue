<template>
  <div class="scholar-page">
    <header class="scholar-head">
      <p class="scholar-eyebrow">TRACEABLE QA / 引用溯源问答</p>
      <h1>引用溯源问答</h1>
      <p class="scholar-lede">
        对语料库蒸馏快照做<strong>确定性关键词检索</strong>：命中的每条证据都带 [n] 编号和语料库真实路径，可回查原文。
        这里<strong>没有大模型参与</strong>——检索不到就如实返回空，不编造答案。
      </p>
    </header>

    <section class="scholar-panel scholar-ask" aria-label="提问">
      <form class="scholar-ask__form" @submit.prevent="ask">
        <input
          v-model="query"
          class="scholar-ask__input"
          type="search"
          placeholder="例如：docker 镜像分层 / GPU 性能优化 / vLLM 推理"
          aria-label="检索问题"
        />
        <select v-model="courseId" class="scholar-ask__select" aria-label="课程范围">
          <option value="">全部课程</option>
          <option v-for="course in snapshot.courses" :key="course.id" :value="course.id">{{ course.label }}</option>
        </select>
        <button class="scholar-btn" type="submit">检索</button>
      </form>
      <div class="scholar-chips">
        <button v-for="hint in hints" :key="hint" type="button" class="scholar-chip" @click="query = hint; ask()">{{ hint }}</button>
      </div>
    </section>

    <p v-if="asked" class="scholar-meta">
      检索词：<code v-for="token in result.tokens" :key="token" class="scholar-mono">{{ token }}</code>
      <span v-if="result.tokens.length === 0" class="scholar-muted">（没有可检索的有效词）</span>
    </p>

    <div v-if="asked && result.results.length === 0" class="scholar-empty">
      <h3>没有命中</h3>
      <p>快照里没有找到与「{{ lastQuery }}」相关的文档。这是诚实结果——本页不会在没有证据时编造回答。换个关键词，或缩小课程范围再试。</p>
    </div>

    <template v-else-if="asked">
      <p class="scholar-meta">在 {{ scannedCount }} 篇文档中命中 {{ result.results.length }} 篇，按相关性排序：</p>
      <article v-for="(item, index) in result.results" :key="item.doc.id" class="scholar-hit">
        <div class="scholar-hit__head">
          <span class="scholar-hit__n">[{{ index + 1 }}]</span>
          <strong>{{ item.doc.title }}</strong>
          <span class="scholar-muted">相关度 {{ item.score }}</span>
        </div>
        <p class="scholar-muted scholar-hit__path">{{ courseLabel(item.doc.courseId) }} · <code class="scholar-mono">{{ item.doc.path }}</code></p>
        <blockquote v-for="section in item.sections" :key="section.text" class="scholar-quote">
          <strong>{{ section.text }}</strong>
          <p>{{ section.excerpt }}</p>
        </blockquote>
        <p class="scholar-meta">命中词：<code v-for="token in item.matchedTerms" :key="token" class="scholar-mono">{{ token }}</code></p>
      </article>
    </template>

    <footer class="scholar-foot">
      数据来源：<code class="scholar-mono">atlasDistilled.json</code>（{{ snapshot.generatedAt.slice(0, 10) }} 蒸馏，
      {{ snapshot.totals.documents }} 篇文档）。确定性检索，无大模型、无编造。
    </footer>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import snapshot from '../atlas/atlasDistilled.json'
import { searchDocuments } from '../../domain/scholar/scholarEngine.js'

const route = useRoute()
const HINTS = ['docker 镜像分层', 'GPU 性能优化', 'vLLM 推理部署', 'systemctl 服务管理']
const hints = HINTS.filter(hint => searchDocuments(snapshot, hint, { limit: 1 }).results.length > 0)

const query = ref(String(route.query.q ?? ''))
const courseId = ref('')
const lastQuery = ref('')
const asked = ref(false)
const result = ref({ tokens: [], results: [] })

const scannedCount = computed(() =>
  courseId.value ? snapshot.documents.filter(doc => doc.courseId === courseId.value).length : snapshot.totals.documents)

const courseLabel = id => snapshot.courses.find(course => course.id === id)?.label ?? id

function ask() {
  lastQuery.value = query.value.trim()
  result.value = searchDocuments(snapshot, lastQuery.value, { limit: 6, courseId: courseId.value || null })
  asked.value = true
}

// 支持从流水线页带 q 参数深链进入
if (query.value) ask()
</script>

<style scoped>
.scholar-page { display: grid; gap: 16px; color: var(--smart-text, #1f2937); padding-bottom: 32px; }
.scholar-eyebrow { margin: 0 0 4px; font-size: 12px; font-weight: 700; letter-spacing: .08em; color: var(--smart-primary-strong, #2563eb); }
.scholar-head h1 { margin: 0 0 8px; font-size: 22px; }
.scholar-lede { margin: 0; max-width: 880px; font-size: 13.5px; line-height: 1.8; color: var(--smart-muted, #6b7280); }
.scholar-mono { font-family: var(--font-mono, Consolas, monospace); font-size: 12px; background: rgba(37, 99, 235, .08); padding: 1px 6px; border-radius: 4px; margin-right: 4px; }
.scholar-muted { color: var(--smart-muted, #6b7280); }

.scholar-panel { border: 1px solid var(--smart-border, #e5e7eb); border-radius: 12px; background: var(--smart-surface, #fff); padding: 14px 16px; }
.scholar-ask { display: grid; gap: 10px; }
.scholar-ask__form { display: flex; gap: 8px; flex-wrap: wrap; }
.scholar-ask__input { flex: 1; min-width: 240px; padding: 8px 12px; border: 1px solid var(--smart-border, #e5e7eb); border-radius: 8px; font-size: 14px; background: var(--smart-surface, #fff); color: inherit; }
.scholar-ask__input:focus-visible, .scholar-ask__select:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 1px; }
.scholar-ask__select { padding: 8px 10px; border: 1px solid var(--smart-border, #e5e7eb); border-radius: 8px; background: var(--smart-surface, #fff); color: inherit; }
.scholar-btn { padding: 8px 18px; border: 0; border-radius: 8px; background: var(--smart-primary-strong, #2563eb); color: #fff; font-size: 13.5px; cursor: pointer; }
.scholar-btn:hover { filter: brightness(1.08); }
.scholar-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.scholar-chip { border: 1px solid var(--smart-border, #e5e7eb); background: none; border-radius: 999px; padding: 3px 12px; font-size: 12px; color: var(--smart-muted, #6b7280); cursor: pointer; }
.scholar-chip:hover { color: var(--smart-primary-strong, #2563eb); border-color: var(--smart-primary-strong, #2563eb); }

.scholar-meta { margin: 0; font-size: 12.5px; color: var(--smart-muted, #6b7280); }
.scholar-empty { border: 1px dashed var(--smart-border, #e5e7eb); border-radius: 12px; padding: 24px; text-align: center; }
.scholar-empty h3 { margin: 0 0 8px; }
.scholar-empty p { margin: 0 auto; max-width: 560px; font-size: 13px; color: var(--smart-muted, #6b7280); line-height: 1.8; }

.scholar-hit { border: 1px solid var(--smart-border, #e5e7eb); border-radius: 12px; background: var(--smart-surface, #fff); padding: 14px 16px; display: grid; gap: 8px; }
.scholar-hit__head { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.scholar-hit__n { font-family: var(--font-mono, Consolas, monospace); color: var(--smart-primary-strong, #2563eb); font-weight: 700; }
.scholar-hit__path { margin: 0; font-size: 12px; }
.scholar-quote { margin: 0; border-left: 3px solid var(--smart-primary-strong, #2563eb); background: rgba(37, 99, 235, .05); border-radius: 0 8px 8px 0; padding: 8px 12px; }
.scholar-quote strong { font-size: 13px; }
.scholar-quote p { margin: 4px 0 0; font-size: 12.5px; line-height: 1.7; color: var(--smart-muted, #6b7280); }

.scholar-foot { border-top: 1px solid var(--smart-border, #e5e7eb); padding-top: 12px; font-size: 12px; color: var(--smart-muted, #6b7280); }
</style>
