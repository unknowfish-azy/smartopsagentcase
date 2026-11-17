<template>
  <div class="scholar-page">
    <header class="scholar-head">
      <p class="scholar-eyebrow">STUDY CARDS / 研究资料卡</p>
      <h1>研究资料卡</h1>
      <p class="scholar-lede">
        把语料库章节蒸馏成<strong>翻转背诵卡</strong>：正面是章节主题，背面是该节正文节选 + 出处。
        每张卡的内容都是快照原文节选，不是生成的摘要——点开背面即可回查出处路径。
      </p>
    </header>

    <div v-if="deck.length === 0" class="scholar-empty">
      <h3>这一组没有可用章节</h3>
      <p>蒸馏快照里该课程没有带正文的章节。换个课程范围，或执行 <code class="scholar-mono">npm run atlas:distill</code> 重新蒸馏。</p>
    </div>

    <template v-else>
      <section class="scholar-panel scholar-toolbar" aria-label="组卷控制">
        <div class="scholar-toolbar__row">
          <label class="scholar-muted" for="deck-course">课程</label>
          <select id="deck-course" v-model="courseId" class="scholar-select">
            <option value="">全部课程（{{ snapshot.totals.documents }} 篇）</option>
            <option v-for="course in deckCourses" :key="course.id" :value="course.id">{{ course.label }}（{{ course.count }} 张卡）</option>
          </select>
          <button class="scholar-btn scholar-btn--ghost" type="button" @click="step(-1)" :disabled="index === 0">上一张</button>
          <button class="scholar-btn" type="button" @click="step(1)" :disabled="index >= deck.length - 1">下一张</button>
          <span class="scholar-progress scholar-muted">{{ index + 1 }} / {{ deck.length }} · 已翻 {{ flippedCount }} 次</span>
        </div>
        <p class="scholar-meta scholar-muted">点击卡片翻转正面 / 背面。卡序按快照文档顺序排列（确定性组卷，无随机）。</p>
      </section>

      <!-- 知识树导航：课程 › 文档 › 章节，结构来自快照真实层级；已翻背面的章节节点点亮 -->
      <section class="scholar-panel scholar-tree" aria-label="知识树导航">
        <button
          type="button"
          class="scholar-tree__toggle"
          :aria-expanded="treeOpen"
          @click="treeOpen = !treeOpen"
        >
          <span>知识树 · 已学 {{ viewedInRange }}/{{ deck.length }}</span>
          <span class="scholar-tree__hint">{{ treeOpen ? '收起 ▲' : '展开 课程 › 文档 › 章节 ▼' }}</span>
        </button>
        <div v-show="treeOpen" class="scholar-tree__body">
          <div class="scholar-tree__bar" role="progressbar" :aria-valuenow="viewedInRange" :aria-valuemax="deck.length">
            <span class="scholar-tree__bar-fill" :style="{ width: `${deck.length ? (viewedInRange / deck.length) * 100 : 0}%` }"></span>
          </div>
          <div v-for="group in treeCourses" :key="group.label" class="scholar-tree__course">
            <button type="button" class="scholar-tree__course-name" :title="`切换到课程：${group.label}`" @click="jumpToCourse(group)">
              {{ group.label }}
            </button>
            <ul class="scholar-tree__docs">
              <li v-for="doc in group.docs" :key="doc.title">
                <button type="button" class="scholar-tree__doc" :aria-expanded="expandedDocs.has(doc.title)" @click="toggleDoc(doc.title)">
                  <span class="scholar-tree__doc-title">{{ doc.title }}</span>
                  <span class="scholar-muted">{{ docViewedCount(doc) }}/{{ doc.cards.length }}</span>
                </button>
                <ul v-show="expandedDocs.has(doc.title)" class="scholar-tree__sections">
                  <li v-for="card in doc.cards" :key="card.id">
                    <button
                      type="button"
                      class="scholar-tree__section"
                      :class="{ 'is-viewed': viewedCards.has(card.id) }"
                      @click="jumpToCard(card.id, doc.title)"
                    >
                      {{ card.front }}
                    </button>
                  </li>
                </ul>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section ref="cardZone" class="scholar-card-zone" aria-label="背诵卡">
        <button
          type="button"
          class="flip"
          :class="{ 'flip--back': flipped }"
          :aria-label="flipped ? '翻到正面' : '翻到背面'"
          @click="flip"
        >
          <span class="flip__inner">
            <span class="flip__face flip__face--front">
              <span class="flip__tag">{{ current.courseLabel }}</span>
              <strong class="flip__topic">{{ current.front }}</strong>
              <span class="flip__hint scholar-muted">出自：{{ current.source }} · 点击查看背面</span>
            </span>
            <span class="flip__face flip__face--back">
              <span class="flip__tag flip__tag--back">{{ current.back.docTitle }}</span>
              <p class="flip__excerpt">{{ current.back.excerpt }}</p>
              <span class="flip__hint scholar-muted"><code class="scholar-mono">{{ current.back.path }}</code></span>
              <span v-if="current.back.commands.length" class="flip__cmds">
                <code v-for="cmd in current.back.commands" :key="cmd" class="scholar-mono">{{ cmd }}</code>
              </span>
            </span>
          </span>
        </button>
      </section>
    </template>

    <footer class="scholar-foot">
      卡片来源：<code class="scholar-mono">atlasDistilled.json</code> 的章节节选（每篇最多 12 节，节选 ≤160 字）。
      背诵卡片是蒸馏而非生成——引用原文，不替原文发言。
    </footer>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import snapshot from '../atlas/atlasDistilled.json'
import { buildDeck } from '../../domain/scholar/scholarEngine.js'

const courseId = ref('')
const index = ref(0)
const flipped = ref(false)
const flippedCount = ref(0)
const cardZone = ref(null)

const deck = computed(() => buildDeck(snapshot, { courseId: courseId.value || null, limit: 60 }))
const current = computed(() => deck.value[index.value] ?? deck.value[0])

const deckCourses = computed(() => snapshot.courses
  .map(course => ({ id: course.id, label: course.label, count: buildDeck(snapshot, { courseId: course.id, limit: 60 }).length }))
  .filter(course => course.count > 0))

watch(courseId, () => { index.value = 0; flipped.value = false })

function step(delta) {
  index.value = Math.min(Math.max(index.value + delta, 0), Math.max(deck.value.length - 1, 0))
  flipped.value = false
}
function flip() {
  flipped.value = !flipped.value
  if (flipped.value) {
    flippedCount.value += 1
    markViewed(current.value.id)
  }
}

// ------------------------------------------------------------------
// 知识树导航 + 进度点亮：树结构完全来自 deck（快照真实层级），
// 点击章节节点定位到对应卡片；已翻背面的卡点亮（localStorage 持久真实浏览行为）。
// ------------------------------------------------------------------

const VIEWED_KEY = 'scholar-cards-viewed'
const treeOpen = ref(false)
const expandedDocs = ref(new Set())
const viewedCards = ref(loadViewedCards())

function loadViewedCards() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(VIEWED_KEY) || '[]')
    return new Set(Array.isArray(raw) ? raw : [])
  } catch {
    return new Set()
  }
}

function markViewed(cardId) {
  if (!cardId || viewedCards.value.has(cardId)) return
  const next = new Set(viewedCards.value)
  next.add(cardId)
  viewedCards.value = next
  try {
    window.localStorage.setItem(VIEWED_KEY, JSON.stringify([...next]))
  } catch { /* 隐私模式等 localStorage 不可用时仅本次会话生效 */ }
}

/* 树仅渲染当前 deck 范围（与卡片组严格同步，定位永不落空） */
const treeDocs = computed(() => {
  const docs = new Map()
  for (const card of deck.value) {
    if (!docs.has(card.source)) {
      docs.set(card.source, { title: card.source, courseId: card.courseId, cards: [] })
    }
    docs.get(card.source).cards.push({ id: card.id, front: card.front })
  }
  return [...docs.values()]
})

const treeCourses = computed(() => {
  const groups = new Map()
  for (const doc of treeDocs.value) {
    const course = snapshot.courses.find(item => item.id === doc.courseId)
    const label = course?.label || doc.courseId
    if (!groups.has(label)) groups.set(label, { label, docs: [] })
    groups.get(label).docs.push(doc)
  }
  return [...groups.values()]
})

const viewedInRange = computed(() => deck.value.filter(card => viewedCards.value.has(card.id)).length)

function docViewedCount(doc) {
  return doc.cards.filter(card => viewedCards.value.has(card.id)).length
}

/* 当前卡所在文档自动展开（其余保持用户手动状态），对齐「默认折叠仅当前域展开」惯例 */
watch(() => current.value?.source, (docTitle) => {
  if (!docTitle || expandedDocs.value.has(docTitle)) return
  expandedDocs.value = new Set([...expandedDocs.value, docTitle])
}, { immediate: true })

function toggleDoc(docTitle) {
  const next = new Set(expandedDocs.value)
  if (next.has(docTitle)) next.delete(docTitle)
  else next.add(docTitle)
  expandedDocs.value = next
}

function jumpToCourse(group) {
  const course = snapshot.courses.find(item => item.label === group.label)
  if (course && courseId.value !== course.id) courseId.value = course.id
}

function jumpToCard(cardId, docTitle) {
  const target = deck.value.findIndex(card => card.id === cardId)
  if (target < 0) return
  index.value = target
  flipped.value = false
  expandedDocs.value = new Set([...expandedDocs.value, docTitle])
  nextTick(() => cardZone.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
}
</script>

<style scoped>
.scholar-page { display: grid; gap: 16px; color: var(--smart-text, #1f2937); padding-bottom: 32px; }
.scholar-eyebrow { margin: 0 0 4px; font-size: 12px; font-weight: 700; letter-spacing: .08em; color: var(--smart-primary-strong, #2563eb); }
.scholar-head h1 { margin: 0 0 8px; font-size: 22px; }
.scholar-lede { margin: 0; max-width: 880px; font-size: 13.5px; line-height: 1.8; color: var(--smart-muted, #6b7280); }
.scholar-mono { font-family: var(--font-mono, Consolas, monospace); font-size: 11.5px; background: rgba(37, 99, 235, .08); padding: 1px 6px; border-radius: 4px; }
.scholar-muted { color: var(--smart-muted, #6b7280); }

.scholar-panel { border: 1px solid var(--smart-border, #e5e7eb); border-radius: 12px; background: var(--smart-surface, #fff); padding: 12px 16px; display: grid; gap: 8px; }
.scholar-toolbar__row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.scholar-select { padding: 7px 10px; border: 1px solid var(--smart-border, #e5e7eb); border-radius: 8px; background: var(--smart-surface, #fff); color: inherit; }
.scholar-btn { padding: 7px 16px; border: 0; border-radius: 8px; background: var(--smart-primary-strong, #2563eb); color: #fff; font-size: 13px; cursor: pointer; }
.scholar-btn--ghost { background: none; border: 1px solid var(--smart-border, #e5e7eb); color: var(--smart-text, #1f2937); }
.scholar-btn:disabled { opacity: .45; cursor: not-allowed; }
.scholar-progress { margin-left: auto; font-size: 12.5px; }
.scholar-meta { margin: 0; font-size: 12px; }
.scholar-empty { border: 1px dashed var(--smart-border, #e5e7eb); border-radius: 12px; padding: 24px; text-align: center; }
.scholar-empty p { margin: 0 auto; max-width: 560px; font-size: 13px; color: var(--smart-muted, #6b7280); line-height: 1.8; }

/* 知识树导航：默认折叠仅显示进度行；展开后限高滚动，避免挤占卡片首屏 */
.scholar-tree__toggle {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 0;
  border: 0;
  background: none;
  color: var(--smart-text, #1f2937);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}
.scholar-tree__toggle:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 4px; border-radius: 6px; }
.scholar-tree__hint { font-weight: 400; font-size: 12px; color: var(--smart-muted, #6b7280); }
.scholar-tree__body { display: grid; gap: 10px; margin-top: 10px; max-height: 320px; overflow-y: auto; }
.scholar-tree__bar { height: 4px; border-radius: 999px; background: rgba(37, 99, 235, .12); overflow: hidden; }
.scholar-tree__bar-fill { display: block; height: 100%; border-radius: inherit; background: var(--smart-primary-strong, #2563eb); transition: width .3s ease; }
.scholar-tree__course { display: grid; gap: 6px; }
.scholar-tree__course-name {
  justify-self: start;
  padding: 3px 10px;
  border: 1px solid var(--smart-border, #e5e7eb);
  border-radius: 999px;
  background: rgba(37, 99, 235, .06);
  color: var(--smart-primary-strong, #2563eb);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
.scholar-tree__course-name:hover { border-color: var(--smart-primary-strong, #2563eb); }
.scholar-tree__course-name:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 2px; }
.scholar-tree__docs { margin: 0; padding: 0 0 0 6px; list-style: none; display: grid; gap: 4px; }
.scholar-tree__docs > li { border-left: 2px solid var(--smart-border, #e5e7eb); padding-left: 10px; }
.scholar-tree__doc {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  width: 100%;
  padding: 4px 6px;
  border: 0;
  border-radius: 6px;
  background: none;
  color: var(--smart-text, #1f2937);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}
.scholar-tree__doc:hover { background: rgba(37, 99, 235, .06); }
.scholar-tree__doc:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 1px; }
.scholar-tree__doc-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scholar-tree__sections { margin: 2px 0 6px; padding: 0 0 0 12px; list-style: none; display: grid; gap: 2px; }
.scholar-tree__sections > li { border-left: 1px dashed var(--smart-border, #e5e7eb); padding-left: 10px; }
.scholar-tree__section {
  display: block;
  width: 100%;
  padding: 3px 6px;
  border: 0;
  border-radius: 6px;
  background: none;
  color: var(--smart-muted, #6b7280);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.scholar-tree__section:hover { background: rgba(37, 99, 235, .06); color: var(--smart-text, #1f2937); }
.scholar-tree__section:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 1px; }
.scholar-tree__section.is-viewed { color: var(--smart-primary-strong, #2563eb); }
.scholar-tree__section.is-viewed::before { content: '● '; font-size: 9px; vertical-align: 1px; }

/* 翻转卡：3D 翻转；reduced-motion 下退化为直接切换（无 transition） */
.scholar-card-zone { display: grid; place-items: center; min-height: 340px; }
.flip { width: min(680px, 100%); min-height: 300px; border: 0; background: none; padding: 0; cursor: pointer; perspective: 1200px; text-align: left; }
.flip:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 4px; border-radius: 14px; }
.flip__inner { position: relative; display: block; width: 100%; min-height: 300px; transition: transform .45s ease; transform-style: preserve-3d; }
.flip--back .flip__inner { transform: rotateY(180deg); }
.flip__face { position: absolute; inset: 0; display: flex; flex-direction: column; gap: 12px; padding: 26px 30px; border: 1px solid var(--smart-border, #e5e7eb); border-radius: 14px; background: var(--smart-surface, #fff); backface-visibility: hidden; -webkit-backface-visibility: hidden; }
.flip__face--back { transform: rotateY(180deg); background: rgba(37, 99, 235, .04); }
.flip__tag { font-size: 12px; color: var(--smart-primary-strong, #2563eb); letter-spacing: .04em; }
.flip__tag--back { color: var(--smart-muted, #6b7280); }
.flip__topic { font-size: 22px; line-height: 1.4; }
.flip__hint { margin-top: auto; font-size: 12px; }
.flip__excerpt { margin: 0; font-size: 14.5px; line-height: 1.9; }
.flip__cmds { display: flex; gap: 6px; flex-wrap: wrap; }

@media (prefers-reduced-motion: reduce) {
  .flip__inner { transition: none; }
}

.scholar-foot { border-top: 1px solid var(--smart-border, #e5e7eb); padding-top: 12px; font-size: 12px; color: var(--smart-muted, #6b7280); }
</style>
