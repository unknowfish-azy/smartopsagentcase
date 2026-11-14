<template>
  <section class="dim-grid" aria-label="纠察维度">
    <button
      v-for="(item, index) in cards"
      :key="item.key"
      type="button"
      class="dim-card"
      :class="{ 'dim-card--active': activeKey === item.key, 'dim-card--empty': item.count === 0 }"
      :style="{ '--ml-index': index + 1 }"
      :aria-pressed="activeKey === item.key"
      @click="toggle(item.key)"
    >
      <span class="dim-card__head">
        <span class="dim-card__cn">{{ item.cn }}</span>
        <span class="dim-card__en">{{ item.en }}</span>
      </span>
      <strong class="dim-card__value">{{ item.count ? item.count : '—' }}</strong>
      <svg class="dim-card__spark" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true">
        <polyline
          v-if="item.count"
          :points="item.spark"
          fill="none"
          stroke="var(--ds-color-primary-strong, #7ad7f5)"
          stroke-width="1.5"
          vector-effect="non-scaling-stroke"
        />
        <line
          v-else
          x1="0" y1="18" x2="100" y2="18"
          stroke="var(--ds-color-border, rgba(159,190,207,.18))"
          stroke-width="1"
          stroke-dasharray="3 4"
          vector-effect="non-scaling-stroke"
        />
      </svg>
      <span class="dim-card__foot">{{ item.count ? `${item.count} 条纠察` : '暂无该维度事件' }}</span>
    </button>
  </section>
</template>

<script setup>
/**
 * InspectorDimensionGrid — 8 个纠察维度的数据驱动状态卡
 *
 * 诚实性约束：
 *  - 计数只来自传入事件按 category 的显式别名映射，未匹配的事件不计入任何维度，
 *    绝不把事件"均匀分配"到 8 个维度来凑数；
 *  - 无数据一律显示「—」，不用 0 冒充真实统计；
 *  - DEMO 数据的标注由父页面统一承担（整页醒目角标）。
 */
import { computed } from 'vue'
import { DIMENSIONS, dimensionKeyOf, toEventTimestamp } from './dimensions'

const props = defineProps({
  events: { type: Array, default: () => [] },
  activeKey: { type: String, default: '' }
})
const emit = defineEmits(['select'])

const BUCKETS = 7

function sparklineOf(stamps) {
  if (!stamps.length) return ''
  const min = Math.min(...stamps)
  const max = Math.max(...stamps)
  const span = max - min || 1
  const counts = Array(BUCKETS).fill(0)
  stamps.forEach(stamp => {
    const index = Math.min(BUCKETS - 1, Math.floor(((stamp - min) / span) * BUCKETS))
    counts[index] += 1
  })
  const peak = Math.max(1, ...counts)
  return counts
    .map((count, index) => `${(index / (BUCKETS - 1)) * 100},${22 - (count / peak) * 18}`)
    .join(' ')
}

const cards = computed(() => {
  const grouped = new Map(DIMENSIONS.map(item => [item.key, []]))
  props.events.forEach(event => {
    const key = dimensionKeyOf(event)
    if (key) grouped.get(key).push(toEventTimestamp(event))
  })
  return DIMENSIONS.map(item => {
    const stamps = grouped.get(item.key).filter(stamp => stamp > 0)
    return {
      ...item,
      count: stamps.length,
      spark: sparklineOf(stamps)
    }
  })
})

function toggle(key) {
  emit('select', props.activeKey === key ? '' : key)
}
</script>

<style scoped>
.dim-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.dim-card {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid var(--ds-hairline, rgba(159, 190, 207, .18));
  border-radius: 9px;
  background: var(--ds-surface-raised, #151a21);
  color: var(--ds-color-text, #e8f2f7);
  text-align: left;
  cursor: pointer;
  transition: border-color var(--ds-duration-micro, 150ms) ease, background-color var(--ds-duration-micro, 150ms) ease;
}
.dim-card:hover { border-color: var(--ds-color-primary, #2496ed); }
.dim-card--active {
  border-color: var(--ds-color-primary-strong, #7ad7f5);
  background: var(--ds-surface-overlay, #1b212a);
}
.dim-card--empty { opacity: .72; }
.dim-card__head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; min-width: 0; }
.dim-card__cn { font-size: 13px; font-weight: 500; white-space: nowrap; }
.dim-card__en {
  overflow: hidden;
  color: var(--ds-color-muted, #92a6b5);
  font: 10px var(--font-mono, ui-monospace, monospace);
  letter-spacing: .06em;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dim-card__value {
  font: 300 26px var(--font-mono, ui-monospace, monospace);
  font-variant-numeric: var(--ds-type-num, tabular-nums);
  line-height: 1.1;
}
.dim-card__spark { display: block; width: 100%; height: 22px; }
.dim-card__foot { color: var(--ds-color-muted, #92a6b5); font-size: 11px; }
@media (max-width: 1023px) { .dim-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (prefers-reduced-motion: reduce) { .dim-card { transition: none; } }
</style>
