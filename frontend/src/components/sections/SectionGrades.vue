<template>
  <div class="grades-host">
    <div v-for="row in rows" :key="row.key" class="grade-row">
      <span class="grade-name">
        <b>{{ row.en }}</b>
        <small>{{ row.cn }}</small>
      </span>
      <span class="grade-band" role="img" :aria-label="`${row.en} 分级评价：${gradeLabel(row.grade)}`">
        <i v-for="seg in SEGMENTS" :key="seg.key" class="grade-seg" :class="[`grade-seg--${seg.key}`, { 'grade-seg--lit': ORDER[seg.key] <= (ORDER[row.grade] ?? 0) }]"></i>
        <span class="grade-cursor" :style="{ left: cursorPct(row.grade) }"></span>
      </span>
      <span class="grade-label" :class="`grade-label--${row.grade}`">{{ gradeLabel(row.grade) }}</span>
    </div>
    <p v-if="!rows.length" class="grades-empty">—</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  rows: { type: Array, default: () => [] }   // [{ key, cn, en, grade }]
})

// 四档：正常 / 注意 / 预警 / 严重（G7：红=严重、琥珀=预警；绿仅用于"正常"语义而非涨跌）
const SEGMENTS = [
  { key: 'ok', label: '正常' },
  { key: 'watch', label: '注意' },
  { key: 'warn', label: '预警' },
  { key: 'crit', label: '严重' }
]

const ORDER = { ok: 0, watch: 1, warn: 2, crit: 3 }
const LABELS = Object.fromEntries(SEGMENTS.map(s => [s.key, s.label]))

const rows = computed(() => props.rows)
function gradeLabel(grade) { return LABELS[grade] || '—' }
function cursorPct(grade) {
  const idx = ORDER[grade] ?? 0
  return `${(idx + 0.5) * 25}%`
}
</script>

<style scoped>
.grades-host {
  display: grid;
  gap: 12px;
  padding: 14px 15px;
}

.grade-row {
  display: grid;
  grid-template-columns: 108px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
}

.grade-name {
  display: grid;
  line-height: 1.25;
}

.grade-name b {
  font: 11px Consolas, 'Cascadia Mono', ui-monospace, monospace;
  letter-spacing: .05em;
  color: var(--ds-color-text, var(--smart-text, #E8F2F7));
}

.grade-name small {
  font: 9px Consolas, 'Cascadia Mono', ui-monospace, monospace;
  color: var(--ds-color-muted, var(--smart-muted, #92A6B5));
}

.grade-band {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 2px;
  height: 12px;
}

.grade-seg {
  border-radius: 2px;
  opacity: .22;
}

.grade-seg--ok { background: var(--ds-semantic-success, var(--smart-success, #3FB68B)); }
.grade-seg--watch { background: var(--ds-color-primary, var(--smart-primary, #2496ED)); }
.grade-seg--warn { background: var(--ds-semantic-warning, var(--smart-warning, #D29922)); }
.grade-seg--crit { background: var(--ds-semantic-danger, var(--smart-danger, #F85149)); }

/* 当前档位及之前的段点亮 */
.grade-seg--lit { opacity: .85; }

.grade-cursor {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 18px;
  background: var(--ds-color-text, var(--smart-text, #E8F2F7));
  transform: translateX(-1px);
}

.grade-label {
  font: 10px Consolas, 'Cascadia Mono', ui-monospace, monospace;
  letter-spacing: .08em;
  min-width: 3em;
  text-align: right;
}

.grade-label--ok { color: var(--ds-semantic-success, var(--smart-success, #3FB68B)); }
.grade-label--watch { color: var(--ds-color-primary, var(--smart-primary, #2496ED)); }
.grade-label--warn { color: var(--ds-semantic-warning, var(--smart-warning, #D29922)); }
.grade-label--crit { color: var(--ds-semantic-danger, var(--smart-danger, #F85149)); }

.grades-empty {
  margin: 0;
  color: var(--ds-color-muted, var(--smart-muted, #92A6B5));
  font: 11px Consolas, 'Cascadia Mono', ui-monospace, monospace;
  text-align: center;
}

@media (prefers-reduced-motion: reduce) {
  .grades-host * { transition: none !important; animation: none !important; }
}
</style>
