<template>
  <div class="rg-menu-scrim" @click.self="$emit('close')" @contextmenu.prevent.self="$emit('close')">
    <div
      ref="menuRef"
      class="rg-menu"
      role="menu"
      aria-label="审核快捷菜单"
      :style="{ top: `${pos.top}px`, left: `${pos.left}px` }"
      @keydown.down.prevent="move(1)"
      @keydown.up.prevent="move(-1)"
      @keydown.esc.prevent.stop="$emit('close')"
    >
      <header class="rg-menu__head">
        <strong class="rg-menu__title">{{ title }}</strong>
        <span class="rg-menu__meta">目标条目 · {{ targetEntry }}</span>
        <span class="rg-menu__meta">状态 · {{ stateLabel }}</span>
      </header>

      <button
        v-for="item in items"
        :key="item.key"
        type="button"
        role="menuitem"
        class="rg-menu__item"
        :class="{ 'is-blocked': !item.enabled }"
        :disabled="!item.enabled"
        @click="run(item)"
      >
        <span class="rg-menu__label">{{ item.label }}</span>
        <!-- 可用项写明将执行的请求与写入目标；置灰项只写最根本的一个原因。 -->
        <span v-if="item.enabled" class="rg-menu__detail">{{ item.request }}</span>
        <span v-else class="rg-menu__detail rg-menu__detail--blocked">{{ item.reason }}</span>
      </button>

      <button type="button" class="rg-menu__cancel" @click="$emit('close')">关闭 · Esc</button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { STATUS_TEXT } from './useReviewGraph.js'

const props = defineProps({
  target: { type: Object, required: true },
  libraries: { type: Array, default: () => [] },
  guideMode: { type: Boolean, default: false },
  top: { type: Number, default: 0 },
  left: { type: Number, default: 0 }
})

const emit = defineEmits(['action', 'close'])

const menuRef = ref(null)
/* 锚点是鼠标/行的位置；真实高度要等渲染后才知道，所以挂载后再夹一次视口。 */
const pos = ref({ top: props.top, left: props.left })

const candidate = computed(() => props.target.candidate || null)
const targetEntry = computed(() => props.target.entry?.title || '待归类（source_ref 无对应条目）')
const title = computed(() => candidate.value?.title
  || props.target.entry?.title
  || (props.target.kind === 'commit' ? '审核事件' : '条目行'))
const stateLabel = computed(() => {
  if (candidate.value) return STATUS_TEXT[candidate.value.status] || '未知状态'
  if (props.target.entry) return `条目 v${props.target.entry.version}`
  return props.target.kind === 'commit' ? '审核事件' : '无候选'
})

function relativeTime(value) {
  if (!value) return '时间未知'
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return '时间未知'
  const diff = Date.now() - time
  const minute = 60000
  if (diff < minute) return '刚刚'
  if (diff < 60 * minute) return `${Math.floor(diff / minute)} 分钟前`
  if (diff < 24 * 60 * minute) return `${Math.floor(diff / (60 * minute))} 小时前`
  return `${Math.floor(diff / (24 * 60 * minute))} 天前`
}

/* 不可用原因按 DESIGN §7 的顺序检查，只写最根本的一条。 */
function pendingBlock(candidateStatus) {
  if (!candidate.value) return '该行不是候选'
  if (props.guideMode || candidate.value.isGuide) return '演示数据不写库（guideMode）'
  if (candidateStatus !== 'PENDING_REVIEW') {
    return candidateStatus === 'PROMOTED'
      ? `已采纳于 ${relativeTime(candidate.value.updatedAt || candidate.value.createdAt)}（目标条目：${targetEntry.value}）`
      : '已驳回，不能再次审核'
  }
  if (!props.libraries.length) return '还没有知识库，promote 必须带 libraryId'
  return ''
}

const items = computed(() => {
  const status = candidate.value?.status
  const adoptBlock = pendingBlock(status)
  const rejectBlock = candidate.value
    ? (props.guideMode || candidate.value.isGuide ? '演示数据不写库（guideMode）'
      : status !== 'PENDING_REVIEW' ? (status === 'PROMOTED' ? '已采纳，不能再次驳回' : '已驳回，不能重复驳回') : '')
    : '该行不是候选'
  const id = candidate.value?.id
  return [
    {
      key: 'adopt',
      label: '采纳并入库',
      enabled: !adoptBlock,
      request: `POST /api/knowledge/candidates/${id}/promote {libraryId, title, contentMarkdown} → 新建条目 v1（未验证）`,
      reason: adoptBlock
    },
    {
      key: 'merge',
      label: '并入已有条目',
      enabled: false,
      reason: '当前后端只支持新建条目，条目合并需要 target_entry_id'
    },
    {
      key: 'reject',
      label: '驳回并记录原因',
      enabled: !rejectBlock,
      request: `POST /api/knowledge/candidates/${id}/reject {reason} → 摘要追加驳回原因`,
      reason: rejectBlock
    },
    {
      key: 'regenerate',
      label: '按新证据重新生成',
      enabled: false,
      reason: candidate.value?.sourceRunId
        ? '同一来源运行只能有一个候选（UNIQUE(user_id, source_run_id)），覆盖需要后端支持'
        : '来源运行不存在'
    },
    {
      key: 'evidence',
      label: '查看证据正文',
      enabled: Boolean(candidate.value),
      request: '打开右侧栏（纯本地，不发请求）',
      reason: candidate.value ? '' : '该行没有候选正文'
    },
    {
      key: 'copy-trace',
      label: '复制 Trace ID',
      enabled: Boolean(candidate.value?.traceId),
      request: `写入剪贴板：${candidate.value?.traceId || ''}（无 API 请求）`,
      reason: '该行没有 Trace ID'
    },
    {
      key: 'discard',
      label: '丢弃候选',
      enabled: false,
      reason: '尚未实现；先驳回，再丢弃'
    }
  ]
})

function enabledButtons() {
  return [...(menuRef.value?.querySelectorAll('.rg-menu__item:not(:disabled)') || [])]
}

function move(delta) {
  const buttons = enabledButtons()
  if (!buttons.length) return
  const current = buttons.indexOf(document.activeElement)
  const next = current < 0 ? 0 : (current + delta + buttons.length) % buttons.length
  buttons[next].focus()
}

function run(item) {
  if (!item.enabled) return
  emit('action', item.key)
}

onMounted(() => {
  nextTick(() => {
    const el = menuRef.value
    if (el) {
      const pad = 12
      pos.value = {
        top: Math.max(pad, Math.min(props.top, window.innerHeight - el.offsetHeight - pad)),
        left: Math.max(pad, Math.min(props.left, window.innerWidth - el.offsetWidth - pad))
      }
    }
    enabledButtons()[0]?.focus()
  })
})
</script>
