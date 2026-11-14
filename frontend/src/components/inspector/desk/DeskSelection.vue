<template>
  <section class="side-card">
    <div class="side-head">
      <h3>选中对象</h3>
      <span v-if="selected" class="kind" :class="kindClass">{{ kindLabel }}</span>
    </div>
    <p class="muted" v-if="!selected">在上方任意视图点一个标记，或发 ←/→ 逐个走。切视图不丢选中。</p>
    <template v-else>
      <p class="sel-meta">{{ typeLabel }} · {{ fmtDateTime(selected.at) }}</p>
      <h4 class="sel-title">{{ selected.id }}</h4>
      <p class="sel-sub" v-if="isEvent">{{ selected.taskId }}<span v-if="selected.category"> · {{ selected.category }}</span></p>
      <p class="sel-sub" v-else>{{ toolMeta(selected.tool).cn }} · {{ selected.status }}</p>
      <dl class="sel-dl">
        <template v-if="isEvent">
          <dt>traceId</dt><dd>{{ selected.traceId || '—' }}</dd>
          <dt>运行</dt><dd>{{ linkedRunLabel }}</dd>
        </template>
        <template v-else>
          <dt>traceId</dt><dd>{{ selected.traceId || '—' }}</dd>
          <dt>时长</dt><dd>{{ Number(selected.duration).toFixed(1) }}s</dd>
          <dt>退出码</dt><dd>{{ selected.exitCode == null ? '—' : selected.exitCode }}</dd>
        </template>
      </dl>
      <p class="link-row" :class="{ 'is-off': link.kind !== 'linked' }">
        <b v-if="isEvent">{{ linkText(link) }}</b>
        <b v-else>{{ linkTextRun(link) }}</b>
      </p>
    </template>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { fmtDateTime, linkText, linkTextRun, toolMeta } from './deskModel'

const props = defineProps({
  selected: { type: Object, default: null },
  link: { type: Object, default: null }
})

const isEvent = computed(() => props.selected?.__type === 'event')
const kindLabel = computed(() => (isEvent.value ? 'EVENT' : 'RUN'))
const kindClass = computed(() => {
  if (!props.selected) return ''
  if (isEvent.value) {
    const sev = props.selected.severity
    if (sev === 'CRITICAL') return 'kind--bad'
    if (sev === 'HIGH') return 'kind--warn'
    return ''
  }
  return props.selected.status === 'FAILED' ? 'kind--bad' : ''
})
const typeLabel = computed(() => (isEvent.value ? '纠察事件' : '命令执行'))
const linkedRunLabel = computed(() => {
  if (props.link?.kind === 'linked') return props.link.run.id
  return '未找到对应命令'
})
</script>

<style scoped>
.side-card { background: #151A21; border: 1px solid #1E2630; border-radius: 12px; padding: 16px; }
.side-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.side-head h3 { margin: 0; font-size: 14px; }
.kind { font-size: 11px; color: #6B7D8C; border: 1px solid #1E2630; padding: 2px 8px; border-radius: 4px; letter-spacing: .08em; }
.kind--warn { border-color: rgba(210,153,34,.45); color: #d29922; }
.kind--bad { border-color: rgba(248,81,73,.45); color: #f85149; }
.muted { color: #6B7D8C; font-size: 12px; line-height: 1.6; margin: 0; }
.sel-meta { color: #6B7D8C; font-size: 11px; margin: 4px 0 0; }
.sel-title { margin: 4px 0; font-size: 16px; font-weight: 600; }
.sel-sub { color: #92A6B5; font-size: 12px; margin: 0 0 10px; }
.sel-dl { display: grid; grid-template-columns: 64px minmax(0,1fr); gap: 5px 8px; margin: 12px 0 0; font: 11px Consolas, monospace; }
.sel-dl dt { color: #5d6b78; }
.sel-dl dd { margin: 0; color: #E8F2F7; overflow-wrap: anywhere; }
.link-row { display: flex; align-items: center; gap: 7px; margin-top: 12px; padding-top: 10px; border-top: 1px solid #1E2630; color: #92A6B5; font-size: 11px; }
.link-row b { font-weight: 500; }
.link-row.is-off { color: #d29922; }
</style>
