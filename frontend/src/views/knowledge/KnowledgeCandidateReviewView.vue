<template>
  <section class="kr-page" :class="{ 'kr-page--side-open': sideOpen }">
    <div class="kr-main">
      <header class="kr-head">
        <div class="kr-head__text">
          <p class="kr-head__overline">KNOWLEDGE REVIEW · ENTRY GRAPH</p>
          <h1>知识候选审核</h1>
          <p class="kr-head__desc">主视图是泳道图：每条候选的来源、归属与审核事件一眼看完；候选正文与证据退到右侧栏。</p>
        </div>
        <span class="kr-head__pending">{{ pendingLabel }}</span>
      </header>

      <ReviewGraph
        ref="graphRef"
        :model="graph"
        :library-name="libraryLabel"
        :selected-id="selectedId"
        :color-mode="colorMode"
        :density="density"
        :guide-mode="guideMode"
        :entry-note="entryNote"
        :truncated="truncated"
        :total="total"
        @select="toggleCandidate"
        @act="onRowAction"
        @menu="openMenu"
        @update:color-mode="colorMode = $event"
        @update:density="density = $event"
        @load-more="loadMore"
      />
    </div>

    <!-- 侧栏：证据 + 正文 + 操作 -->
    <aside v-if="sideOpen" class="kr-side" aria-live="polite" aria-label="候选证据与正文">
      <header class="kr-side__head">
        <button class="kr-side__close" @click="closeSide" aria-label="关闭">×</button>
        <p class="kr-side__overline">Candidate #{{ detail?.id ?? selectedId }}</p>
        <h2>{{ detail?.title || '加载中…' }}</h2>
        <div class="kr-side__tags">
          <span v-if="detail" class="kr-tag" :class="'kr-tag--' + statusClass(detail.status)">{{ statusLabel(detail.status) }}</span>
          <span class="kr-tag kr-tag--target">目标条目 · {{ detailEntry ? detailEntry.title : '待归类' }}</span>
          <span v-if="detail?.isGuide" class="kr-tag kr-tag--demo">演示数据</span>
        </div>
      </header>

      <template v-if="detail">
        <dl class="kr-side__facts">
          <div><dt>来源工具</dt><dd>{{ detail.toolId }}</dd></div>
          <div><dt>来源 Trace</dt><dd><DecodeText :value="detail.traceId" tag="code" /></dd></div>
          <div><dt>运行记录</dt><dd>#{{ detail.sourceRunId }}</dd></div>
          <div><dt>生成时间</dt><dd>{{ formatTime(detail.createdAt) }}</dd></div>
          <div>
            <dt>目标条目</dt>
            <dd class="kr-side__fact-text">{{ detailEntry ? `${detailEntry.title} · v${detailEntry.version}` : '待归类（source_ref 无对应条目）' }}</dd>
          </div>
        </dl>

        <div class="kr-side__notice">
          <strong>待人工审核 · 人工审核要求</strong>
          <span>区分事实、推测与待验证项；核对敏感信息、组件版本、风险、回滚与验证结果。</span>
        </div>

        <!-- ECharts 证据关系图（从主位挪到侧栏） -->
        <div class="kr-side__graph">
          <p class="kr-side__graph-label">证据关系</p>
          <KnowledgeReviewGraph :candidate="detail" />
        </div>

        <article class="kr-side__doc" v-html="renderedMarkdown"></article>

        <footer class="kr-side__foot">
          <button
            class="kr-btn kr-btn--primary"
            :disabled="!canReview"
            :title="adoptHint"
            @click="openAction('adopt', detail, $event)"
          >采纳并新建条目</button>
          <button class="kr-btn" :disabled="!canReview" @click="openAction('reject', detail, $event)">驳回并记录原因</button>
        </footer>
      </template>

      <p v-else class="kr-side__loading">正在读取候选详情…</p>
    </aside>

    <!-- 就地审核 popover：采纳要先选知识库与标题，驳回原因必填；提交前重新校验状态。 -->
    <div v-if="action" class="kr-pop-scrim" @click.self="closeAction">
      <form class="kr-pop" :style="actionStyle" @submit.prevent>
        <h4>{{ action.type === 'adopt' ? '采纳并新建条目' : '驳回并记录原因' }}</h4>
        <p class="kr-pop__cand">{{ action.candidate.title }}</p>

        <template v-if="action.type === 'adopt'">
          <label class="kr-pop__field">
            <span>目标知识库</span>
            <select v-model.number="adoptTarget">
              <option v-for="library in libraries" :key="library.id" :value="library.id">
                {{ library.name || `知识库 #${library.id}` }}
              </option>
            </select>
          </label>
          <label class="kr-pop__field">
            <span>条目标题</span>
            <input ref="titleInputRef" v-model="adoptTitle" placeholder="条目标题" @keydown.enter.prevent="confirmAdopt" />
          </label>
          <p class="kr-pop__hint">将在所选知识库新建条目 v1（未验证）。后端 promote 只能新建，不能并入已有条目。</p>
          <p v-if="actionError" class="kr-pop__error" role="alert">{{ actionError }}</p>
          <code class="kr-pop__req">POST /api/knowledge/candidates/{{ action.candidate.id }}/promote → 知识库 #{{ adoptTarget }} 新建条目</code>
        </template>

        <template v-else>
          <label class="kr-pop__field">
            <span>驳回原因</span>
            <input ref="reasonInputRef" v-model="rejectReason" placeholder="例：证据不足（缺上游日志）" @keydown.enter.prevent="confirmReject" />
          </label>
          <p class="kr-pop__hint">原因会追加到候选摘要，不可为空。</p>
          <p v-if="actionError" class="kr-pop__error" role="alert">{{ actionError }}</p>
          <code class="kr-pop__req">POST /api/knowledge/candidates/{{ action.candidate.id }}/reject → summary</code>
        </template>

        <div class="kr-pop__acts">
          <button type="button" class="kr-btn" @click="closeAction">取消</button>
          <button
            v-if="action.type === 'adopt'"
            type="button"
            class="kr-btn kr-btn--primary"
            :disabled="actionBusy"
            @click="confirmAdopt"
          >确认采纳</button>
          <button
            v-else
            type="button"
            class="kr-btn kr-btn--primary"
            :disabled="actionBusy"
            @click="confirmReject"
          >确认驳回</button>
        </div>
      </form>
    </div>

    <!-- 右键 / Shift+F10 的审核快捷菜单：可用项写请求，置灰项写根本原因。 -->
    <ReviewActionMenu
      v-if="menu"
      :target="menu.row"
      :libraries="libraries"
      :guide-mode="guideMode"
      :top="menu.top"
      :left="menu.left"
      @action="onMenuAction"
      @close="menu = null"
    />

    <!-- toast -->
    <div v-if="toast" class="kr-toast" :class="{ 'kr-toast--on': toast }">
      {{ toast.msg }}
      <span v-if="toast.req" class="kr-toast__req">{{ toast.req }}</span>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { getKnowledgeCandidate, getKnowledgeCandidates, promoteKnowledgeCandidate, rejectKnowledgeCandidate } from '../../api/operations.ts'
import { getKnowledgeEntries, listKnowledgeLibraries } from '../../api/personalKnowledge.ts'
import { knowledgeEntryGuides, reviewQueueWithGuide } from '../../components/knowledge/knowledgeCandidateGuide.js'
import { renderKnowledgeMarkdown } from '../../components/knowledge/renderKnowledgeMarkdown.js'
import DecodeText from '../../components/common/DecodeText.vue'
import KnowledgeReviewGraph from '../../components/knowledge/KnowledgeReviewGraph.vue'
import ReviewGraph from './reviewGraph/ReviewGraph.vue'
import ReviewActionMenu from './reviewGraph/ReviewActionMenu.vue'
import { buildReviewGraph } from './reviewGraph/useReviewGraph.js'

/* 后端把 pageSize 上限钳到 100（KnowledgeCandidateService#list），这里就用满上限。 */
const PAGE_SIZE = 100

const candidates = ref([])
const libraries = ref([])
const entries = ref([])
const total = ref(0)
const pagesLoaded = ref(1)
const guideMode = ref(false)
const entryNote = ref('')
const colorMode = ref('tool')
const density = ref('comfortable')
const selectedId = ref(null)
const detail = ref(null)
const loadingMore = ref(false)
const action = ref(null)
const actionError = ref('')
const actionBusy = ref(false)
const adoptTarget = ref(null)
const adoptTitle = ref('')
const rejectReason = ref('')
const graphRef = ref(null)
const menu = ref(null)
const titleInputRef = ref(null)
const reasonInputRef = ref(null)
const toast = ref(null)
let toastTimer = null

/* 演示模式没有后端条目，补一条带 isGuide 的演示条目，泳道图才能演示「条目 + 采纳事件」。 */
const graphEntries = computed(() => (guideMode.value ? [...entries.value, ...knowledgeEntryGuides] : entries.value))

const graph = computed(() => buildReviewGraph({
  candidates: candidates.value,
  entries: graphEntries.value,
  colorMode: colorMode.value,
  density: density.value
}))

const sideOpen = computed(() => selectedId.value != null)
const truncated = computed(() => !guideMode.value && total.value > candidates.value.length)
const pendingLabel = computed(() => (guideMode.value
  ? '演示数据 · 不计统计'
  : `待人工审核 ${graph.value.stats.pending}`))

const libraryLabel = computed(() => {
  const list = libraries.value
  if (!list.length) return '未建知识库'
  if (list.length === 1) return list[0].name || `知识库 #${list[0].id}`
  return `${list.length} 个知识库`
})

const detailEntry = computed(() => {
  const candidate = detail.value
  if (!candidate?.traceId) return null
  return graph.value.entryByTrace.get(String(candidate.traceId)) || null
})

const adoptLibraryId = computed(() => libraries.value[0]?.id ?? null)
const canReview = computed(() => Boolean(detail.value)
  && detail.value.status === 'PENDING_REVIEW'
  && !detail.value.isGuide
  && adoptLibraryId.value != null)
const adoptHint = computed(() => {
  if (!detail.value) return ''
  if (detail.value.isGuide) return '演示数据不写库'
  if (detail.value.status !== 'PENDING_REVIEW') return statusLabel(detail.value.status)
  if (adoptLibraryId.value == null) return '先创建知识库才能采纳（后端 promote 必须带 libraryId）'
  return `写入知识库：${libraryLabel.value} · 新建条目 v1（未验证）`
})

const renderedMarkdown = computed(() => renderKnowledgeMarkdown(detail.value?.contentMarkdown))

const actionStyle = computed(() => ({
  top: `${action.value?.top ?? 120}px`,
  left: `${action.value?.left ?? 24}px`
}))

const unwrap = response => response?.data ?? response
const formatTime = value => value
  ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium', hour12: false }).format(new Date(value))
  : '—'

function statusClass(status) {
  if (status === 'PENDING_REVIEW') return 'waiting'
  if (status === 'PROMOTED') return 'done'
  if (status === 'REJECTED') return 'rejected'
  return 'quiet'
}

/* 生成中状态拿不到候选列表（缺口 C），所以未知状态如实写「未知状态」，不伪造「生成中」。 */
function statusLabel(status) {
  return { PENDING_REVIEW: '待审', PROMOTED: '已采纳', REJECTED: '已驳回' }[status] || '未知状态'
}

function showToast(msg, req) {
  toast.value = { msg, req }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, 3600)
}

async function loadCandidates() {
  /* 不传 status：后端把 status 当等值条件，传 'ALL' 会得到 WHERE status='ALL' 的空结果。 */
  const result = reviewQueueWithGuide(unwrap(await getKnowledgeCandidates({
    page: 1,
    pageSize: PAGE_SIZE
  })))
  candidates.value = result.items || []
  total.value = result.total || 0
  guideMode.value = Boolean(result.guideMode)
  pagesLoaded.value = 1
}

/* 条目泳道的数据源：每个知识库拉全量条目，按 source_ref 与候选 trace_id 回挂。
   只取第一页会让第 101 条之后的条目匹配不到候选，把已有条目的候选误标成「待归类」，
   所以这里翻页到底；上限 10 页，超出时在页脚如实标注而不是静默丢弃。 */
const ENTRY_PAGE_SIZE = 100
const ENTRY_PAGE_LIMIT = 10

async function loadEntries(libraryList) {
  const pages = await Promise.all(libraryList.map(async library => {
    const collected = []
    try {
      for (let page = 1; page <= ENTRY_PAGE_LIMIT; page += 1) {
        const result = unwrap(await getKnowledgeEntries(library.id, { page, pageSize: ENTRY_PAGE_SIZE }))
        const items = Array.isArray(result?.items) ? result.items : []
        collected.push(...items)
        const total = Number(result?.total ?? items.length)
        if (items.length < ENTRY_PAGE_SIZE || collected.length >= total) break
        if (page === ENTRY_PAGE_LIMIT) {
          entryNote.value = `知识库「${library.name || library.id}」条目超过 ${ENTRY_PAGE_LIMIT * ENTRY_PAGE_SIZE} 条，超出部分未参与泳道匹配`
        }
      }
    } catch (cause) {
      entryNote.value = `知识库「${library.name || library.id}」条目读取失败：${cause.message || '未知错误'}`
    }
    return collected
  }))
  return pages.flat()
}

async function loadLibraries() {
  try {
    const data = unwrap(await listKnowledgeLibraries())
    libraries.value = Array.isArray(data) ? data : (data?.items || [])
    entries.value = await loadEntries(libraries.value)
  } catch (cause) {
    entryNote.value = `知识库读取失败：${cause.message || '未知错误'}，候选暂时全部落在「待归类」`
  }
}

async function loadWorkspace() {
  try {
    await Promise.all([loadCandidates(), loadLibraries()])
  } catch (cause) {
    showToast('候选加载失败', cause.message || '请检查后端服务与数据库连接')
  }
}

async function loadMore() {
  if (loadingMore.value) return
  loadingMore.value = true
  try {
    const nextPage = pagesLoaded.value + 1
    const page = unwrap(await getKnowledgeCandidates({ page: nextPage, pageSize: PAGE_SIZE }))
    const merged = new Map(candidates.value.map(candidate => [candidate.id, candidate]))
    for (const candidate of page?.items || []) merged.set(candidate.id, candidate)
    candidates.value = [...merged.values()]
    pagesLoaded.value = nextPage
  } catch (cause) {
    showToast('加载更早的候选失败', cause.message)
  } finally {
    loadingMore.value = false
  }
}

async function loadDetail(id) {
  try {
    const selected = candidates.value.find(candidate => candidate.id === id)
    detail.value = selected?.isGuide ? selected : unwrap(await getKnowledgeCandidate(id))
  } catch (cause) {
    showToast('详情加载失败', cause.message)
    detail.value = null
  }
}

function toggleCandidate(id) {
  if (selectedId.value === id) { closeSide(); return }
  selectedId.value = id
  detail.value = null
  loadDetail(id)
}

function closeSide() {
  detail.value = null
  selectedId.value = null
}

function onRowAction(payload) {
  openAction(payload.type, payload.candidate, payload.anchor)
}

/* 动作面板贴着触发按钮出现，并夹在视口内；不遮挡整页，只挡一次点击。 */
function openAction(type, candidate, anchor) {
  if (!candidate) return
  if (candidate.isGuide) { showToast('演示数据不可写库', 'guideMode 候选不调用 promote / reject'); return }
  if (candidate.status !== 'PENDING_REVIEW') {
    showToast(`该候选已是「${statusLabel(candidate.status)}」`, '只有 PENDING_REVIEW 可以采纳或驳回')
    return
  }
  const width = 320
  const rect = anchor?.getBoundingClientRect?.()
  const top = rect ? Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - 300)) : 120
  const left = rect ? Math.min(Math.max(12, rect.right - width), window.innerWidth - width - 12) : 24
  action.value = { type, candidate, top, left }
  actionError.value = ''
  actionBusy.value = false
  if (type === 'adopt') {
    adoptTarget.value = adoptLibraryId.value
    adoptTitle.value = candidate.title || ''
    // 键盘路径：打开即把焦点放进标题框，回车直接确认（库与标题都有默认值）。
    nextTick(() => {
      titleInputRef.value?.focus?.()
      titleInputRef.value?.select?.()
    })
  } else {
    rejectReason.value = ''
    nextTick(() => reasonInputRef.value?.focus?.())
  }
}

function closeAction() {
  action.value = null
  actionError.value = ''
  actionBusy.value = false
}

const isConflict = cause => (cause?.status ?? cause?.response?.status) === 409

/* 写操作之后一律以服务端为准：重新拉列表与条目，选中项若还开着就重新读详情。 */
async function refreshAfterChange(id) {
  await loadWorkspace()
  if (selectedId.value === id) await loadDetail(id)
}

async function confirmAdopt() {
  const target = action.value?.candidate
  if (!target) return
  if (adoptTarget.value == null) { actionError.value = '请选择目标知识库'; return }
  const title = adoptTitle.value.trim()
  if (!title) { actionError.value = '条目标题不能为空'; return }
  actionError.value = ''
  actionBusy.value = true
  try {
    // 提交前重新校验：状态已被处理就什么都不写，直接刷新成真实状态。
    const fresh = unwrap(await getKnowledgeCandidate(target.id))
    if (fresh?.status !== 'PENDING_REVIEW') {
      closeAction()
      showToast('该候选已被处理', `服务端当前状态：${statusLabel(fresh?.status)}；未提交 promote`)
      await refreshAfterChange(target.id)
      return
    }
    await promoteKnowledgeCandidate(target.id, {
      libraryId: adoptTarget.value,
      title,
      contentMarkdown: fresh.contentMarkdown ?? target.contentMarkdown
    })
    const library = libraries.value.find(item => item.id === adoptTarget.value)
    const libraryName = library?.name || `知识库 #${adoptTarget.value}`
    closeAction()
    showToast(
      `已采纳：在「${libraryName}」新建条目「${title}」v1（未验证）`,
      `POST /api/knowledge/candidates/${target.id}/promote → 知识库 ${adoptTarget.value} 新建条目`
    )
    await refreshAfterChange(target.id)
  } catch (cause) {
    if (isConflict(cause)) {
      closeAction()
      showToast('该候选已被处理', '409 KNOWLEDGE_CANDIDATE_NOT_PENDING；已刷新为服务端真实状态')
      await refreshAfterChange(target.id)
      return
    }
    actionBusy.value = false
    actionError.value = cause.message || '采纳失败，请重试'
  }
}

async function confirmReject() {
  const target = action.value?.candidate
  if (!target) return
  const reason = rejectReason.value.trim()
  if (!reason) { actionError.value = '请填写驳回原因'; return }
  actionError.value = ''
  actionBusy.value = true
  try {
    await rejectKnowledgeCandidate(target.id, reason)
    closeAction()
    showToast('已驳回：原因已追加到候选摘要', `POST /api/knowledge/candidates/${target.id}/reject → summary`)
    await refreshAfterChange(target.id)
  } catch (cause) {
    if (isConflict(cause)) {
      closeAction()
      showToast('该候选已被处理', '409 KNOWLEDGE_CANDIDATE_NOT_PENDING；已刷新为服务端真实状态')
      await refreshAfterChange(target.id)
      return
    }
    actionBusy.value = false
    actionError.value = cause.message || '驳回失败，请重试'
  }
}

/* ---------- 快捷菜单（右键 / Shift+F10） ---------- */

function openMenu({ row, x, y }) {
  const width = 300
  const left = Math.max(12, Math.min(x, window.innerWidth - width - 12))
  const top = Math.max(12, Math.min(y, window.innerHeight - 420))
  action.value = null
  menu.value = { row, top, left }
}

function onMenuAction(key) {
  const open = menu.value
  menu.value = null
  if (!open) return
  const anchor = { getBoundingClientRect: () => ({ bottom: open.top, right: open.left + 40 }) }
  if (key === 'adopt') { openAction('adopt', open.row.candidate, anchor); return }
  if (key === 'reject') { openAction('reject', open.row.candidate, anchor); return }
  if (key === 'evidence') { if (open.row.candidate) toggleCandidate(open.row.candidate.id); return }
  if (key === 'copy-trace') copyTrace(open.row.candidate)
}

async function copyTrace(candidate) {
  if (!candidate?.traceId) return
  try {
    await navigator.clipboard.writeText(candidate.traceId)
    showToast('已复制 Trace ID', candidate.traceId)
  } catch {
    showToast('复制失败', '浏览器拒绝了剪贴板写入')
  }
}

/* ---------- 键盘（DESIGN §6.3）：状态在 ReviewGraph，这里统一分发 ---------- */

function isTypingTarget(target) {
  if (!(target instanceof HTMLElement)) return false
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable
}

function onKeydown(event) {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return
  if (isTypingTarget(event.target)) {
    if (event.key === 'Escape' && action.value) { event.preventDefault(); closeAction() }
    return
  }
  // 行内按钮自己的回车/空格交给浏览器，避免和全局 Enter 重复触发。
  const onButton = event.target instanceof HTMLElement && event.target.closest('button')
  if (onButton && (event.key === 'Enter' || event.key === ' ')) return

  const api = graphRef.value

  if (event.key === 'Escape') {
    if (menu.value) { menu.value = null; event.preventDefault(); return }
    if (action.value) { closeAction(); event.preventDefault(); return }
    if (selectedId.value != null) { closeSide(); event.preventDefault(); return }
    if (api?.clearFocus()) { event.preventDefault(); return }
    if (api?.clearFilter()) { event.preventDefault() }
    return
  }

  if (menu.value || action.value || !api) return

  const key = event.key
  /* 键盘焦点是虚拟焦点（行上只有 ring），Shift+F10 在这里兜底；行内真焦点时由行自己处理。 */
  if (key === 'F10' && event.shiftKey) {
    const row = api.focusedRow()
    if (row) {
      const rect = api.focusTarget()?.getBoundingClientRect?.()
      event.preventDefault()
      openMenu({ row, x: rect ? rect.right - 24 : 24, y: rect ? rect.top : 80 })
    }
    return
  }
  if (key === 'ArrowDown' || key === 'ArrowUp') {
    event.preventDefault()
    api.moveFocus(key === 'ArrowDown' ? 1 : -1)
    return
  }
  if (key === '?') { event.preventDefault(); api.toggleLegend(); return }
  if (key === 'f' || key === 'F') { if (api.focusChain()) event.preventDefault(); return }

  const row = api.focusedRow()
  if (key === 'Enter') {
    if (row?.candidate) { event.preventDefault(); toggleCandidate(row.candidate.id) }
    return
  }
  if (key === 'a' || key === 'A') {
    if (row) { event.preventDefault(); openAction('adopt', row.candidate, api.focusTarget()) }
    return
  }
  if (key === 'r' || key === 'R') {
    if (row) { event.preventDefault(); openAction('reject', row.candidate, api.focusTarget()) }
  }
}

onMounted(() => {
  loadWorkspace()
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  clearTimeout(toastTimer)
})
</script>

<style scoped>
.kr-page { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; align-items: start; }

.kr-main { min-width: 0; }

.kr-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; padding: 28px 0 16px; }
.kr-head__text { min-width: 0; }
.kr-head__overline { margin: 0 0 6px; font: 11px/1 var(--ds-font-mono); letter-spacing: .12em; color: var(--ds-semantic-neutral); text-transform: uppercase; }
.kr-head h1 { margin: 0 0 6px; font-size: var(--ds-type-h2-size, 26px); font-weight: 500; color: var(--ds-color-text); }
.kr-head__desc { margin: 0; max-width: 62ch; font-size: 12.5px; line-height: 1.6; color: var(--ds-color-muted); }
.kr-head__pending { flex: none; padding: 4px 10px; border-radius: var(--ds-radius-pill); background: var(--ds-pill-warning-bg); border: 1px solid color-mix(in srgb, var(--ds-semantic-warning) 34%, transparent); color: var(--ds-semantic-warning); font-size: 11.5px; white-space: nowrap; }

/* 侧栏 */
.kr-page--side-open { grid-template-columns: minmax(0, 1fr) 400px; }
.kr-side { position: sticky; top: 72px; max-height: calc(100dvh - 96px); border: 1px solid var(--ds-color-border); border-radius: var(--ds-radius-lg); background: var(--ds-surface-raised); display: flex; flex-direction: column; overflow: hidden; }
.kr-side__head { position: relative; padding: 16px 18px 14px; border-bottom: 1px solid var(--ds-hairline); }
.kr-side__head,
.kr-side__facts,
.kr-side__notice,
.kr-side__graph,
.kr-side__foot { flex: none; }
.kr-side__close { position: absolute; top: 12px; right: 14px; width: 28px; height: 28px; border: 0; border-radius: var(--ds-radius-sm); background: none; color: var(--ds-color-muted); font-size: 20px; cursor: pointer; }
.kr-side__close:hover { background: var(--ds-surface-base); color: var(--ds-color-text); }
.kr-side__overline { margin: 0 0 6px; font: 11px/1 var(--ds-font-mono); letter-spacing: .12em; color: var(--ds-semantic-neutral); }
.kr-side__head h2 { margin: 0 0 10px; font-size: var(--ds-type-h3-size, 18px); font-weight: 500; line-height: 1.35; color: var(--ds-color-text); }
.kr-side__tags { display: flex; gap: 6px; flex-wrap: wrap; }
.kr-side__loading { margin: 0; padding: 20px 18px; font-size: 12px; color: var(--ds-color-muted); }
.kr-tag { display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: var(--ds-radius-sm); border: 1px solid color-mix(in srgb, var(--ds-color-text) 10%, transparent); font-size: 11.5px; color: var(--ds-color-muted); }
.kr-tag--waiting { color: var(--ds-semantic-warning); border-color: color-mix(in srgb, var(--ds-semantic-warning) 42%, transparent); background: var(--ds-pill-warning-bg); }
.kr-tag--done { color: var(--ds-semantic-success); border-color: color-mix(in srgb, var(--ds-semantic-success) 38%, transparent); background: var(--ds-pill-success-bg); }
.kr-tag--rejected { color: var(--ds-semantic-neutral); border-color: var(--ds-hairline); background: color-mix(in srgb, var(--ds-semantic-neutral) 10%, transparent); }
.kr-tag--quiet { color: var(--ds-color-muted); }
.kr-tag--target { color: var(--ds-color-muted); border-color: var(--ds-hairline); max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kr-tag--demo { color: var(--ds-semantic-info); border-color: color-mix(in srgb, var(--ds-semantic-info) 32%, transparent); }

.kr-side__facts { display: grid; grid-template-columns: minmax(0, 1fr); gap: 6px; padding: 14px 18px; border-bottom: 1px solid var(--ds-hairline); font-size: 12px; }
.kr-side__facts > div { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 10px; align-items: baseline; }
.kr-side__facts dt { color: var(--ds-semantic-neutral); }
.kr-side__facts dd { margin: 0; color: var(--ds-color-text); font-family: var(--ds-font-mono); font-size: 11.5px; overflow-wrap: anywhere; }
.kr-side__facts code { font-family: var(--ds-font-mono); }
.kr-side__facts .kr-side__fact-text { font-family: var(--ds-font-cn); font-size: 11.5px; }

.kr-side__notice { margin: 12px 18px; padding: 10px 12px; border: 1px solid color-mix(in srgb, var(--ds-semantic-warning) 34%, transparent); border-radius: var(--ds-radius-md); background: color-mix(in srgb, var(--ds-semantic-warning) 7%, transparent); font-size: 11.5px; color: var(--ds-color-muted); line-height: 1.6; }
.kr-side__notice strong { display: block; color: var(--ds-semantic-warning); font-weight: 500; margin-bottom: 4px; }

.kr-side__graph { margin: 0 18px 12px; border: 1px solid var(--ds-color-border); border-radius: var(--ds-radius-md); overflow: hidden; background: var(--ds-surface-base); }
.kr-side__graph-label { margin: 0; padding: 8px 12px; border-bottom: 1px solid var(--ds-hairline); font: 11px/1 var(--ds-font-mono); letter-spacing: .12em; color: var(--ds-semantic-neutral); text-transform: uppercase; }
.kr-side__graph :deep(.kr-graph) { height: 200px; min-height: 0; }

.kr-side__doc { flex: 1; overflow: auto; padding: 6px 18px 24px; font-size: 12.5px; line-height: 1.7; color: var(--ds-color-muted); }
.kr-side__doc :deep(h1) { font-size: 15px; color: var(--ds-color-text); font-weight: 500; margin: 14px 0 8px; }
.kr-side__doc :deep(h2) { font-size: 13px; color: var(--ds-color-text); font-weight: 500; margin: 14px 0 6px; }
.kr-side__doc :deep(h3) { font-size: 12.5px; color: var(--ds-color-text); font-weight: 500; margin: 12px 0 6px; }
.kr-side__doc :deep(p) { margin: 0 0 10px; }
.kr-side__doc :deep(ul), .kr-side__doc :deep(ol) { margin: 6px 0; padding-left: 18px; }
.kr-side__doc :deep(li) { margin: 3px 0; }
.kr-side__doc :deep(blockquote) { margin: 8px 0; padding: 8px 10px; border-left: 2px solid var(--ds-color-border-strong); background: color-mix(in srgb, var(--ds-color-text) 8%, var(--ds-surface-base)); color: var(--ds-color-muted); }
.kr-side__doc :deep(code) { background: color-mix(in srgb, var(--ds-color-text) 8%, var(--ds-surface-base)); padding: 1px 5px; border-radius: var(--ds-radius-sm); color: var(--ds-color-text); font-family: var(--ds-font-mono); }
.kr-side__doc :deep(pre) { margin: 8px 0; padding: 10px; background: color-mix(in srgb, var(--ds-color-text) 8%, var(--ds-surface-base)); border-radius: var(--ds-radius-md); overflow: auto; font-size: 11px; line-height: 1.6; }
.kr-side__doc :deep(pre code) { background: none; padding: 0; }

.kr-side__foot { display: flex; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--ds-hairline); background: var(--ds-surface-base); }
.kr-side__foot .kr-btn { flex: 1; height: 32px; }

.kr-btn { display: inline-flex; align-items: center; justify-content: center; gap: 5px; height: 26px; padding: 0 10px; border-radius: var(--ds-radius-md); font-size: 12px; border: 1px solid var(--ds-color-border); color: var(--ds-color-text); background: none; cursor: pointer; transition: background var(--ds-duration-micro) var(--ds-ease-out); }
.kr-btn:hover:not(:disabled) { background: var(--ds-surface-base); border-color: var(--ds-color-border-strong); }
.kr-btn--primary { background: var(--ds-semantic-warning); border-color: transparent; color: var(--ds-surface-base); font-weight: 500; }
.kr-btn--primary:hover:not(:disabled) { background: color-mix(in srgb, var(--ds-semantic-warning) 82%, var(--ds-color-text)); }
.kr-btn:disabled { opacity: .45; cursor: not-allowed; }

/* 就地审核 popover：贴按钮定位（top/left 由脚本夹在视口内），窄屏不超宽。 */
.kr-pop-scrim { position: fixed; inset: 0; z-index: 69; }
.kr-pop { position: fixed; z-index: 70; width: 320px; max-width: calc(100vw - 24px); max-height: calc(100vh - 24px); overflow: auto; padding: 14px; border: 1px solid var(--ds-color-border); border-radius: var(--ds-radius-md); background: var(--ds-surface-raised); box-shadow: var(--ds-elevation-3); }
.kr-pop h4 { margin: 0 0 6px; font-size: 12.5px; font-weight: 500; color: var(--ds-color-text); }
.kr-pop__cand { margin: 0 0 10px; font-size: 12px; line-height: 1.45; color: var(--ds-color-muted); overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.kr-pop__field { display: grid; gap: 4px; margin-bottom: 8px; font-size: 11px; color: var(--ds-semantic-neutral); }
.kr-pop__field select,
.kr-pop__field input { width: 100%; height: 30px; padding: 0 8px; border-radius: var(--ds-radius-md); border: 1px solid var(--ds-color-border); background: var(--ds-surface-base); color: var(--ds-color-text); font: 12px var(--ds-font-cn); }
.kr-pop__field select:focus-visible,
.kr-pop__field input:focus-visible { outline: 2px solid var(--ds-color-primary); outline-offset: 1px; }
.kr-pop__hint { margin: 0 0 8px; font-size: 11px; line-height: 1.55; color: var(--ds-color-muted); }
.kr-pop__error { margin: 0 0 8px; font-size: 11px; line-height: 1.5; color: var(--ds-semantic-danger); }
.kr-pop__req { display: block; font: 10.5px/1.5 var(--ds-font-mono); color: var(--ds-semantic-neutral); overflow-wrap: anywhere; }
.kr-pop__acts { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }

/* toast */
.kr-toast { position: fixed; right: 18px; bottom: 18px; z-index: 80; max-width: 420px; padding: 10px 12px; border-radius: var(--ds-radius-md); border: 1px solid var(--ds-color-border); background: var(--ds-surface-raised); box-shadow: var(--ds-elevation-3); font-size: 12px; line-height: 1.55; color: var(--ds-color-text); opacity: 0; transform: translateY(6px); transition: opacity var(--ds-duration-spring) var(--ds-ease-out), transform var(--ds-duration-spring) var(--ds-ease-out); }
.kr-toast--on { opacity: 1; transform: none; }
.kr-toast__req { display: block; margin-top: 4px; font: 10.5px/1.5 var(--ds-font-mono); color: var(--ds-semantic-neutral); }

@media (max-width: 1439px) {
  .kr-page--side-open { grid-template-columns: minmax(0, 1fr); }
}

@media (max-width: 1279px) {
  .kr-side { position: fixed; right: 0; top: 0; bottom: 0; z-index: 40; max-height: none; width: 400px; border-radius: 0; box-shadow: var(--ds-elevation-3); }
}

@media (max-width: 767px) {
  .kr-side { width: 100%; }
  .kr-head { padding-top: 18px; }
  .kr-head h1 { font-size: 21px; }
}
</style>
