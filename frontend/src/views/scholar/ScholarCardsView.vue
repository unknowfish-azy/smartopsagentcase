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
          <div class="scholar-tree__legend-row">
            <p class="scholar-tree__legend">
              依赖来自各课「前置知识」原文的先修课次；主干为快照文档顺序，非推断的硬依赖。
            </p>
            <div class="scholar-tree__views" role="group" aria-label="知识树视图切换">
              <button type="button" class="scholar-tree__view" :class="{ 'is-active': treeView === 'list' }" :aria-pressed="treeView === 'list'" @click="treeView = 'list'">列表</button>
              <button type="button" class="scholar-tree__view" :class="{ 'is-active': treeView === 'graph' }" :aria-pressed="treeView === 'graph'" @click="treeView = 'graph'">依赖图</button>
            </div>
            <label v-if="treeView === 'graph'" class="scholar-tree__weak-toggle">
              <input v-model="showWeak" type="checkbox">
              弱关联
            </label>
          </div>

          <!-- 依赖图：节点＝当前课程文档；纵向主干为顺序，右侧弧线为原文声明的先修课次 -->
          <div v-show="treeView === 'graph'" class="scholar-tree__graph">
            <p v-if="!graph.nodes.length" class="scholar-tree__deps-empty">当前课程没有可绘制的文档节点。</p>
            <svg
              v-else
              class="scholar-tree__svg"
              :viewBox="`0 0 ${graph.width} ${graph.height}`"
              preserveAspectRatio="xMinYMin meet"
              role="img"
              :aria-label="`依赖图：${graph.nodes.length} 个文档节点，${graph.edgeCount} 条先修连线，${graph.weakEdges.length} 条弱关联`"
            >
              <line
                v-for="rail in graph.rails"
                :key="rail.id"
                class="scholar-tree__rail"
                :x1="rail.x1" :y1="rail.y1" :x2="rail.x2" :y2="rail.y2"
              />
              <path
                v-for="edge in graph.edges"
                :key="edge.id"
                class="scholar-tree__edge"
                :class="[`is-${edge.kind}`, { 'is-focus': edge.focus }]"
                :d="edge.d"
              />
              <path
                v-for="edge in graph.weakEdges"
                :key="edge.id"
                class="scholar-tree__edge is-weak"
                :class="{ 'is-focus': edge.focus }"
                :d="edge.d"
              >
                <title>弱关联：共用 {{ edge.tools }}</title>
              </path>
              <g
                v-for="node in graph.nodes"
                :key="node.docId"
                class="scholar-tree__node"
                :class="{ 'is-viewed': node.viewed > 0, 'is-active': node.title === current?.source }"
                role="button"
                tabindex="0"
                :aria-label="`${node.title}，已学 ${node.viewed}/${node.total}，点击查看`"
                @click="jumpToDoc(node.title)"
                @keydown.enter.prevent="jumpToDoc(node.title)"
                @keydown.space.prevent="jumpToDoc(node.title)"
                @mouseenter="hoveredDocId = node.docId"
                @mouseleave="hoveredDocId = ''"
                @focus="hoveredDocId = node.docId"
                @blur="hoveredDocId = ''"
              >
                <title>{{ node.title }}（已学 {{ node.viewed }}/{{ node.total }}）</title>
                <rect :x="node.x" :y="node.y" :width="graph.nodeW" :height="graph.nodeH" rx="6" />
                <text :x="node.x + 8" :y="node.y + 15">{{ node.label }}</text>
              </g>
              <g v-for="ghost in graph.ghosts" :key="ghost.id" class="scholar-tree__ghost">
                <text :x="ghost.x" :y="ghost.y + 4">{{ ghost.label }}</text>
              </g>
            </svg>
            <p class="scholar-tree__legend">
              实线＝原文“已完成第 N 课”；短虚线＝原文“建议先完成”；长虚线＝共用专业工具推得的弱关联（非先修）；竖线主干＝快照文档顺序；灰字＝原文提到但快照未收录；悬停节点高亮其全部关联边。
            </p>
          </div>

          <div v-show="treeView === 'list'">
            <div v-for="group in treeCourses" :key="group.label" class="scholar-tree__course">
              <button type="button" class="scholar-tree__course-name" :title="`切换到课程：${group.label}`" @click="jumpToCourse(group)">
                {{ group.label }}
              </button>
              <ul class="scholar-tree__docs">
                <li v-for="doc in group.docs" :key="doc.docId">
                  <button type="button" class="scholar-tree__doc" :aria-expanded="expandedDocs.has(doc.title)" @click="toggleDoc(doc.title)">
                    <span class="scholar-tree__doc-title">{{ doc.title }}</span>
                    <span class="scholar-muted">
                      <span v-if="depsOf(doc).length" class="scholar-tree__dep-count" :title="depSummary(doc)">前置 {{ depsOf(doc).length }}</span>
                      {{ docViewedCount(doc) }}/{{ doc.cards.length }}
                    </span>
                  </button>
                  <div v-show="expandedDocs.has(doc.title)" class="scholar-tree__branch">
                    <div v-if="depsOf(doc).length" class="scholar-tree__deps">
                      <span class="scholar-tree__deps-label">依赖</span>
                      <button
                        v-for="dep in depsOf(doc)"
                        :key="`${dep.kind}-${dep.label}`"
                        type="button"
                        class="scholar-tree__dep"
                        :class="[`is-${dep.kind}`, { 'is-missing': !dep.docTitle }]"
                        :disabled="!dep.docTitle"
                        :title="dep.docTitle ? `跳转到 ${dep.docTitle}` : '原文提到的课次不在当前快照中'"
                        @click="jumpToDoc(dep.docTitle)"
                      >
                        {{ dep.label }}<span v-if="dep.kind === 'suggested'" class="scholar-tree__dep-note">·建议</span><span v-if="!dep.docTitle" class="scholar-tree__dep-note">·未收录</span>
                      </button>
                    </div>
                    <p v-else-if="declaredNoteOf(doc)" class="scholar-tree__deps-empty">
                      原文前置（未提课次）：{{ declaredNoteOf(doc) }}
                    </p>
                    <p v-else class="scholar-tree__deps-empty">原文未声明前置知识</p>
                    <ul class="scholar-tree__sections">
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
                  </div>
                </li>
              </ul>
            </div>
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
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import snapshot from '../atlas/atlasDistilled.json'
import { buildDeck, buildDependencyMap, buildDocCards, buildWeakLinkMap } from '../../domain/scholar/scholarEngine.js'

const route = useRoute()
const router = useRouter()

const courseId = ref('')
const index = ref(0)
const flipped = ref(false)
const flippedCount = ref(0)
const cardZone = ref(null)
/* 组卷上限默认 60；仅在跳转到更靠后的依赖目标时按需放大，不改变默认观感 */
const deckLimit = ref(60)

const deck = computed(() => buildDeck(snapshot, { courseId: courseId.value || null, limit: deckLimit.value }))
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
const treeView = ref('list')
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

/* 树渲染当前课程的全量文档（不随 60 张组卷上限截断），过滤规则与组卷同源 */
const treeDocs = computed(() => snapshot.documents
  .filter(doc => !courseId.value || doc.courseId === courseId.value)
  .map(doc => ({
    docId: doc.id,
    title: doc.title,
    courseId: doc.courseId,
    cards: buildDocCards(doc).map(card => ({ id: card.id, front: card.front }))
  }))
  .filter(doc => doc.cards.length > 0))

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

/* 依赖表由原文抽取，快照静态故只构建一次 */
const dependencyMap = buildDependencyMap(snapshot)
/* 弱关联：共用稀有专业工具（nsys/ncu 等）推得，属于关联而非先修 */
const weakLinks = buildWeakLinkMap(snapshot)
const showWeak = ref(true)
/* 图谱悬停/聚焦的文档，用于联动高亮其全部关联边 */
const hoveredDocId = ref('')

const viewedInRange = computed(() => deck.value.filter(card => viewedCards.value.has(card.id)).length)

function docViewedCount(doc) {
  return doc.cards.filter(card => viewedCards.value.has(card.id)).length
}

function depsOf(doc) {
  return dependencyMap.get(doc.docId)?.deps || []
}

/* 原文写了前置知识但没提课次时，展示原文首句，而不是断言「未声明」 */
function declaredNoteOf(doc) {
  const entry = dependencyMap.get(doc.docId)
  return entry?.declared && !entry.deps.length ? entry.excerpt : ''
}

function depSummary(doc) {
  return depsOf(doc).map(dep => `${dep.label}${dep.kind === 'suggested' ? '（建议）' : ''}`).join('、')
}

/**
 * 依赖图布局：纵向主干按快照文档顺序排列，跨课先修画成右侧弧线。
 * 纯前端 SVG 计算，无第三方图形库；未收录的课次画成灰字端点。
 */
const graph = computed(() => {
  const nodeW = 200
  const nodeH = 22
  const rowH = 30
  const baseX = 12
  const railX = 4
  const nodes = treeDocs.value.map((doc, order) => ({
    docId: doc.docId,
    title: doc.title,
    label: doc.title.length > 18 ? `${doc.title.slice(0, 18)}…` : doc.title,
    viewed: docViewedCount(doc),
    total: doc.cards.length,
    x: baseX,
    y: order * rowH + 6
  }))
  const byTitle = new Map(nodes.map(node => [node.title, node]))

  /* 主干：相邻节点竖线 + 每节点一段横向接入线 */
  const rails = []
  for (let i = 0; i < nodes.length - 1; i += 1) {
    const from = nodes[i]
    const to = nodes[i + 1]
    rails.push({ id: `rail-${i}`, x1: railX, y1: from.y + nodeH / 2, x2: railX, y2: to.y + nodeH / 2 })
    rails.push({ id: `tick-${i}`, x1: railX, y1: to.y + nodeH / 2, x2: baseX, y2: to.y + nodeH / 2 })
  }

  const edges = []
  const ghosts = []
  /* 悬停节点优先；未悬停时回落到当前卡所在文档 */
  const activeDocId = hoveredDocId.value ||
    nodes.find(node => node.title === current.value?.source)?.docId || ''
  for (const doc of treeDocs.value) {
    const source = byTitle.get(doc.title)
    for (const dep of depsOf(doc)) {
      if (dep.kind === 'order') continue /* 顺序关系已由主干表达，避免重复噪音 */
      const sy = source.y + nodeH / 2
      const target = dep.docTitle ? byTitle.get(dep.docTitle) : null
      if (target) {
        const ty = target.y + nodeH / 2
        const x1 = baseX + nodeW
        const bulge = x1 + 40 + Math.min(Math.abs(ty - sy) * 0.12, 56)
        edges.push({
          id: `${doc.docId}-${dep.kind}-${dep.label}`,
          kind: dep.kind,
          focus: doc.docId === activeDocId || target.docId === activeDocId,
          d: `M${x1},${sy} C${bulge},${sy} ${bulge},${ty} ${x1},${ty}`
        })
      } else {
        const gx = baseX + nodeW + 22
        ghosts.push({ id: `ghost-${doc.docId}-${dep.label}`, x: gx, y: sy, label: `${dep.label}·未收录` })
        edges.push({
          id: `missing-${doc.docId}-${dep.label}`,
          kind: 'missing',
          focus: doc.docId === activeDocId,
          d: `M${baseX + nodeW},${sy} L${gx - 4},${sy}`
        })
      }
    }
  }

  /* 弱关联走更外侧的弧线，避免与先修弧线重叠；与激活节点相连的弱关联一并高亮 */
  const weakEdges = []
  if (showWeak.value) {
    const byDocId = new Map(nodes.map(node => [node.docId, node]))
    for (const link of weakLinks) {
      const from = byDocId.get(link.a)
      const to = byDocId.get(link.b)
      if (!from || !to) continue
      const y1 = from.y + nodeH / 2
      const y2 = to.y + nodeH / 2
      const x1 = baseX + nodeW
      const bulge = x1 + 120 + Math.min(Math.abs(y2 - y1) * 0.05, 60)
      weakEdges.push({
        id: `weak-${link.a}-${link.b}`,
        focus: link.a === activeDocId || link.b === activeDocId,
        tools: link.shared.join('/'),
        d: `M${x1},${y1} C${bulge},${y1} ${bulge},${y2} ${x1},${y2}`
      })
    }
  }

  return {
    nodes,
    rails,
    edges,
    ghosts,
    weakEdges,
    nodeW,
    nodeH,
    width: baseX + nodeW + 200,
    height: Math.max(nodes.length * rowH + 12, 40),
    edgeCount: edges.filter(edge => edge.kind !== 'missing').length
  }
})

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

/* 跳到依赖目标文档：必要时切课程并放大组卷上限，确保目标卡确实在组内 */
function jumpToDoc(docTitle, { scroll = true } = {}) {
  if (!docTitle) return
  const target = snapshot.documents.find(doc => doc.title === docTitle)
  if (!target) return
  const targetIndex = buildDeck(snapshot, { courseId: target.courseId, limit: Number.MAX_SAFE_INTEGER })
    .findIndex(card => card.source === target.title)
  if (targetIndex < 0) return
  if (deckLimit.value < targetIndex + 1) deckLimit.value = targetIndex + 1
  expandedDocs.value = new Set([...expandedDocs.value, target.title])
  /* 切课程会经 watch 归零索引，故在渲染更新后再定位 */
  if (courseId.value !== target.courseId) courseId.value = target.courseId
  nextTick(() => {
    index.value = targetIndex
    flipped.value = false
    if (scroll) cardZone.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
}

/* URL 回写：当前文档写入 ?doc=<id>，刷新或分享链接可直达同一文档 */
const DOC_QUERY = 'doc'

function docIdByTitle(docTitle) {
  return snapshot.documents.find(doc => doc.title === docTitle)?.id || ''
}

onMounted(() => {
  const docId = String(route.query[DOC_QUERY] || '')
  if (!docId) return
  const doc = snapshot.documents.find(item => item.id === docId)
  if (doc) jumpToDoc(doc.title, { scroll: false })
})

watch(() => current.value?.source, (docTitle) => {
  const docId = docTitle ? docIdByTitle(docTitle) : ''
  if (docId === String(route.query[DOC_QUERY] || '')) return
  const query = { ...route.query }
  if (docId) query[DOC_QUERY] = docId
  else delete query[DOC_QUERY]
  router.replace({ query })
})
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

/* 依赖标注：required 实线 / suggested 虚线 / order 灰底 / missing 斜体灰 */
.scholar-tree__legend { margin: 0; font-size: 11.5px; line-height: 1.6; color: var(--smart-muted, #6b7280); }
.scholar-tree__branch { display: grid; gap: 4px; }
.scholar-tree__deps { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; padding: 2px 0 4px 4px; }
.scholar-tree__deps-label { font-size: 11px; color: var(--smart-muted, #6b7280); }
.scholar-tree__dep {
  padding: 1px 8px;
  border: 1px solid var(--smart-primary-strong, #2563eb);
  border-radius: 999px;
  background: rgba(37, 99, 235, .08);
  color: var(--smart-primary-strong, #2563eb);
  font-size: 11px;
  cursor: pointer;
}
.scholar-tree__dep:hover:not(:disabled) { background: rgba(37, 99, 235, .16); }
.scholar-tree__dep:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 2px; }
.scholar-tree__dep.is-suggested { border-style: dashed; background: none; }
.scholar-tree__dep.is-order {
  border-color: var(--smart-border, #e5e7eb);
  background: rgba(107, 114, 128, .08);
  color: var(--smart-muted, #6b7280);
}
.scholar-tree__dep.is-missing {
  border-style: dashed;
  border-color: var(--smart-border, #e5e7eb);
  background: none;
  color: var(--smart-muted, #6b7280);
  cursor: not-allowed;
}
.scholar-tree__dep-note { opacity: .8; }
.scholar-tree__dep-count {
  margin-right: 6px;
  padding: 0 5px;
  border-radius: 999px;
  background: rgba(37, 99, 235, .12);
  color: var(--smart-primary-strong, #2563eb);
  font-size: 10.5px;
}
.scholar-tree__deps-empty { margin: 0 0 2px 4px; font-size: 11px; color: var(--smart-muted, #6b7280); }

/* 依赖图：纯 SVG，主干竖线 + 右侧贝塞尔先修弧线 */
.scholar-tree__legend-row { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 6px 12px; }
.scholar-tree__views { display: inline-flex; flex: none; border: 1px solid var(--smart-border, #e5e7eb); border-radius: 999px; overflow: hidden; }
.scholar-tree__view {
  padding: 2px 10px;
  border: 0;
  background: none;
  color: var(--smart-muted, #6b7280);
  font-size: 11.5px;
  cursor: pointer;
  transition: background .15s ease, color .15s ease;
}
.scholar-tree__view.is-active { background: var(--smart-primary-strong, #2563eb); color: #fff; }
.scholar-tree__view:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 1px; }
.scholar-tree__graph { display: grid; gap: 6px; }
.scholar-tree__svg { display: block; width: 100%; max-width: 420px; height: auto; }
.scholar-tree__rail { stroke: var(--smart-border, #d1d5db); stroke-width: 1.5; }
.scholar-tree__edge { fill: none; stroke: var(--smart-primary-strong, #2563eb); stroke-width: 1.4; }
/* 悬停节点联动：与该节点相连的边加粗提亮 */
.scholar-tree__edge.is-focus { stroke-width: 2.2; opacity: 1; }
.scholar-tree__edge.is-suggested { stroke-dasharray: 4 3; opacity: .85; }
.scholar-tree__edge.is-missing { stroke: var(--smart-muted, #9ca3af); stroke-dasharray: 2 3; }
.scholar-tree__node { cursor: pointer; }
.scholar-tree__node rect { fill: var(--smart-surface, #fff); stroke: var(--smart-border, #d1d5db); stroke-width: 1; }
.scholar-tree__node text { font-size: 11px; fill: var(--smart-text, #1f2937); pointer-events: none; }
.scholar-tree__node:hover rect,
.scholar-tree__node:focus-visible rect { stroke: var(--smart-primary-strong, #2563eb); }
.scholar-tree__node:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 1px; }
.scholar-tree__node.is-viewed rect { fill: rgba(37, 99, 235, .10); stroke: rgba(37, 99, 235, .5); }
.scholar-tree__node.is-active rect { stroke-width: 2; stroke: var(--smart-primary-strong, #2563eb); }
.scholar-tree__ghost text { font-size: 10.5px; fill: var(--smart-muted, #9ca3af); }
/* 弱关联：长虚线、低对比，当前卡相关的高亮；与先修弧线区分 */
.scholar-tree__edge.is-weak {
  stroke: #0f9d8f;
  stroke-width: 1.2;
  stroke-dasharray: 8 4;
  stroke-linecap: butt;
  opacity: .38;
  transition: opacity .15s ease, stroke-width .15s ease;
}
.scholar-tree__edge.is-weak.is-focus { opacity: .95; stroke-width: 1.8; }
.scholar-tree__weak-toggle {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 5px;
  color: var(--smart-muted, #6b7280);
  font-size: 11.5px;
  cursor: pointer;
}

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
