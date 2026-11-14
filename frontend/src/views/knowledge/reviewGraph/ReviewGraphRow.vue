<template>
  <div
    class="rg-row"
    :class="[
      `rg-row--${row.kind}`,
      row.kind === 'cand' && `rg-row--${statusClass}`,
      { 'is-selected': selected, 'is-focused': focused, 'is-unassigned': row.unassigned, 'is-dimmed': dimmed }
    ]"
    :style="rowStyle"
    :data-row-id="row.id"
    :role="row.kind === 'gap' ? 'presentation' : 'listitem'"
    :tabindex="interactive ? 0 : -1"
    :aria-selected="interactive ? selected : undefined"
    @click="emitSelect"
    @keydown.enter.prevent="emitSelect"
    @keydown.space.prevent="emitSelect"
    @contextmenu.prevent="emitMenu"
    @keydown.shift.f10.prevent.stop="emitMenu"
  >
    <template v-if="row.kind === 'gap'">
      <span class="rg-gap" aria-hidden="true"></span>
    </template>

    <template v-else-if="row.kind === 'entry'">
      <span class="rg-entry-name" :title="entryTitle">{{ entryTitle }}</span>
      <span v-if="row.entry" class="rg-tag rg-tag--version">v{{ row.entry.version }}</span>
      <span v-if="row.entry?.isGuide" class="rg-tag rg-tag--quiet">演示条目</span>
      <span v-if="row.unassigned" class="rg-tag rg-tag--quiet">尚未关联知识条目</span>
      <span v-else-if="row.pending" class="rg-tag rg-tag--pending">{{ row.pending }} 条待审</span>
      <span v-else class="rg-tag rg-tag--quiet">无待审</span>
      <span class="rg-spacer"></span>
      <span class="rg-meta">{{ row.total }} 条候选</span>
    </template>

    <template v-else-if="row.kind === 'cand'">
      <span class="rg-avatar" :class="`rg-avatar--${statusClass}`" :style="avatarStyle" aria-hidden="true">
        <span class="rg-avatar__initials">{{ initials }}</span>
        <span class="rg-avatar__badge">{{ badge }}</span>
      </span>
      <span class="rg-cand">
        <span class="rg-cand__line">
          <span class="rg-tool">{{ row.candidate.toolId }}</span>
          <span class="rg-tag" :class="statusTagClass">{{ statusLabel }}</span>
          <span class="rg-cand__title" :title="row.candidate.title">{{ row.candidate.title }}</span>
          <span class="rg-meta">{{ age }}</span>
        </span>
        <span class="rg-cand__line rg-cand__line--sub">
          <span class="rg-cand__note" :title="secondLine">{{ secondLine }}</span>
          <span class="rg-tag rg-tag--target" v-if="!row.entry">待归类</span>
          <!-- 待审行就地操作：不进侧栏也能采纳/驳回，DESIGN §6.1 -->
          <span v-if="actionable" class="rg-cand__acts">
            <button type="button" class="rg-act rg-act--primary" @click.stop="emitAct('adopt', $event)" @keydown.stop>采纳</button>
            <button type="button" class="rg-act" @click.stop="emitAct('reject', $event)" @keydown.stop>驳回</button>
          </span>
        </span>
      </span>
    </template>

    <template v-else-if="row.kind === 'commit'">
      <span class="rg-commit">
        <span class="rg-commit__kind" :class="`rg-commit__kind--${row.event.kind}`">{{ commitKindLabel }}</span>
        <span class="rg-commit__title">{{ commitTitle }}</span>
        <span class="rg-spacer"></span>
        <span class="rg-meta">{{ commitTime }}</span>
      </span>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { laneCenter, rejectReasonOf, STATUS_TEXT } from './useReviewGraph.js'

const props = defineProps({
  row: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  focused: { type: Boolean, default: false },
  dimmed: { type: Boolean, default: false },
  padLeft: { type: Number, default: 0 },
  avatarSize: { type: Number, default: 28 }
})

const emit = defineEmits(['select', 'act', 'menu'])

/* 右键与 Shift+F10 都落到同一行；键盘触发时没有鼠标坐标，就用行的右上角。 */
function emitMenu(event) {
  const rect = event?.currentTarget?.getBoundingClientRect?.()
  const x = event?.clientX > 0 ? event.clientX : (rect ? rect.right - 24 : 0)
  const y = event?.clientY > 0 ? event.clientY : (rect ? rect.top : 0)
  emit('menu', { row: props.row, x, y })
}

const interactive = computed(() => props.row.kind === 'cand' || props.row.kind === 'commit')

/* 只有真待审、且不是演示数据时才给就地动作，避免对已决策行承诺可写。 */
const actionable = computed(() => props.row.kind === 'cand'
  && props.row.candidate?.status === 'PENDING_REVIEW'
  && !props.row.candidate?.isGuide)

function emitAct(type, event) {
  emit('act', { type, candidate: props.row.candidate, anchor: event?.currentTarget ?? null })
}

const rowStyle = computed(() => ({
  height: `${props.row.h}px`,
  '--rg-pad-left': `${props.padLeft}px`
}))

const entryTitle = computed(() => (props.row.unassigned ? '待归类' : props.row.entry?.title || '未命名条目'))

const statusClass = computed(() => {
  const status = props.row.candidate?.status
  if (status === 'PENDING_REVIEW') return 'waiting'
  if (status === 'PROMOTED') return 'done'
  if (status === 'REJECTED') return 'rejected'
  return 'unknown'
})

const statusLabel = computed(() => {
  const candidate = props.row.candidate
  if (!candidate) return ''
  /* 演示数据也要写清真实状态，前缀「演示」表示不写库。 */
  const status = STATUS_TEXT[candidate.status] || '未知状态'
  return candidate.isGuide ? `演示 · ${status}` : status
})

const statusTagClass = computed(() => {
  if (props.row.candidate?.isGuide) return 'rg-tag--quiet'
  if (statusClass.value === 'waiting') return 'rg-tag--pending'
  if (statusClass.value === 'done') return 'rg-tag--done'
  if (statusClass.value === 'rejected') return 'rg-tag--rejected'
  return 'rg-tag--quiet'
})

const badge = computed(() => {
  if (statusClass.value === 'waiting') return '!'
  if (statusClass.value === 'done') return '✓'
  if (statusClass.value === 'rejected') return '–'
  return '·'
})

const initials = computed(() => {
  const toolId = props.row.candidate?.toolId || ''
  const head = toolId.split(/[.\-_/]/).filter(Boolean)[0] || toolId || '?'
  return head.slice(0, 2).toUpperCase()
})

/* 头像中心必须压在泳道线的 x 上：左边 = 泳道中心 - 半径，尺寸随密度切换。 */
const avatarStyle = computed(() => ({
  left: `${laneCenter(props.row.lane) - props.avatarSize / 2}px`,
  width: `${props.avatarSize}px`,
  height: `${props.avatarSize}px`,
  marginTop: `${-props.avatarSize / 2}px`
}))

const secondLine = computed(() => {
  const candidate = props.row.candidate
  if (!candidate) return ''
  /* 演示数据不写库，所以不能写成「已新建条目」。 */
  if (candidate.isGuide) {
    return candidate.status === 'PROMOTED' ? '演示数据：已采纳示意，未写库' : '演示数据：仅供界面引导，不写库'
  }
  if (candidate.status === 'PENDING_REVIEW') return '采纳后在所选知识库新建条目 v1（未验证）'
  if (candidate.status === 'PROMOTED') {
    const entry = props.row.entry
    if (!entry) return '已采纳，未匹配到知识条目（source_ref 无对应记录）'
    const verified = entry.verificationStatus === 'VERIFIED' ? '已验证' : '未验证'
    return `已新建条目 v${entry.version}（${verified}）`
  }
  if (candidate.status === 'REJECTED') {
    const reason = rejectReasonOf(candidate.summary)
    return reason ? `驳回：${reason}` : '已驳回，后端未记录原因'
  }
  return candidate.summary || '未识别的候选状态'
})

const age = computed(() => relativeTime(props.row.candidate?.createdAt))

const commitKindLabel = computed(() => (props.row.event?.kind === 'adopt' ? '采纳' : '驳回'))

const commitTitle = computed(() => {
  const event = props.row.event
  if (!event) return ''
  if (event.kind === 'adopt') {
    const version = event.entry?.version ? `v${event.entry.version}` : 'v1'
    if (event.candidate?.isGuide) return `演示 · 采纳后条目 ${version}（未写库） · ${event.entry?.title || ''}`
    return `新建条目 ${version} · ${event.entry?.title || event.candidate?.title || ''}`
  }
  const reason = rejectReasonOf(event.candidate?.summary)
  return reason ? `${event.candidate?.title || ''} · ${reason}` : event.candidate?.title || ''
})

/* 采纳事件时间取 entry.createdAt（入库时刻）；驳回没有事件时间字段，退回候选创建时间并注明。 */
const commitTime = computed(() => {
  const event = props.row.event
  if (!event) return ''
  if (event.kind === 'adopt') return relativeTime(event.at)
  return `候选生成于 ${relativeTime(event.candidateCreatedAt)}`
})

function relativeTime(value) {
  if (!value) return '—'
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return '—'
  const diff = Date.now() - time
  if (diff < 0) return '刚刚'
  const minute = 60 * 1000
  if (diff < minute) return '刚刚'
  if (diff < 60 * minute) return `${Math.floor(diff / minute)} 分钟前`
  if (diff < 24 * 60 * minute) return `${Math.floor(diff / (60 * minute))} 小时前`
  if (diff < 30 * 24 * 60 * minute) return `${Math.floor(diff / (24 * 60 * minute))} 天前`
  return new Date(time).toLocaleDateString('zh-CN')
}

function emitSelect() {
  if (!interactive.value) return
  const id = props.row.candidate?.id
  if (id != null) emit('select', id)
}
</script>
