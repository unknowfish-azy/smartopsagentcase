<template>
  <article class="share-donut-panel">
    <div class="panel-title"><div><p class="eyebrow">MODEL SHARE</p><h2>模型用量份额</h2></div><span class="unit-label">{{ unitLabel }}</span></div>
    <div v-if="slices.length" class="donut-layout">
      <div ref="root" class="donut-chart" role="img" :aria-label="`${title}。可展开下方数据表查看各模型份额。`" />
      <div class="donut-side">
        <p class="donut-total"><strong>{{ fmt(total) }}</strong><span>已知 Token 总量</span></p>
        <ol class="donut-legend">
          <li v-for="(slice, index) in slices" :key="`${slice.connectionId}-${slice.modelName}`">
            <i class="legend-dot" :style="{ opacity: opacityOf(index) }" aria-hidden="true" />
            <b>{{ slice.modelName }}</b>
            <span>{{ (slice.share * 100).toFixed(1) }}% · {{ fmt(slice.knownTokens) }}</span>
          </li>
        </ol>
      </div>
    </div>
    <p v-else class="empty-table">用量未知或暂无调用记录，无法计算模型份额。</p>
    <details v-if="slices.length" class="chart-data">
      <summary>查看份额数据</summary>
      <div class="data-scroll" tabindex="0" aria-label="模型份额数据表">
        <table><caption>模型用量份额 · {{ unitLabel }}</caption><thead><tr><th scope="col">模型</th><th scope="col">已知 Token</th><th scope="col">份额</th><th scope="col">调用次数</th></tr></thead>
          <tbody><tr v-for="slice in slices" :key="`${slice.connectionId}-${slice.modelName}`"><th scope="row">{{ slice.modelName }}</th><td>{{ fmt(slice.knownTokens) }}</td><td>{{ (slice.share * 100).toFixed(1) }}%</td><td>{{ fmt(slice.calls) }}</td></tr>
          </tbody></table>
      </div>
    </details>
    <p class="source-note">{{ note }}</p>
  </article>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { use, init } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, AriaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { resolvedTheme } from '../../theme.js'
import { formatMetric } from './modelAnalytics.js'

use([PieChart, TooltipComponent, AriaComponent, CanvasRenderer])
const props = defineProps({
  title: { type: String, default: '模型用量份额' },
  rows: { type: Array, default: () => [] },
  unitLabel: { type: String, default: '' },
  note: { type: String, default: '' }
})
const fmt = value => formatMetric(value)
// 单霓虹色阶（项目红线：单一强调色，不用多彩调色板）；份额从大到小透明度递减
const slices = computed(() => props.rows.filter(row => row.share != null && row.knownTokens != null))
const total = computed(() => slices.value.reduce((sum, slice) => sum + Number(slice.knownTokens), 0))
const opacityOf = index => 1 - index * 0.55 / Math.max(slices.value.length - 1, 1)
const root = ref(null)
let chart, observer, motionQuery
/* 懒初始化：空态（slices 为空）时 v-if 不渲染图表容器，root 为 null——
   此时绝不能 init(null)（ECharts 会抛，且 mounted hook 的错误会污染 Vue 的
   post flush 队列，导致父组件后续更新全部丢失）。root 随数据出现时再 init，
   root 消失（数据变空）时 dispose，避免 setOption 到游离实例。 */
function render() {
  if (!root.value) {
    if (chart) { observer?.disconnect(); chart?.dispose(); chart = null }
    return
  }
  if (!chart) {
    chart = init(root.value)
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(root.value)
  }
  const css = getComputedStyle(root.value)
  const color = name => css.getPropertyValue(name).trim()
  chart.setOption({
    animation: !motionQuery?.matches,
    animationDuration: 350,
    aria: { enabled: true },
    textStyle: { fontFamily: 'system-ui, sans-serif' },
    color: [color('--smart-primary-strong')],
    tooltip: {
      trigger: 'item', renderMode: 'richText', confine: true,
      backgroundColor: color('--smart-surface'), borderColor: color('--smart-border'),
      textStyle: { color: color('--smart-text'), fontSize: 12 },
      formatter: item => `${item.name}<br/>${fmt(item.value)} Token · ${item.percent}%`
    },
    series: [{
      type: 'pie', radius: ['58%', '82%'], avoidLabelOverlap: true,
      itemStyle: { borderColor: color('--smart-surface'), borderWidth: 2, borderRadius: 3 },
      label: { show: false },
      emphasis: { label: { show: true, color: color('--smart-text'), fontSize: 12, formatter: '{b}\n{d}%' }, scaleSize: 4 },
      data: slices.value.map((slice, index) => ({
        name: slice.modelName, value: Number(slice.knownTokens),
        itemStyle: { color: color('--smart-primary-strong'), opacity: opacityOf(index) }
      }))
    }]
  }, { notMerge: true })
}
onMounted(() => {
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  motionQuery.addEventListener('change', render)
  render() // root 存在才 init；空态时安全跳过
})
watch([slices, resolvedTheme], render, { deep: true, flush: 'post' })
onBeforeUnmount(() => { observer?.disconnect(); motionQuery?.removeEventListener('change', render); chart?.dispose(); chart = null })
</script>

<style scoped>
.share-donut-panel { border: 1px solid var(--smart-border); border-radius: 12px; background: var(--smart-surface); padding: 24px; min-width: 0; }
.donut-layout { display: grid; grid-template-columns: minmax(0, 220px) minmax(0, 1fr); gap: 24px; align-items: center; }
.donut-chart { width: 100%; height: 220px; }
.donut-total { margin: 0 0 14px; }
.donut-total strong { display: block; font-family: var(--font-mono); font-size: 26px; font-weight: 600; font-variant-numeric: tabular-nums; }
.donut-total span { display: block; margin-top: 6px; font-size: 11px; color: var(--smart-muted); }
.donut-legend { list-style: none; margin: 0; padding: 0; }
.donut-legend li { display: grid; grid-template-columns: 10px minmax(0, 1fr) auto; gap: 10px; align-items: baseline; padding: 7px 0; font-size: 12px; }
.donut-legend b { font-weight: 500; overflow-wrap: anywhere; }
.donut-legend span { color: var(--smart-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.legend-dot { width: 8px; height: 8px; border-radius: 2px; background: var(--smart-primary-strong); }
.empty-table { text-align: center; color: var(--smart-muted); padding: 30px; font-size: 12px; }
.chart-data { margin-top: 12px; color: var(--smart-muted); font-size: 12px; }
.chart-data summary { cursor: pointer; width: fit-content; padding: 8px 0; }
.data-scroll { overflow-x: auto; max-height: 320px; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
caption { padding: 12px; text-align: left; }
th, td { padding: 10px; border-bottom: 1px solid var(--smart-border); text-align: right; white-space: nowrap; }
th:first-child { text-align: left; }
.source-note { color: var(--smart-muted); font-size: 11px; line-height: 1.8; margin: 12px 0 0; }
@media (max-width: 767px) {
  .share-donut-panel { padding: 18px 14px; }
  .donut-layout { grid-template-columns: minmax(0, 1fr); gap: 14px; }
  .donut-chart { height: 200px; max-width: 260px; margin: 0 auto; }
}
</style>
