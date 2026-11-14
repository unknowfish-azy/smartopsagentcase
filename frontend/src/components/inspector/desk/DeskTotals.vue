<template>
  <section class="side-card">
    <div class="side-head">
      <h3>全量统计</h3>
      <span class="badge">全量</span>
    </div>
    <div v-if="!rows.length" class="muted">加载中…</div>
    <div v-else class="total-list">
      <div v-for="row in rows" :key="row.key" class="total-row">
        <b>{{ row.key }}</b>
        <span class="track"><span class="fill" :style="{ width: row.pct + '%' }"></span></span>
        <em>{{ row.value }}</em>
      </div>
    </div>
    <p class="note">来自 /api/inspector/statistics 的全量聚合，不受上方时间窗影响；窗口内的聚合请看「统计」视图。</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  stats: { type: Object, default: () => ({}) }
})

const rows = computed(() => {
  const byCategory = props.stats?.byCategory || props.stats?.categories || {}
  const entries = Object.entries(byCategory).filter(([, v]) => typeof v === 'number')
  if (!entries.length) return []
  const max = Math.max(...entries.map(([, v]) => v))
  return entries.map(([key, value]) => ({
    key, value, pct: Math.round((value / max) * 100)
  }))
})
</script>

<style scoped>
.side-card { background: #151A21; border: 1px solid #1E2630; border-radius: 12px; padding: 16px; }
.side-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.side-head h3 { margin: 0; font-size: 14px; }
.badge { font-size: 11px; color: #6B7D8C; border: 1px solid #1E2630; padding: 2px 8px; border-radius: 4px; }
.total-list { display: grid; gap: 8px; }
.total-row { display: grid; grid-template-columns: minmax(0,1fr) 92px 34px; align-items: center; gap: 8px; color: #92A6B5; font-size: 12px; }
.total-row b { color: #E8F2F7; font-weight: 400; }
.track { height: 3px; background: #1E2630; display: block; }
.fill { display: block; height: 100%; background: #2496ed; }
.total-row em { font-style: normal; text-align: right; color: #5d6b78; font: 11px Consolas, monospace; }
.note { margin: 10px 0 0; color: #5d6b78; font-size: 11px; line-height: 1.6; }
.muted { color: #6B7D8C; font-size: 12px; }
</style>
