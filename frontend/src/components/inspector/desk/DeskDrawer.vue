<template>
  <section class="drawer" :class="{ 'is-open': open }" aria-expanded="open">
    <div class="drawer-head">
      <strong>证据抽屉</strong>
      <span class="drawer-id muted" v-if="!selected">未选择</span>
      <span class="drawer-id" v-else>{{ selected.id }}</span>
      <nav class="drawer-tabs" role="tablist">
        <button role="tab" :aria-selected="tab === 'evidence'" @click="$emit('tab', 'evidence')">证据</button>
        <button role="tab" :aria-selected="tab === 'output'" @click="$emit('tab', 'output')">输出</button>
        <button role="tab" :aria-selected="tab === 'trace'" @click="$emit('tab', 'trace')">轨迹</button>
      </nav>
      <span class="drawer-hint muted">{{ open ? '按 Esc 关闭' : '点击图上任意标记 / 按 Enter 打开' }}</span>
      <button class="drawer-toggle" @click="$emit('toggle')">{{ open ? '收起' : '展开' }}</button>
    </div>
    <div v-if="open" class="drawer-body">
      <template v-if="!selected">
        <p class="muted">未选择对象。</p>
      </template>
      <template v-else-if="tab === 'evidence'">
        <div class="evidence">
          <div><b>类型</b><span>{{ typeLabel }}</span></div>
          <div><b>时间</b><span>{{ fmtDateTime(selected.at) }}</span></div>
          <template v-if="isEvent">
            <div><b>等级</b><span>{{ severityMeta(selected.severity).cn }}（{{ selected.severity }}）</span></div>
            <div><b>任务</b><span>{{ selected.taskId }}</span></div>
            <div v-if="selected.category"><b>类别</b><span>{{ selected.category }}</span></div>
            <div v-if="selected.target"><b>目标</b><span>{{ selected.target }}</span></div>
          </template>
          <template v-else>
            <div><b>工具</b><span>{{ toolMeta(selected.tool).cn }}（{{ selected.tool }}）</span></div>
            <div><b>结果</b><span>{{ selected.status }}</span></div>
            <div><b>时长</b><span>{{ Number(selected.duration).toFixed(1) }}s</span></div>
            <div v-if="selected.exitCode != null"><b>退出码</b><span>{{ selected.exitCode }}</span></div>
          </template>
          <div><b>traceId</b><span>{{ selected.traceId || '—（未关联，不做猜测）' }}</span></div>
        </div>
        <pre>{{ jsonPretty(selected) }}</pre>
      </template>
      <template v-else-if="tab === 'output'">
        <pre v-if="outputText">{{ outputText }}</pre>
        <p v-else class="muted">该对象暂无输出样例。</p>
      </template>
      <template v-else>
        <pre v-if="traceText">{{ traceText }}</pre>
        <p v-else class="muted">该对象暂无 trace 骨架。</p>
      </template>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { fmtDateTime, severityMeta, toolMeta } from './deskModel'

const props = defineProps({
  open: { type: Boolean, default: false },
  tab: { type: String, default: 'evidence' },
  selected: { type: Object, default: null }
})
defineEmits(['toggle', 'tab'])

const isEvent = computed(() => props.selected?.__type === 'event')
const typeLabel = computed(() => (isEvent.value ? '纠察事件' : '命令执行'))

const outputText = computed(() => {
  if (!props.selected) return ''
  if (isEvent.value) return '# 纠察事件无 stdout；证据见「证据」tab。'
  const s = props.selected.status
  if (s === 'SUCCESS') return `$ ${props.selected.tool}\n[ok] 执行完成，exit 0\n`
  if (s === 'FAILED') return `$ ${props.selected.tool}\n[error] 执行失败，exit ${props.selected.exitCode ?? 1}\n`
  return `$ ${props.selected.tool}\n[timeout] 执行超时\n`
})

const traceText = computed(() => {
  if (!props.selected) return ''
  const traceId = props.selected.traceId
  if (!traceId) return '# 该对象没有 traceId，无法生成轨迹骨架。'
  return `traceId: ${traceId}\n└─ ${isEvent.value ? 'event' : 'run'}: ${props.selected.id}\n   └─ time: ${fmtDateTime(props.selected.at)}\n`
})

function jsonPretty(obj) {
  const clean = { ...obj }
  delete clean.__type
  return JSON.stringify(clean, null, 2)
}
</script>

<style scoped>
.drawer { background: var(--ds-surface-raised); border: 1px solid var(--ds-surface-overlay); border-radius: 12px; padding: 12px 16px; }
.drawer-head { display: flex; gap: 16px; align-items: center; }
.drawer-id { color: var(--smart-text); font: 12px Consolas, monospace; }
.drawer-tabs { display: flex; gap: 2px; margin-left: auto; }
.drawer-tabs button { background: transparent; border: 0; color: var(--smart-muted); padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
.drawer-tabs button[aria-selected="true"] { background: var(--ds-surface-overlay); color: var(--smart-text); }
.drawer-hint { color: var(--smart-muted); font-size: 12px; }
.drawer-toggle { background: var(--ds-surface-overlay); border: 0; color: var(--smart-text); padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.drawer-body { padding-top: 12px; }
.evidence { display: grid; gap: 6px; margin-bottom: 10px; }
.evidence div { display: flex; gap: 10px; padding: 7px 9px; border-left: 2px solid var(--ds-surface-overlay); background: color-mix(in srgb, var(--smart-surface) 2%, transparent); color: var(--smart-muted); font-size: 12px; }
.evidence div b { color: var(--smart-text); font: 11px Consolas, monospace; min-width: 74px; }
.drawer-body pre { margin: 0; padding: 12px; border: 1px solid var(--ds-surface-overlay); border-radius: 4px; background: var(--smart-bg); color: var(--smart-text); font: 11px/1.7 Consolas, monospace; overflow: auto; max-height: 240px; }
.muted { color: var(--smart-muted); font-size: 12px; }
</style>
