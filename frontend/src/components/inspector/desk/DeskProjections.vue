<template>
  <section class="side-card">
    <div class="side-head">
      <h3>在另外两个视图里</h3>
      <span class="muted" v-if="selected">{{ currentIndex }} / 3</span>
    </div>
    <p class="muted" v-if="!selected">选中对象后，这里显示它在另外两个视图里落在哪，以及「有没有对应物」。</p>
    <div v-else class="proj-list">
      <div
        v-for="proj in projections"
        :key="proj.view"
        class="projection"
        :class="{ 'is-on': proj.isCurrent, 'is-linked': proj.hasMatch }"
      >
        <b>{{ proj.label }}</b>
        <span>{{ proj.text }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  selected: { type: Object, default: null },
  link: { type: Object, default: null },
  view: { type: String, default: 'events' },
  statsBin: { type: Object, default: null }
})

const VIEWS = [
  { key: 'events', label: '纠察' },
  { key: 'stats', label: '统计' },
  { key: 'runs', label: '运行' }
]

const currentIndex = computed(() => VIEWS.findIndex(v => v.key === props.view) + 1)

const projections = computed(() => {
  if (!props.selected) return []
  const isEvent = props.selected.__type === 'event'
  return VIEWS.map(v => {
    const isCurrent = v.key === props.view
    let text = '—'
    let hasMatch = false
    if (v.key === 'events') {
      if (isEvent) { text = `${props.selected.id} · ${props.selected.taskId}`; hasMatch = true }
      else if (props.link?.kind === 'linked') { text = `${props.link.event.id} · ${props.link.event.taskId}`; hasMatch = true }
      else { text = '没有对应事件（未关联 traceId）' }
    } else if (v.key === 'stats') {
      if (props.statsBin) {
        const total = props.statsBin.CRITICAL + props.statsBin.HIGH + props.statsBin.WARN + props.statsBin.PASS
        text = `这一箱：${total} 条`
        hasMatch = true
      } else {
        text = '未落入统计分箱'
      }
    } else if (v.key === 'runs') {
      if (!isEvent) { text = `${props.selected.id} · ${props.selected.tool}`; hasMatch = true }
      else if (props.link?.kind === 'linked') { text = `${props.link.run.id} · ${props.link.run.tool}`; hasMatch = true }
      else { text = '没有对应命令（未关联 traceId）' }
    }
    return { view: v.key, label: v.label, isCurrent, text, hasMatch }
  })
})
</script>

<style scoped>
.side-card { background: var(--ds-surface-raised); border: 1px solid var(--ds-surface-overlay); border-radius: 12px; padding: 16px; }
.side-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.side-head h3 { margin: 0; font-size: 14px; }
.muted { color: var(--smart-muted); font-size: 12px; }
.proj-list { display: grid; gap: 8px; }
.projection { display: grid; gap: 3px; padding: 10px; border: 1px solid var(--ds-surface-overlay); border-radius: 6px; color: var(--smart-muted); font-size: 12px; }
.projection b { color: var(--smart-text); font-size: 12px; letter-spacing: .04em; }
.projection.is-on { border-color: color-mix(in srgb, var(--smart-primary) 45%, transparent); background: color-mix(in srgb, var(--smart-primary) 7%, transparent); }
.projection.is-linked { color: var(--smart-text); }
</style>
