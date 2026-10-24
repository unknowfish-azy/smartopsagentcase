<template>
  <svg class="metric-spark" viewBox="0 0 108 34" preserveAspectRatio="none" aria-hidden="true" focusable="false">
    <template v-for="(segment, index) in geometry.segments" :key="index">
      <polyline :points="segment" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
    </template>
    <circle v-if="geometry.last" :cx="geometry.last.x" :cy="geometry.last.y" r="2.6" fill="currentColor" />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

/* KPI 卡内的微趋势线（codeburn 的 sparkline card）。纯装饰：数值本身是可访问内容，
   这里 aria-hidden；null 视为断点分段不断线；静态渲染，无动画需要降级。 */
const props = defineProps({ values: { type: Array, default: () => [] } })

const geometry = computed(() => {
  const values = (props.values || []).map(value => value == null || !Number.isFinite(Number(value)) ? null : Number(value))
  const present = values.filter(value => value != null)
  if (present.length < 2) return { segments: [], last: null }
  const min = Math.min(...present), max = Math.max(...present), span = max - min
  const step = values.length > 1 ? 108 / (values.length - 1) : 0
  const y = value => span === 0 ? 17 : 30 - (value - min) / span * 26
  const segments = []
  let current = []
  values.forEach((value, index) => {
    if (value == null) { if (current.length) segments.push(current.join(' ')); current = []; return }
    current.push(`${(index * step).toFixed(2)},${y(value).toFixed(2)}`)
  })
  if (current.length) segments.push(current.join(' '))
  const lastIndex = values.length - 1 - [...values].reverse().findIndex(value => value != null)
  const lastValue = values[lastIndex]
  return { segments, last: { x: lastIndex * step, y: y(lastValue) } }
})
</script>
