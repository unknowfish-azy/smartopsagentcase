<template>
  <div class="line-chart-component">
    <div ref="root" class="line-chart" role="img" :aria-label="`${title}。可展开下方数据表查看每日数值。`" />
    <details class="chart-data">
      <summary>查看每日数据</summary>
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
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, AriaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { resolvedTheme } from '../../theme.js'
import { formatMetric } from '../model/modelAnalytics.js'
import { chartCategoryAxis, chartPalette, chartTooltip, chartValueAxis } from '../../design/chartTheme.js'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, AriaComponent, CanvasRenderer])
const props = defineProps({
  title: { type: String, required: true },
  labels: { type: Array, default: () => [] },
  series: { type: Array, default: () => [] },
  unit: { type: String, default: 'Token' },
  maximum: { type: Number, default: undefined },
  reference: { type: Object, default: null } // { name, value }：横向虚线参考线（如额度节奏线）；不传时行为不变
})
const root = ref(null)
let chart, observer, motionQuery
function render() {
  if (!chart || !root.value) return
  const css = getComputedStyle(root.value)
  const color = name => css.getPropertyValue(name).trim()
  // 语义调色板（最多 5 色）由 design/chartTheme.js 统一提供，禁止组件内写死彩虹色。
  const palette = chartPalette(root.value)
  chart.setOption({
    animation: !motionQuery?.matches,
    animationDuration: 480,
    animationDurationUpdate: 280,
    animationEasing: 'cubicOut',
    color: palette,
    aria: { enabled: true },
    textStyle: { fontFamily: 'system-ui, sans-serif' },
    grid: { left: 10, right: 22, top: 42, bottom: 12, containLabel: true },
    legend: { top: 0, left: 0, icon: 'roundRect', itemHeight: 3, itemWidth: 18, textStyle: { color: color('--ds-chart-text') } },
    tooltip: chartTooltip(root.value, props.unit, value => value == null ? '未上报' : `${formatMetric(value, 1)} ${props.unit}`),
    xAxis: chartCategoryAxis(root.value, { labels: props.labels, formatter: value => value.slice(5) }),
    yAxis: chartValueAxis(root.value, { maximum: props.maximum }),
    series: props.series.map((item, index) => {
      const base = { name: item.name, data: item.data, type: 'line', smooth: 0.2, smoothMonotone: 'x', connectNulls: false, showSymbol: item.data.some((value, position) => value != null && item.data[position - 1] == null && item.data[position + 1] == null), symbolSize: 6, lineStyle: { width: 2 }, emphasis: { focus: 'series' }, animationDuration: 480, animationEasing: 'cubicOut' }
      // 参考线挂在首序列上（markLine 不参与图例与数据表，避免污染逐日数值口径）
      if (index === 0 && props.reference && Number.isFinite(Number(props.reference.value))) {
        base.markLine = {
          silent: true, symbol: 'none', animation: false,
          data: [{ yAxis: Number(props.reference.value) }],
          lineStyle: { color: color('--smart-primary-strong'), type: 'dashed', width: 1 },
          label: { formatter: props.reference.name, color: color('--smart-muted'), fontSize: 10, position: 'insideEndTop' }
        }
      }
      return base
    })
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
.line-chart-component { min-width: 0; }.line-chart { width: 100%; height: 280px; }.chart-data { margin-top: 12px; color: var(--smart-muted); font-size: 12px; }.chart-data summary { cursor: pointer; width: fit-content; padding: 8px 0; }.data-scroll { overflow-x: auto; max-height: 320px; }table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }caption { padding: 12px; text-align: left; }th, td { padding: 10px; border-bottom: 1px solid var(--smart-border); text-align: right; white-space: nowrap; }th:first-child { text-align: left; }@media(max-width: 600px) { .line-chart { height: 240px; } }
</style>
