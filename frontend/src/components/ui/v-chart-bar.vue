<template>
  <div class="stack-chart-component">
    <div ref="root" class="stack-chart" role="img" :aria-label="`${title}。可展开下方数据表查看每日数值。`" />
    <details class="chart-data">
      <summary>查看每日构成</summary>
      <div class="data-scroll" tabindex="0" :aria-label="`${title}数据表`">
        <table><caption>{{ title }} · {{ unit }}</caption><thead><tr><th scope="col">日期（UTC）</th><th v-for="item in series" :key="item.name" scope="col">{{ item.name }}</th></tr></thead>
          <tbody><tr v-for="(label, index) in labels" :key="label"><th scope="row">{{ label }}</th><td v-for="item in series" :key="item.name">{{ formatMetric(item.data[index], 1) }}</td></tr></tbody>
        </table>
      </div>
    </details>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { use, init } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, AriaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { resolvedTheme } from '../../theme.js'
import { formatMetric } from '../model/modelAnalytics.js'
import { chartCategoryAxis, chartPalette, chartTooltip, chartValueAxis } from '../../design/chartTheme.js'

use([BarChart, GridComponent, TooltipComponent, LegendComponent, AriaComponent, CanvasRenderer])
const props = defineProps({
  title: { type: String, required: true },
  labels: { type: Array, default: () => [] },
  series: { type: Array, default: () => [] },
  unit: { type: String, default: 'Token' },
  maximum: { type: Number, default: undefined }
})
const root = ref(null)
let chart, observer, motionQuery
function render() {
  if (!chart || !root.value) return
  const css = getComputedStyle(root.value)
  const color = name => css.getPropertyValue(name).trim()
  // 语义调色板（最多 5 色）由 design/chartTheme.js 统一提供。
  const palette = chartPalette(root.value)
  chart.setOption({
    animation: !motionQuery?.matches,
    animationDuration: 360,
    animationDurationUpdate: 280,
    animationEasing: 'cubicOut',
    color: palette,
    aria: { enabled: true },
    textStyle: { fontFamily: 'system-ui, sans-serif' },
    grid: { left: 10, right: 22, top: 34, bottom: 12, containLabel: true },
    // 图例右上：10px mono 小字（Helicone 式图表密度）
    legend: { top: 0, right: 0, icon: 'roundRect', itemHeight: 3, itemWidth: 18, textStyle: { color: color('--ds-chart-text'), fontSize: 10, fontFamily: 'var(--font-mono, ui-monospace)' } },
    tooltip: { ...chartTooltip(root.value, props.unit, value => value == null ? '未上报' : `${formatMetric(value, 1)} ${props.unit}`), axisPointer: { type: 'shadow' } },
    xAxis: { ...chartCategoryAxis(root.value, { labels: props.labels, formatter: value => value.slice(5) }), boundaryGap: true },
    yAxis: chartValueAxis(root.value, { maximum: props.maximum }),
    // 堆叠柱：6px 柱宽、无圆角、2px 系列间距——科技感来自几何锐利度，不是发光
    series: props.series.map((item, seriesIndex) => ({
      name: item.name, data: item.data, type: 'bar', stack: 'usage',
      barWidth: 6, barGap: '20%',
      itemStyle: { borderRadius: 0 },
      emphasis: { focus: 'series' },
      // E6 柱状错峰：每根柱 90ms 步进；多系列时同下标柱同时生长
      animationDelay: idx => idx * 90 + seriesIndex * 20,
      animationDuration: 360,
      animationEasing: 'cubicOut'
    }))
  }, { notMerge: true })
}
onMounted(() => {
  chart = init(root.value)
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  motionQuery.addEventListener('change', render)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(root.value)
  render()
})
watch([() => props.labels, () => props.series, () => props.maximum, resolvedTheme], render, { deep: true, flush: 'post' })
onBeforeUnmount(() => { observer?.disconnect(); motionQuery?.removeEventListener('change', render); chart?.dispose(); chart = null })
</script>

<style scoped>
.stack-chart-component { min-width: 0; }.stack-chart { width: 100%; height: 220px; }.chart-data { margin-top: 12px; color: var(--smart-muted); font-size: 12px; }.chart-data summary { cursor: pointer; width: fit-content; padding: 8px 0; }.data-scroll { overflow-x: auto; max-height: 320px; }table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }caption { padding: 12px; text-align: left; }th, td { padding: 10px; border-bottom: 1px solid var(--smart-border); text-align: right; white-space: nowrap; }th:first-child { text-align: left; }@media(max-width: 600px) { .stack-chart { height: 200px; } }
</style>
