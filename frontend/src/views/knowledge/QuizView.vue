<template>
  <article class="quiz-space">
    <header class="quiz-hero">
      <p class="eyebrow">QUIZ BANK / 运维题库</p>
      <h1>运维题库</h1>
      <p class="lede">从内置知识包抽取问答题与判断题，自评「会 / 不会」，答不上的自动进错题本反复巩固。</p>
      <div class="quiz-stats">
        <div class="stat"><strong>{{ quizItems.length }}</strong><span>题库总量</span></div>
        <div class="stat"><strong>{{ quizPlatforms.length }}</strong><span>知识平台</span></div>
        <div class="stat"><strong>{{ quizTypes.length }}</strong><span>题型</span></div>
        <div class="stat"><strong>{{ wrongBook.length }}</strong><span>错题待巩固</span></div>
      </div>
    </header>

    <nav class="zone-tabs" aria-label="Knowledge zones">
      <RouterLink class="zone-tab" to="/knowledge">系统知识库</RouterLink>
      <RouterLink class="zone-tab" to="/knowledge/personal">我的知识库</RouterLink>
      <RouterLink class="zone-tab active" to="/knowledge/quiz">题库</RouterLink>
    </nav>

    <section class="quiz-toolbar" aria-label="抽题设置">
      <div class="filter-group">
        <label for="quiz-platform">知识平台</label>
        <select id="quiz-platform" v-model="filters.platform">
          <option value="">全部平台</option>
          <option v-for="p in quizPlatforms" :key="p" :value="p">{{ p }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label for="quiz-type">题型</label>
        <select id="quiz-type" v-model="filters.type">
          <option value="">全部题型</option>
          <option v-for="t in quizTypes" :key="t" :value="t">{{ t }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label for="quiz-count">抽题数量</label>
        <select id="quiz-count" v-model.number="filters.count">
          <option :value="5">5 题</option>
          <option :value="10">10 题</option>
          <option :value="20">20 题</option>
          <option :value="0">全部</option>
        </select>
      </div>
      <button type="button" class="primary draw" :disabled="!pool.length" @click="draw">{{ drawing ? '换一批' : '开始抽题' }}</button>
    </section>

    <p v-if="!pool.length" class="empty">当前筛选下没有题目，换个平台或题型试试。</p>

    <section v-if="drawing" class="quiz-practice" aria-label="练习区">
      <div class="section-head">
        <h2>本次练习</h2>
        <span class="head-note">{{ answeredCount }} / {{ session.length }} 已自评</span>
      </div>
      <ol class="quiz-list">
        <li v-for="(item, index) in session" :key="item.id" class="quiz-card" :class="{ revealed: item.revealed, correct: item.verdict === 'know', wrong: item.verdict === 'unknown' }">
          <div class="quiz-card__top">
            <span class="quiz-number">{{ index + 1 }}</span>
            <div class="quiz-meta">
              <span class="quiz-type">{{ item.typeLabel }}</span>
              <span class="quiz-platform">{{ item.platform }}</span>
            </div>
            <span v-if="item.verdict" class="quiz-verdict" :class="item.verdict">{{ item.verdict === 'know' ? '已掌握' : '待巩固' }}</span>
          </div>
          <p class="quiz-prompt">{{ item.prompt }}</p>
          <div v-if="item.revealed" class="quiz-answer">
            <template v-if="item.kind === 'wrong'"><strong class="answer-tag">该说法错误</strong></template>
            <template v-else><strong class="answer-tag">参考解析</strong></template>
            <p>{{ item.answer }}</p>
          </div>
          <div class="quiz-actions">
            <button type="button" class="ghost" @click="toggleReveal(item)">{{ item.revealed ? '收起解析' : '查看解析' }}</button>
            <button type="button" class="know" :class="{ on: item.verdict === 'know' }" @click="assess(item, 'know')">✓ 会</button>
            <button type="button" class="unknown" :class="{ on: item.verdict === 'unknown' }" @click="assess(item, 'unknown')">✗ 不会</button>
          </div>
        </li>
      </ol>
    </section>

    <section class="wrong-book" aria-label="错题本">
      <div class="section-head">
        <h2>错题本</h2>
        <span class="head-note">{{ wrongBook.length }} 道待巩固</span>
      </div>
      <p v-if="!wrongBook.length" class="muted">还没有错题。练习时点「不会」的题会自动收进这里，学懂了再移出。</p>
      <ol v-else class="quiz-list">
        <li v-for="item in wrongBook" :key="item.id" class="quiz-card quiz-card--wrong">
          <div class="quiz-card__top">
            <div class="quiz-meta"><span class="quiz-type">{{ item.typeLabel }}</span><span class="quiz-platform">{{ item.platform }}</span></div>
          </div>
          <p class="quiz-prompt">{{ item.prompt }}</p>
          <details class="quiz-answer"><summary>查看解析</summary><p>{{ item.answer }}</p></details>
          <div class="quiz-actions"><button type="button" class="ghost" @click="removeWrong(item.id)">移出错题本</button></div>
        </li>
      </ol>
    </section>
  </article>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { quizItems, quizPlatforms, quizTypes, loadWrongBook, addWrongItem, removeWrongItem } from './quizCatalog.js'

const filters = reactive({ platform: '', type: '', count: 5 })
const session = ref([])
const drawing = ref(false)
const wrongBook = ref(loadWrongBook())

const pool = computed(() => quizItems.filter(item =>
  (!filters.platform || item.platform === filters.platform) &&
  (!filters.type || item.typeLabel === filters.type)))

const answeredCount = computed(() => session.value.filter(item => item.verdict).length)

function draw() {
  const source = [...pool.value]
  for (let i = source.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1)); [source[i], source[j]] = [source[j], source[i]]
  }
  const take = filters.count > 0 ? Math.min(filters.count, source.length) : source.length
  session.value = source.slice(0, take).map(item => ({ ...item, revealed: false, verdict: null }))
  drawing.value = true
}

function toggleReveal(item) { item.revealed = !item.revealed }

function assess(item, verdict) {
  item.verdict = verdict
  if (verdict === 'unknown') wrongBook.value = addWrongItem(item)
  else if (wrongBook.value.some(entry => entry.id === item.id)) wrongBook.value = removeWrongItem(item.id)
}

function removeWrong(id) { wrongBook.value = removeWrongItem(id) }
</script>

<style scoped>
.quiz-space { max-width: 1240px; margin: 0 auto; padding: clamp(24px, 4vw, 56px) clamp(16px, 4vw, 48px) 72px; color: var(--smart-text); overflow-wrap: anywhere; }

/* --- 头部 hero --- */
.quiz-hero { padding: 8px 0 40px; }
.eyebrow { margin: 0 0 14px; color: var(--smart-primary-strong); font: 12px var(--font-mono); letter-spacing: .22em; }
.quiz-hero h1 { margin: 0; font-size: clamp(30px, 5vw, 44px); font-weight: 700; letter-spacing: -.02em; line-height: 1.1; }
.lede { max-width: 720px; margin: 16px 0 0; color: var(--smart-muted); font-size: 16px; line-height: 1.8; }
.quiz-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-top: 36px; }
.stat { padding: 22px 24px; border: 1px solid var(--smart-border); border-radius: 14px; background: var(--smart-surface); }
.stat strong { display: block; font-size: 34px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; color: var(--smart-primary-strong); }
.stat span { display: block; margin-top: 10px; color: var(--smart-muted); font-size: 13px; }

/* --- zone tabs --- */
.zone-tabs { display: flex; gap: 6px; flex-wrap: wrap; border-bottom: 1px solid var(--smart-border); }
.zone-tab { min-height: 46px; display: inline-flex; align-items: center; padding: 10px 18px; color: var(--smart-muted); text-decoration: none; border-bottom: 2px solid transparent; font-size: 14px; }
.zone-tab:hover, .zone-tab.active { color: var(--smart-primary-strong); border-color: var(--smart-primary-strong); }

/* --- 工具栏 --- */
.quiz-toolbar { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr) minmax(0,1fr) auto; gap: 20px; align-items: end; padding: 28px 0 8px; }
.filter-group { display: grid; gap: 10px; }
.filter-group label { color: var(--smart-muted); font-size: 12px; font-weight: 600; letter-spacing: .04em; }
.filter-group select { min-height: 48px; padding: 10px 14px; border: 1px solid var(--smart-border); border-radius: 10px; background: var(--smart-surface); color: var(--smart-text); font-size: 15px; }
.quiz-toolbar .primary { min-height: 48px; padding: 10px 26px; border: 1px solid transparent; border-radius: 10px; background: var(--smart-primary-strong); color: var(--smart-bg); font-size: 15px; font-weight: 600; cursor: pointer; }
.quiz-toolbar .primary:disabled { opacity: .45; cursor: not-allowed; }
.empty { padding: 60px 0; color: var(--smart-muted); text-align: center; font-size: 15px; }

/* --- 练习区 / 错题本 --- */
.quiz-practice, .wrong-book { margin-top: 44px; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 20px; margin-bottom: 22px; padding-bottom: 14px; border-bottom: 1px solid var(--smart-border); }
.section-head h2 { margin: 0; font-size: 22px; font-weight: 700; }
.head-note { color: var(--smart-muted); font-size: 14px; }
.muted { color: var(--smart-muted); font-size: 14px; line-height: 1.8; }

.quiz-list { display: grid; gap: 20px; margin: 0; padding: 0; list-style: none; }
.quiz-card { padding: 26px 28px; border: 1px solid var(--smart-border); border-radius: 16px; background: var(--smart-surface); box-shadow: 0 1px 2px rgb(0 0 0 / 4%); }
.quiz-card.revealed { border-color: var(--smart-border-strong); }
.quiz-card.correct { border-left: 4px solid #8bc8a7; }
.quiz-card.wrong { border-left: 4px solid #e19b8b; }
.quiz-card--wrong { border-left: 4px solid #e19b8b; }

.quiz-card__top { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
.quiz-number { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 10px; background: var(--smart-primary-strong); color: var(--smart-bg); font-size: 15px; font-weight: 700; }
.quiz-meta { display: flex; align-items: center; gap: 10px; flex: 1 1 auto; min-width: 0; }
.quiz-type { padding: 4px 10px; border: 1px solid var(--smart-primary-strong); border-radius: 999px; color: var(--smart-primary-strong); font-size: 12px; }
.quiz-platform { color: var(--smart-muted); font-size: 13px; }
.quiz-verdict { padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.quiz-verdict.know { background: rgba(139,200,167,.14); color: #6fbf92; }
.quiz-verdict.unknown { background: rgba(225,155,139,.14); color: #e19b8b; }

.quiz-prompt { margin: 0 0 18px; font-size: 17px; font-weight: 500; line-height: 1.85; color: var(--smart-text); }

.quiz-answer { margin: 0 0 20px; padding: 18px 20px; border-left: 3px solid var(--smart-primary-strong); border-radius: 10px; background: rgba(77,179,255,.07); }
.answer-tag { display: block; margin-bottom: 8px; color: var(--smart-text); font-size: 13px; font-weight: 600; letter-spacing: .02em; }
.quiz-answer p { margin: 0; color: var(--smart-muted); font-size: 15px; line-height: 1.9; white-space: pre-wrap; }
details.quiz-answer { cursor: pointer; }
details.quiz-answer summary { color: var(--smart-primary-strong); font-size: 14px; font-weight: 500; }

.quiz-actions { display: flex; gap: 12px; flex-wrap: wrap; }
.quiz-actions button { min-height: 44px; padding: 10px 22px; border: 1px solid var(--smart-border-strong); border-radius: 10px; background: var(--smart-surface); color: var(--smart-text); font-size: 14px; font-weight: 500; cursor: pointer; }
.quiz-actions button:hover { border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); }
.quiz-actions .know.on { border-color: #6fbf92; background: rgba(139,200,167,.16); color: #6fbf92; }
.quiz-actions .unknown.on { border-color: #e19b8b; background: rgba(225,155,139,.16); color: #e19b8b; }
.quiz-actions .ghost { background: transparent; }

@media (max-width: 760px) {
  .quiz-stats { grid-template-columns: repeat(2, 1fr); }
  .quiz-toolbar { grid-template-columns: 1fr 1fr; }
  .quiz-toolbar .primary { grid-column: 1 / -1; }
  .quiz-card { padding: 20px 20px; }
}
</style>
