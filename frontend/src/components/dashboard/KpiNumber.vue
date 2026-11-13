<template>
  <span class="kpi-number u-num">{{ display }}</span>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useCountUp } from '../../composables/useCountUp'

/**
 * KPI 数字展示：纯数字走 count-up（从 0 滚到真实值），非数字（如「—」）直接显示。
 * tabular-nums 由 .u-num 保证宽度恒定，避免滚动时 CLS。
 */
const props = defineProps({
  value: { type: [String, Number], default: '—' },
  decimals: { type: Number, default: 0 }
})

const numeric = computed(() => {
  const n = Number(props.value)
  return Number.isFinite(n) ? n : null
})

const target = ref(numeric.value)
const { display } = useCountUp(target, { decimals: props.decimals })

watch(numeric, v => { target.value = v })
</script>

<style scoped>
.kpi-number { font-variant-numeric: tabular-nums; display: inline-block; min-width: 1ch; }
</style>
