<template>
  <div
    class="quota-ring"
    role="progressbar"
    :aria-label="ariaLabel"
    :aria-valuenow="Math.round(state.percent)"
    aria-valuemin="0"
    aria-valuemax="100"
  >
    <svg :viewBox="`0 0 ${size} ${size}`" class="quota-ring__svg" aria-hidden="true">
      <circle class="quota-ring__track" :cx="center" :cy="center" :r="radius" />
      <circle
        class="quota-ring__bar"
        :class="`quota-ring__bar--${state.level}`"
        :cx="center" :cy="center" :r="radius"
        :stroke-dasharray="dashArray"
      />
    </svg>
    <div class="quota-ring__label">
      <strong>{{ Math.round(state.percent) }}<small>%</small></strong>
      <span>{{ state.overage > 0 ? '已超额' : '已用' }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatMetric, quotaRingState } from './modelAnalytics.js'

const props = defineProps({
  // 月度额度（Token）；null 表示未设额度，父级应避免渲染本组件
  budget: { type: Number, default: null },
  // 已知用量（Token）
  used: { type: Number, default: 0 },
  size: { type: Number, default: 132 }
})

const state = computed(() => quotaRingState(props.budget, props.used))
const center = computed(() => props.size / 2)
const radius = computed(() => props.size / 2 - 7)
// 周长 = 2πr；超额时画满整圈
const dashArray = computed(() => {
  const circumference = 2 * Math.PI * radius.value
  return `${(state.value.percent / 100 * circumference).toFixed(2)} ${circumference.toFixed(2)}`
})
const ariaLabel = computed(() =>
  `月度 Token 额度已用 ${Math.round(state.value.percent)}%：${formatMetric(props.used)} / ${formatMetric(props.budget)} Token`
)
</script>

<style scoped>
.quota-ring { position: relative; display: grid; place-items: center; width: 132px; height: 132px; flex: none; }
.quota-ring__svg { width: 100%; height: 100%; transform: rotate(-90deg); }
.quota-ring__track { fill: none; stroke: var(--smart-border); stroke-width: 6; }
.quota-ring__bar { fill: none; stroke-width: 6; stroke-linecap: round; transition: stroke-dasharray .6s cubic-bezier(.22, 1, .36, 1), stroke 300ms; }
/* 等级 → 状态令牌：healthy=success / warning=warning / critical·exceeded=danger */
.quota-ring__bar--healthy { stroke: var(--smart-success); }
.quota-ring__bar--warning { stroke: var(--smart-warning); }
.quota-ring__bar--critical, .quota-ring__bar--exceeded { stroke: var(--smart-danger); }
.quota-ring__label { position: absolute; inset: 0; display: grid; place-content: center; justify-items: center; gap: 4px; }
.quota-ring__label strong { font: 500 30px/1 var(--font-mono); font-variant-numeric: tabular-nums; color: var(--smart-text); }
.quota-ring__label strong small { font-size: 13px; color: var(--smart-muted); margin-left: 2px; }
.quota-ring__label span { font: 10px var(--font-mono); letter-spacing: .12em; color: var(--smart-muted); }
@media (prefers-reduced-motion: reduce) { .quota-ring__bar { transition: none; } }
</style>
