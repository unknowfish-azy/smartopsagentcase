<template>
  <div class="ops-chart">
    <div ref="root" class="ops-chart__canvas" :style="{ height: `${height}px` }" role="img" :aria-label="`${title}。可展开下方数据表查看具体数值。`" />
    <details class="ops-chart__data">
      <summary>查看数据表</summary>
      <table>
        <caption>{{ title }}<template v-if="unit"> · {{ unit }}</template></caption>
        <thead><tr><th scope="col">类目</th><th v-for="item in series" :key="item.name" scope="col">{{ item.name }}</th></tr></thead>
        <tbody>
          <tr v-for="(label, index) in labels" :key="label">
            <th scope="row">{{ label }}</th>
            <td v-for="item in series" :key="item.name">{{ item.data[index] ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </details>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { use, init } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, AriaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { resolvedTheme } from '../../theme.js'
import { chartCategoryAxis, chartPalette, chartTextStyle, chartTooltip, chartValueAxis } from '../../design/chartTheme.js'

use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, AriaComponent, CanvasRenderer])

const props = defineProps({
  title: { type: String, required: true },
  /** 'bar' | 'line' */
  type: { type: String, default: 'bar' },
  labels: { type: Array, default: () => [] },
  /** [{ name, data }] */
  series: { type: Array, default: () => [] },
  unit: { type: String, default: '' },
  height: { type: Number, default: 200 },
  /** 按类目的语义色（如 PASS/WARN/HIGH/CRITICAL），长度需与 labels 对齐 */
  colors: { type: Array, default: () => [] }
})

const root = ref(null)
let chart
let observer
let motionQuery

/** 支持 `--ds-chart-*` 令牌名或直接色值；未传时按序列顺序取语义调色板。 */
function resolveColor(token, palette, position) {
  if (!token) return palette[position % palette.length]
  if (typeof token === 'string' && token.startsWith('--') && root.value) {
    return getComputedStyle(root.value).getPropertyValue(token).trim() || palette[position % palette.length]
  }
  return token
}

function seriesOption(item, palette) {
  if (props.type === 'line') {
    return {
      name: item.name,
      data: item.data,
      type: 'line',
      smooth: 0.2,
      connectNulls: false,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2 },
      areaStyle: { opacity: 0.12 },
      emphasis: { focus: 'series' }
    }
  }
  return {
    name: item.name,
    data: props.colors.length
      ? item.data.map((value, position) => ({ value, itemStyle: { color: resolveColor(props.colors[position], palette, position) } }))
      : item.data,
    type: 'bar',
    barWidth: props.series.length > 1 ? 14 : 32,
    itemStyle: { borderRadius: 2 },
    emphasis: { focus: 'series' }
  }
}

function render() {
  if (!chart || !root.value) return
  const palette = chartPalette(root.value)
  chart.setOption({
    animation: !motionQuery?.matches,
    animationDuration: 320,
    color: palette,
    aria: { enabled: true },
    grid: { left: 8, right: 16, top: 18, bottom: 8, containLabel: true },
    legend: props.series.length > 1 ? { top: 0, right: 0, icon: 'roundRect', itemHeight: 3, itemWidth: 16, textStyle: chartTextStyle(root.value, 10) } : { show: false },
    tooltip: chartTooltip(root.value, props.unit),
    xAxis: { ...chartCategoryAxis(root.value, { labels: props.labels }), boundaryGap: props.type === 'bar' },
    yAxis: chartValueAxis(root.value),
    series: props.series.map(item => seriesOption(item, palette))
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

watch([() => props.labels, () => props.series, () => props.colors, () => props.type, resolvedTheme], render, { deep: true, flush: 'post' })

onBeforeUnmount(() => {
  observer?.disconnect()
  motionQuery?.removeEventListener('change', render)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.ops-chart { min-width: 0; }
.ops-chart__canvas { width: 100%; }
.ops-chart__data { margin-top: 8px; color: var(--ds-color-muted); font-size: var(--ds-type-caption-size); overflow-x: auto; }
.ops-chart__data summary { width: fit-content; padding: 6px 0; cursor: pointer; }
.ops-chart__data table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.ops-chart__data caption { padding: 8px 0; text-align: left; color: var(--ds-color-muted); }
.ops-chart__data th,
.ops-chart__data td { padding: 6px 8px; border-bottom: 1px solid var(--ds-hairline); text-align: right; white-space: nowrap; }
.ops-chart__data th:first-child { text-align: left; }
</style>
