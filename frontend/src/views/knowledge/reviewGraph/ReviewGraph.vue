<template>
  <div ref="rootRef" class="rg" :class="{ 'rg--compact': density === 'compact' }">
    <header class="rg-bar">
      <div class="rg-bar__scope">
        <span class="rg-overline">知识库</span>
        <strong class="rg-bar__name">{{ libraryName }}</strong>
      </div>

      <div class="rg-bar__counts" role="group" aria-label="按状态定位候选">
        <button type="button" class="rg-count rg-count--waiting" :disabled="!model.stats.pending" @click="jump('PENDING_REVIEW')">
          <span class="rg-dot"></span>{{ model.stats.pending }} 待审
        </button>
        <button type="button" class="rg-count" :disabled="!model.stats.promoted" @click="jump('PROMOTED')">
          <span class="rg-dot"></span>{{ model.stats.promoted }} 已采纳
        </button>
        <button type="button" class="rg-count" :disabled="!model.stats.rejected" @click="jump('REJECTED')">
          <span class="rg-dot"></span>{{ model.stats.rejected }} 已驳回
        </button>
      </div>

      <span v-if="guideMode" class="rg-chip">演示数据 · 不写库</span>
      <span class="rg-spacer"></span>

      <div class="rg-seg" role="group" aria-label="泳道着色方式">
        <button type="button" :aria-pressed="colorMode === 'tool'" @click="$emit('update:colorMode', 'tool')">按来源</button>
        <button type="button" :aria-pressed="colorMode === 'entry'" @click="$emit('update:colorMode', 'entry')">按条目</button>
      </div>

      <div class="rg-seg" role="group" aria-label="行密度">
        <button type="button" :aria-pressed="density === 'comfortable'" @click="$emit('update:density', 'comfortable')">舒适</button>
        <button type="button" :aria-pressed="density === 'compact'" @click="$emit('update:density', 'compact')">紧凑</button>
      </div>

      <div class="rg-zoom" role="group" aria-label="缩放" title="Ctrl/⌘ + 滚轮缩放，拖动空白处或行平移画布">
        <button type="button" class="rg-zoom__btn" aria-label="缩小" :disabled="zoom <= ZOOM_MIN" @click="zoomBy(-1)">−</button>
        <button type="button" class="rg-zoom__value" title="复位到 100%" @click="resetViewport">{{ zoomPercent(zoom) }}</button>
        <button type="button" class="rg-zoom__btn" aria-label="放大" :disabled="zoom >= ZOOM_MAX" @click="zoomBy(1)">+</button>
      </div>
    </header>

    <!-- 图例与筛选：状态编码、线条虚实、着色来源全部来自同一份行模型，不手抄颜色。 -->
    <section v-show="legendOpen" class="rg-legend" aria-label="图例与筛选">
      <div class="rg-legend__group" role="group" aria-label="按状态筛选">
        <span class="rg-legend__label">筛选</span>
        <button
          v-for="chip in statusChips"
          :key="chip.value"
          type="button"
          class="rg-filter"
          :aria-pressed="statusFilter === chip.value"
          @click="statusFilter = chip.value"
        >
          {{ chip.label }}<span class="rg-filter__count">{{ chip.count }}</span>
        </button>
      </div>

      <div class="rg-legend__group" aria-label="状态编码">
        <span class="rg-legend__label">状态</span>
        <span class="rg-legend__item">
          <span class="rg-legend__mark rg-legend__mark--waiting">!</span>{{ STATUS_TEXT.PENDING_REVIEW }}
        </span>
        <span class="rg-legend__item">
          <span class="rg-legend__mark rg-legend__mark--done">✓</span>{{ STATUS_TEXT.PROMOTED }}
        </span>
        <span class="rg-legend__item">
          <span class="rg-legend__mark rg-legend__mark--rejected">–</span>{{ STATUS_TEXT.REJECTED }}
        </span>
      </div>

      <div class="rg-legend__group" aria-label="线条虚实">
        <span class="rg-legend__label">线条</span>
        <span class="rg-legend__item"><svg class="rg-legend__line" width="22" height="8" aria-hidden="true"><path d="M0,4 L22,4" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 3" /></svg>待审段</span>
        <span class="rg-legend__item"><svg class="rg-legend__line" width="22" height="8" aria-hidden="true"><path d="M0,4 L22,4" stroke="currentColor" stroke-width="1.5" /></svg>已决策</span>
      </div>

      <div class="rg-legend__group" aria-label="着色来源">
        <span class="rg-legend__label">{{ colorMode === 'tool' ? '来源' : '条目' }}</span>
        <span v-for="swatch in swatches" :key="swatch.key" class="rg-legend__item" :title="swatch.name">
          <i class="rg-legend__swatch" :style="{ background: swatch.color }"></i>{{ swatch.name }}
        </span>
        <span v-if="hiddenSwatches" class="rg-legend__more">+{{ hiddenSwatches }}</span>
      </div>

      <span class="rg-legend__kbd">↑↓ 移动 · Enter 详情 · A 采纳 · R 驳回 · F 聚焦 · Esc 退出 · ? 图例 · Ctrl+滚轮 缩放 · 拖动平移</span>
    </section>

    <!-- 视口：缩放与平移只作用在这一层，图例与工具栏保持不动。 -->
    <div
      ref="viewportRef"
      class="rg-viewport"
      :class="{ 'is-panning': panning }"
      :style="{ height: `${stageHeight * zoom}px` }"
      @pointerdown="startPan"
      @wheel="onWheel"
    >
      <div
        ref="stageRef"
        class="rg-stage"
        :style="{ width: `${viewportWidth}px`, transform: `translate3d(${panX}px, 0, 0) scale(${zoom})` }"
      >
    <section class="rg-band" aria-label="待审区">
      <div class="rg-band__head">
        <span class="rg-overline">待审</span>
        <span class="rg-hint">同一泳道内：待审 → 已采纳 → 已驳回</span>
      </div>

      <div v-if="!model.nowRows.length" class="rg-empty">
        <p>当前没有候选。运行一次诊断并产出知识候选后，这里会出现对应泳道行。</p>
      </div>
      <div v-else class="rg-rows" role="list" :style="{ height: `${model.nowHeight}px` }">
        <ReviewLaneLayer
          :rows="model.nowRows"
          :lanes="model.lanes"
          :pad-left="model.padLeft"
          :height="model.nowHeight"
        />
        <ReviewGraphRow
          v-for="row in model.nowRows"
          :key="row.id"
          :row="row"
          :selected="row.candidate?.id === selectedId"
          :focused="focusedRowId === row.id"
          :dimmed="isDimmed(row)"
          :avatar-size="model.avatarSize"
          :pad-left="model.padLeft"
          @select="onSelect"
          @act="$emit('act', $event)"
          @menu="$emit('menu', $event)"
        />
      </div>

      <footer class="rg-band__foot">
        <span v-if="entryNote" class="rg-note">{{ entryNote }}</span>
        <span v-else class="rg-note">泳道按 entry.source_ref 与 candidate.trace_id 匹配；未匹配的候选固定落在最右「待归类」。</span>
        <template v-if="truncated">
          <span class="rg-note rg-note--strong">已加载 {{ model.stats.total }} / {{ total }} 条候选</span>
          <button type="button" class="rg-link" @click="$emit('load-more')">加载更早</button>
        </template>
      </footer>
    </section>

    <section class="rg-history" aria-label="演化史">
      <div class="rg-band__head">
        <span class="rg-overline">演化史</span>
        <span class="rg-hint">最近的审核事件，最新在上</span>
      </div>

      <div v-if="!model.histRows.length" class="rg-empty rg-empty--slim">
        <p>还没有采纳或驳回事件。</p>
      </div>
      <div v-else class="rg-rows" role="list" :style="{ height: `${model.histHeight}px` }">
        <ReviewLaneLayer
          :rows="model.histRows"
          :lanes="model.lanes"
          :pad-left="model.padLeft"
          :height="model.histHeight"
        />
        <ReviewGraphRow
          v-for="row in model.histRows"
          :key="row.id"
          :row="row"
          :selected="row.event?.candidate?.id === selectedId"
          :dimmed="isDimmed(row)"
          :avatar-size="model.avatarSize"
          :pad-left="model.padLeft"
          @select="onSelect"
          @act="$emit('act', $event)"
          @menu="$emit('menu', $event)"
        />
      </div>

      <footer class="rg-band__foot">
        <span v-if="model.historyTruncated" class="rg-note">仅显示最近 40 条审核事件。</span>
        <span v-else class="rg-note">采纳时刻取条目创建时间；驳回没有事件时间字段，标为「候选生成于」。</span>
      </footer>
    </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ReviewGraphRow from './ReviewGraphRow.vue'
import ReviewLaneLayer from './ReviewLaneLayer.vue'
import { STATUS_TEXT } from './useReviewGraph.js'
import { ZOOM_MAX, ZOOM_MIN, clampPan, zoomAt, zoomPercent, stepZoom } from './useGraphViewport.js'
import './reviewGraph.css'

const props = defineProps({
  model: { type: Object, required: true },
  libraryName: { type: String, default: '未建知识库' },
  selectedId: { type: [Number, String], default: null },
  colorMode: { type: String, default: 'tool' },
  density: { type: String, default: 'comfortable' },
  guideMode: { type: Boolean, default: false },
  entryNote: { type: String, default: '' },
  truncated: { type: Boolean, default: false },
  total: { type: Number, default: 0 }
})

const emit = defineEmits(['select', 'act', 'menu', 'update:colorMode', 'update:density', 'load-more'])

const rootRef = ref(null)

/* 视口：缩放用 transform，平移只动横向；纵向拖动转成页面滚动，避免把长列表裁进一个固定盒子里。 */
const viewportRef = ref(null)
const stageRef = ref(null)
const viewportWidth = ref(0)
const stageHeight = ref(0)
const zoom = ref(1)
const panX = ref(0)
const panning = ref(false)
let stageObserver = null
let drag = null
let suppressClick = false

function measure() {
  if (viewportRef.value) viewportWidth.value = viewportRef.value.clientWidth
  if (stageRef.value) stageHeight.value = stageRef.value.offsetHeight
}

onMounted(() => {
  measure()
  if (typeof ResizeObserver === 'undefined') return
  stageObserver = new ResizeObserver(() => measure())
  if (stageRef.value) stageObserver.observe(stageRef.value)
  if (viewportRef.value) stageObserver.observe(viewportRef.value)
})

onBeforeUnmount(() => {
  stageObserver?.disconnect()
  drag?.onUp?.()
})

function applyZoom(nextZoom, pointerX) {
  const width = viewportRef.value?.clientWidth ?? viewportWidth.value
  const result = zoomAt({ zoom: zoom.value, panX: panX.value, viewportWidth: width, pointerX, nextZoom })
  zoom.value = result.zoom
  panX.value = result.panX
}

/* 按钮缩放以视口左缘为锚点：泳道与标题都在左侧，放大后不应该先被裁掉；滚轮缩放仍以指针为锚点。 */
function zoomBy(direction) {
  applyZoom(stepZoom(zoom.value, direction), 0)
}

function resetViewport() {
  zoom.value = 1
  panX.value = 0
}

function onWheel(event) {
  if (!event.ctrlKey && !event.metaKey) return
  event.preventDefault()
  const rect = viewportRef.value?.getBoundingClientRect()
  applyZoom(zoom.value * Math.exp(-event.deltaY * 0.002), event.clientX - (rect?.left ?? 0))
}

/* 拖动平移：位移超过 4px 才算拖动，否则保留点击选中；松手后紧跟的 click 被吞掉。 */
function startPan(event) {
  if (event.button !== 0 || event.isPrimary === false) return
  if (event.target.closest('button, a, input, select, textarea')) return
  const startX = event.clientX
  const startY = event.clientY
  const startPanX = panX.value
  const startScroll = window.scrollY
  let moved = false

  const onMove = moveEvent => {
    const dx = moveEvent.clientX - startX
    const dy = moveEvent.clientY - startY
    if (!moved && Math.hypot(dx, dy) < 4) return
    moved = true
    panning.value = true
    const width = viewportRef.value?.clientWidth ?? viewportWidth.value
    panX.value = clampPan(startPanX + dx, width, zoom.value)
    if (dy) window.scrollTo(0, startScroll - dy)
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    window.removeEventListener('pointercancel', onUp)
    if (moved) {
      suppressClick = true
      setTimeout(() => { suppressClick = false }, 0)
    }
    panning.value = false
    drag = null
  }

  drag = { onUp }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onUp)
}

function onSelect(id) {
  if (suppressClick) return
  emit('select', id)
}

/* 筛选只让不匹配的行变淡，不隐藏也不留空行——行高与泳道仍是同一份模型。 */
const statusFilter = ref('ALL')
const legendOpen = ref(true)

/* 键盘焦点只在上段可操作行（候选 / 条目）之间移动，子行与历史行不参与。 */
const focusIndex = ref(-1)
const focusLane = ref(null)
const navRows = computed(() => props.model.nowRows.filter(row => row.kind === 'cand' || row.kind === 'entry'))
const focusedRowId = computed(() => (focusIndex.value >= 0 ? navRows.value[focusIndex.value]?.id ?? null : null))

const statusChips = computed(() => [
  { value: 'ALL', label: '全部', count: props.model.stats.total },
  { value: 'PENDING_REVIEW', label: STATUS_TEXT.PENDING_REVIEW, count: props.model.stats.pending },
  { value: 'PROMOTED', label: STATUS_TEXT.PROMOTED, count: props.model.stats.promoted },
  { value: 'REJECTED', label: STATUS_TEXT.REJECTED, count: props.model.stats.rejected }
])

const allSwatches = computed(() => {
  if (props.colorMode === 'entry') {
    return props.model.lanes.map(lane => ({ key: lane.key, name: lane.name, color: lane.color }))
  }
  return [...props.model.toolColors.entries()].map(([toolId, color]) => ({ key: toolId, name: toolId, color }))
})

const swatches = computed(() => allSwatches.value.slice(0, 6))
const hiddenSwatches = computed(() => Math.max(0, allSwatches.value.length - swatches.value.length))

/* 历史区用事件种类对应状态；待审在演化史里没有事件，所以整体变淡是如实表达。 */
function isDimmed(row) {
  if (focusLane.value != null && row.lane !== focusLane.value) return true
  if (statusFilter.value === 'ALL') return false
  if (row.kind === 'cand') return row.candidate?.status !== statusFilter.value
  if (row.kind === 'commit') {
    const wanted = statusFilter.value === 'PROMOTED'
      ? 'adopt'
      : statusFilter.value === 'REJECTED' ? 'reject' : null
    return wanted ? row.event?.kind !== wanted : true
  }
  return false
}

async function jump(status) {
  const row = props.model.nowRows.find(
    item => item.kind === 'cand' && item.candidate?.status === status
  )
  if (!row) return
  emit('select', row.candidate.id)
  focusIndex.value = navRows.value.findIndex(item => item.id === row.id)
  await nextTick()
  rootRef.value
    ?.querySelector(`[data-row-id="${row.id}"]`)
    ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

/* ---------- 键盘导航（阶段 4）：状态在这里，事件由视图统一分发 ---------- */

function reveal(row) {
  nextTick(() => rootRef.value
    ?.querySelector(`[data-row-id="${row.id}"]`)
    ?.scrollIntoView({ block: 'nearest' }))
}

function moveFocus(delta) {
  const rows = navRows.value
  if (!rows.length) return null
  const next = focusIndex.value < 0
    ? (delta >= 0 ? 0 : rows.length - 1)
    : Math.max(0, Math.min(rows.length - 1, focusIndex.value + delta))
  focusIndex.value = next
  reveal(rows[next])
  return rows[next]
}

function focusedRow() {
  return focusIndex.value >= 0 ? navRows.value[focusIndex.value] ?? null : null
}

/* 给 popover 当锚点：键盘触发没有鼠标坐标，就用行的右侧。 */
function focusTarget() {
  return rootRef.value?.querySelector(`[data-row-id="${focusedRow()?.id}"]`) ?? null
}

/* F：聚焦当前行所属的条目链，其余泳道变淡；同一行再按一次取消。 */
function focusChain() {
  const row = focusedRow()
  if (!row) return false
  focusLane.value = focusLane.value === row.lane ? null : row.lane
  return true
}

function clearFocus() {
  if (focusIndex.value < 0 && focusLane.value == null) return false
  focusIndex.value = -1
  focusLane.value = null
  return true
}

function clearFilter() {
  if (statusFilter.value === 'ALL') return false
  statusFilter.value = 'ALL'
  return true
}

function toggleLegend() {
  legendOpen.value = !legendOpen.value
}

defineExpose({ moveFocus, focusedRow, focusTarget, focusChain, clearFocus, clearFilter, toggleLegend })
</script>
