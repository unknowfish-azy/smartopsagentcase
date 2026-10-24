<template>
  <div
      ref="chartRef"
      class="metric-chart"
  ></div>
</template>

<script setup>
import {
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref
} from 'vue'

import { use, init } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const chartRef = ref(null)

let chart = null

function initChart() {

  if (!chartRef.value) {
    return
  }

  chart = init(chartRef.value)

  chart.setOption({
    tooltip: {
      trigger: 'axis'
    },

    xAxis: {
      type: 'category',
      data: [
        '10:00',
        '10:05',
        '10:10',
        '10:15',
        '10:20'
      ]
    },

    yAxis: {
      type: 'value',
      max: 100
    },

    series: [
      {
        name: 'CPU',
        type: 'line',
        smooth: true,
        data: [
          31,
          42,
          38,
          55,
          47
        ]
      }
    ]
  })
}

function resize() {
  chart?.resize()
}

onMounted(async () => {
  await nextTick()
  initChart()

  window.addEventListener(
      'resize',
      resize
  )
})

onBeforeUnmount(() => {

  window.removeEventListener(
      'resize',
      resize
  )

  chart?.dispose()
})
</script>

<style scoped>
.metric-chart {
  width: 100%;
  height: 320px;
}
</style>
