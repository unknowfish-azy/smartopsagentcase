<template>
  <div class="scholar-page">
    <header class="scholar-head">
      <p class="scholar-eyebrow">RETRIEVAL PIPELINE / 检索编排</p>
      <h1>任务式检索编排</h1>
      <p class="scholar-lede">
        把一次检索拆成<strong>五段可见的流水线</strong>：解析问题 → 全库检索 → 相关性筛选 → 证据汇总 → 引用产出。
        每一段展示的都是引擎真实中间产物（检索词、候选打分、引用节选），全部本地确定性计算，无大模型、无网络请求。
      </p>
    </header>

    <section class="scholar-panel scholar-ask" aria-label="检索任务">
      <form class="scholar-ask__form" @submit.prevent="run">
        <input
          v-model="query"
          class="scholar-ask__input"
          type="search"
          placeholder="下达一个检索任务，例如：docker 镜像分层原理"
          aria-label="检索任务"
        />
        <select v-model="courseId" class="scholar-ask__select" aria-label="课程范围">
          <option value="">全部课程</option>
          <option v-for="course in snapshot.courses" :key="course.id" :value="course.id">{{ course.label }}</option>
        </select>
        <button class="scholar-btn" type="submit">执行流水线</button>
      </form>
    </section>

    <div v-if="!hasRun" class="scholar-empty">
      <h3>流水线待命</h3>
      <p>输入任务后，五个阶段会依次点亮。每个阶段点开即是数据本身——这就是全部过程，没有隐藏步骤。</p>
    </div>

    <ol v-else class="scholar-stages">
      <li
        v-for="(stage, i) in visibleStages"
        :key="stage.id"
        class="scholar-stage"
        :class="{ 'scholar-stage--done': true }"
      >
        <div class="scholar-stage__rail" aria-hidden="true">
          <span class="scholar-stage__dot">{{ i + 1 }}</span>
          <span v-if="i < visibleStages.length - 1" class="scholar-stage__line"></span>
        </div>
        <article class="scholar-panel scholar-stage__body">
          <h2>{{ stage.label }}</h2>

          <template v-if="stage.id === 'parse'">
            <p class="scholar-meta">问题拆解为检索词：</p>
            <p>
              <code v-for="token in stage.data.tokens" :key="token" class="scholar-mono">{{ token }}</code>
              <span v-if="stage.data.tokens.length === 0" class="scholar-muted">没有有效检索词（全是停用词）。</span>
            </p>
          </template>

          <template v-else-if="stage.id === 'retrieve'">
            <p class="scholar-meta">扫描 {{ stage.data.scanned }} 篇文档，命中 {{ stage.data.candidateCount }} 篇候选：</p>
            <ul class="scholar-cands">
              <li v-for="cand in stage.data.candidates" :key="cand.id">
                <span>{{ cand.title }}</span><code class="scholar-score">{{ cand.score }}</code>
              </li>
            </ul>
          </template>

          <template v-else-if="stage.id === 'filter'">
            <p class="scholar-meta">
              保留 {{ stage.data.kept }} 篇（阈值：{{ stage.data.threshold }}）——没有命中的候选不硬凑。
            </p>
            <p class="scholar-meta scholar-muted">打分含 IDF 罕见度权重：越少见的词命中，得分越高。</p>
          </template>

          <template v-else-if="stage.id === 'summarize'">
            <p class="scholar-meta">取 Top 3 作为引用证据：</p>
            <blockquote v-for="citation in stage.data.citations" :key="citation.n" class="scholar-quote">
              <strong>[{{ citation.n }}] {{ citation.title }}</strong>
              <p>{{ citation.excerpt }}</p>
            </blockquote>
            <p v-if="stage.data.citations.length === 0" class="scholar-muted">无证据可汇总。</p>
          </template>

          <template v-else>
            <p class="scholar-produce" :class="{ 'scholar-produce--empty': !stage.data.answerable }">{{ stage.data.statement }}</p>
            <RouterLink v-if="stage.data.answerable" class="scholar-link" :to="{ name: 'ScholarQa', query: { q: lastQuery } }">
              到「引用溯源问答」查看完整引用 →
            </RouterLink>
          </template>
        </article>
      </li>
    </ol>

    <footer class="scholar-foot">
      流水线数据全部来自 <code class="scholar-mono">atlasDistilled.json</code> 蒸馏快照（{{ snapshot.totals.documents }} 篇）。
      阶段推进只是展示节奏，计算在点击瞬间一次完成。
    </footer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import snapshot from '../atlas/atlasDistilled.json'
import { runPipeline } from '../../domain/scholar/scholarEngine.js'

const STAGE_INTERVAL_MS = 320

const query = ref('')
const courseId = ref('')
const lastQuery = ref('')
const hasRun = ref(false)
const stages = ref([])
const revealed = ref(0)
let timer = null

const visibleStages = computed(() => stages.value.slice(0, revealed.value))

const reducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

function run() {
  lastQuery.value = query.value.trim()
  stages.value = runPipeline(snapshot, lastQuery.value, { courseId: courseId.value || null })
  hasRun.value = true
  if (timer) clearInterval(timer)
  if (reducedMotion()) {
    revealed.value = stages.value.length
    return
  }
  revealed.value = 1
  timer = setInterval(() => {
    revealed.value = Math.min(revealed.value + 1, stages.value.length)
    if (revealed.value >= stages.value.length) clearInterval(timer)
  }, STAGE_INTERVAL_MS)
}

onBeforeUnmount(() => timer && clearInterval(timer))
</script>

<style scoped>
.scholar-page { display: grid; gap: 16px; color: var(--smart-text, #1f2937); padding-bottom: 32px; }
.scholar-eyebrow { margin: 0 0 4px; font-size: 12px; font-weight: 700; letter-spacing: .08em; color: var(--smart-primary-strong, #2563eb); }
.scholar-head h1 { margin: 0 0 8px; font-size: 22px; }
.scholar-lede { margin: 0; max-width: 880px; font-size: 13.5px; line-height: 1.8; color: var(--smart-muted, #6b7280); }
.scholar-mono { font-family: var(--font-mono, Consolas, monospace); font-size: 12px; background: rgba(37, 99, 235, .08); padding: 1px 6px; border-radius: 4px; margin-right: 4px; }
.scholar-muted { color: var(--smart-muted, #6b7280); }

.scholar-panel { border: 1px solid var(--smart-border, #e5e7eb); border-radius: 12px; background: var(--smart-surface, #fff); padding: 14px 16px; }
.scholar-panel h2 { margin: 0 0 8px; font-size: 14px; }
.scholar-ask { display: grid; gap: 10px; }
.scholar-ask__form { display: flex; gap: 8px; flex-wrap: wrap; }
.scholar-ask__input { flex: 1; min-width: 240px; padding: 8px 12px; border: 1px solid var(--smart-border, #e5e7eb); border-radius: 8px; font-size: 14px; background: var(--smart-surface, #fff); color: inherit; }
.scholar-ask__input:focus-visible, .scholar-ask__select:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 1px; }
.scholar-ask__select { padding: 8px 10px; border: 1px solid var(--smart-border, #e5e7eb); border-radius: 8px; background: var(--smart-surface, #fff); color: inherit; }
.scholar-btn { padding: 8px 18px; border: 0; border-radius: 8px; background: var(--smart-primary-strong, #2563eb); color: #fff; font-size: 13.5px; cursor: pointer; }
.scholar-btn:hover { filter: brightness(1.08); }
.scholar-meta { margin: 0 0 6px; font-size: 12.5px; color: var(--smart-muted, #6b7280); }

.scholar-empty { border: 1px dashed var(--smart-border, #e5e7eb); border-radius: 12px; padding: 24px; text-align: center; }
.scholar-empty p { margin: 0 auto; max-width: 560px; font-size: 13px; color: var(--smart-muted, #6b7280); line-height: 1.8; }

.scholar-stages { list-style: none; margin: 0; padding: 0; display: grid; gap: 0; }
.scholar-stage { display: grid; grid-template-columns: 40px minmax(0, 1fr); }
.scholar-stage__rail { display: flex; flex-direction: column; align-items: center; gap: 4px; padding-top: 18px; }
.scholar-stage__dot { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: var(--smart-primary-strong, #2563eb); color: #fff; font: 700 12px var(--font-mono, Consolas, monospace); }
.scholar-stage__line { flex: 1; width: 2px; background: var(--smart-border, #e5e7eb); min-height: 16px; }
.scholar-stage__body { margin-bottom: 12px; }

.scholar-cands { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 13px; }
.scholar-cands li { display: flex; justify-content: space-between; gap: 12px; padding: 4px 8px; border-radius: 6px; background: rgba(37, 99, 235, .04); }
.scholar-cands li span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scholar-score { font-family: var(--font-mono, Consolas, monospace); color: var(--smart-primary-strong, #2563eb); }
.scholar-quote { margin: 0 0 8px; border-left: 3px solid var(--smart-primary-strong, #2563eb); background: rgba(37, 99, 235, .05); border-radius: 0 8px 8px 0; padding: 8px 12px; }
.scholar-quote strong { font-size: 12.5px; }
.scholar-quote p { margin: 4px 0 0; font-size: 12.5px; line-height: 1.7; color: var(--smart-muted, #6b7280); }
.scholar-produce { margin: 0; font-size: 14px; font-weight: 600; }
.scholar-produce--empty { color: var(--smart-muted, #6b7280); font-weight: 400; }
.scholar-link { font-size: 13px; color: var(--smart-primary-strong, #2563eb); }

@media (prefers-reduced-motion: reduce) {
  .scholar-stage { animation: none; }
}

.scholar-foot { border-top: 1px solid var(--smart-border, #e5e7eb); padding-top: 12px; font-size: 12px; color: var(--smart-muted, #6b7280); }
</style>
