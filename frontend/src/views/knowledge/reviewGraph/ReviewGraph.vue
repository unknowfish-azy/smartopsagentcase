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
    </header>

    <!-- 图例与筛选：状态编码、线条虚实、着色来源全部来自同一份行模型，不手抄颜色。 -->
    <section class="rg-legend" aria-label="图例与筛选">
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
    </section>

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
          :dimmed="isDimmed(row)"
          :avatar-size="model.avatarSize"
          :pad-left="model.padLeft"
          @select="$emit('select', $event)"
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
          @select="$emit('select', $event)"
        />
      </div>

      <footer class="rg-band__foot">
        <span v-if="model.historyTruncated" class="rg-note">仅显示最近 40 条审核事件。</span>
        <span v-else class="rg-note">采纳时刻取条目创建时间；驳回没有事件时间字段，标为「候选生成于」。</span>
      </footer>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import ReviewGraphRow from './ReviewGraphRow.vue'
import ReviewLaneLayer from './ReviewLaneLayer.vue'
import { STATUS_TEXT } from './useReviewGraph.js'
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

const emit = defineEmits(['select', 'update:colorMode', 'update:density', 'load-more'])

const rootRef = ref(null)

/* 筛选只让不匹配的行变淡，不隐藏也不留空行——行高与泳道仍是同一份模型。 */
const statusFilter = ref('ALL')

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
  await nextTick()
  rootRef.value
    ?.querySelector(`[data-row-id="${row.id}"]`)
    ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}
</script>
