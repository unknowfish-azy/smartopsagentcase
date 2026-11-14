<template>
  <div class="kr-graph">
    <div ref="chartRef" class="kr-graph__canvas" role="img" aria-label="知识候选执行图谱" />
    <div v-if="hoveredNode" class="kr-graph__tooltip" :style="tooltipStyle">
      <strong>{{ hoveredNode.name }}</strong>
      <span>{{ hoveredNode.category }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { use, init } from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([GraphChart, TooltipComponent, CanvasRenderer])

const props = defineProps({
  /** 知识候选对象（含 title / toolId / traceId / sourceRunId / contentMarkdown） */
  candidate: { type: Object, default: () => null }
})

const emit = defineEmits(['select'])

const chartRef = ref(null)
const hoveredNode = ref(null)
const tooltipStyle = ref({ left: '0px', top: '0px' })

let chartInstance = null
let resizeObserver = null

/* ------------------------------------------------------------------
 * 把候选知识拆成图谱节点：
 *   session  →  根节点（候选标题）
 *   tool     →  工具调用节点
 *   trace    →  Trace 节点
 *   evidence →  从 Markdown 里提取的关键事实/命令/验证项
 * --------------------------------------------------------------- */
function extractEvidence(candidate) {
  const md = candidate?.contentMarkdown || ''
  const nodes = []
  const edges = []
  const rootId = `session:${candidate?.id || 'root'}`

  nodes.push({
    id: rootId,
    name: candidate?.title || '知识候选',
    category: 0,
    symbolSize: 64,
    value: candidate?.summary || ''
  })

  // 工具节点
  if (candidate?.toolId) {
    const toolId = `tool:${candidate.toolId}`
    nodes.push({ id: toolId, name: candidate.toolId, category: 1, symbolSize: 46, value: '诊断工具' })
    edges.push({ source: rootId, target: toolId })
  }

  // Trace 节点
  if (candidate?.traceId) {
    const traceNodeId = `trace:${candidate.traceId}`
    nodes.push({ id: traceNodeId, name: candidate.traceId, category: 2, symbolSize: 38, value: '来源 Trace' })
    edges.push({ source: rootId, target: traceNodeId })
  }

  // 从 Markdown 二级标题提取证据节点
  const sections = md.match(/^##\s+(.+)$/gm) || []
  sections.forEach((heading, idx) => {
    const label = heading.replace(/^##\s+/, '').trim()
    const evidenceId = `evidence:${idx}`
    const category = label.includes('修复') ? 4 : label.includes('验证') ? 3 : label.includes('风险') ? 5 : 3
    nodes.push({
      id: evidenceId,
      name: label,
      category,
      symbolSize: 30 + Math.min(label.length, 12),
      value: label
    })
    edges.push({ source: rootId, target: evidenceId })
  })

  return { nodes, edges }
}

/** 从宿主元素读取设计令牌，保证明暗主题下配色一致 */
function token(name, fallback) {
  if (typeof window === 'undefined' || !chartRef.value) return fallback
  const value = getComputedStyle(chartRef.value).getPropertyValue(name).trim()
  return value || fallback
}

const categoryDefs = [
  { name: '知识候选', token: '--ds-color-primary-strong', fallback: '#7ad7f5' },
  { name: '工具调用', token: '--ds-semantic-success', fallback: '#3fb950' },
  { name: 'Trace', token: '--ds-semantic-warning', fallback: '#d29922' },
  { name: '证据/事实', token: '--ds-color-muted', fallback: '#92a6b5' },
  { name: '修复方案', token: '--ds-semantic-success', fallback: '#3fb950' },
  { name: '风险回滚', token: '--ds-semantic-danger', fallback: '#f85149' }
]

const categories = computed(() => categoryDefs.map(c => ({
  name: c.name,
  itemStyle: { color: token(c.token, c.fallback) }
})))

const option = computed(() => {
  const { nodes, edges } = extractEvidence(props.candidate)
  return {
    backgroundColor: 'transparent',
    tooltip: { show: false },
    animationDuration: 800,
    animationEasingUpdate: 'cubicOut',
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      focusNodeAdjacency: true,
      categories: categories.value,
      data: nodes,
      links: edges,
      force: {
        repulsion: 320,
        edgeLength: [90, 160],
        gravity: 0.08
      },
      label: {
        show: true,
        position: 'bottom',
        color: token('--ds-color-muted', '#92a6b5'),
        fontSize: 11,
        fontFamily: 'var(--font-cn)'
      },
      lineStyle: {
        color: 'source',
        curveness: 0.18,
        opacity: 0.55,
        width: 1.4
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3, opacity: 1 },
        label: { fontSize: 13, fontWeight: 600 }
      },
      itemStyle: {
        borderColor: token('--ds-color-border-strong', 'rgba(255,255,255,0.6)'),
        borderWidth: 1,
        shadowBlur: 16,
        shadowColor: token('--ds-color-primary', '#2496ed')
      }
    }]
  }
})

function render() {
  if (!chartInstance || !chartRef.value) return
  chartInstance.setOption(option.value, true)
}

function bindEvents() {
  if (!chartInstance) return
  chartInstance.on('mouseover', params => {
    if (params.dataType === 'node') {
      hoveredNode.value = { name: params.data.name, category: categories[params.data.category]?.name || '' }
    }
  })
  chartInstance.on('mousemove', params => {
    tooltipStyle.value = { left: `${params.event.offsetX + 14}px`, top: `${params.event.offsetY + 14}px` }
  })
  chartInstance.on('mouseout', () => { hoveredNode.value = null })
  chartInstance.on('click', params => {
    if (params.dataType === 'node') emit('select', params.data)
  })
}

onMounted(() => {
  if (!chartRef.value) return
  chartInstance = init(chartRef.value, null, { renderer: 'canvas' })
  bindEvents()
  render()
  resizeObserver = new ResizeObserver(() => chartInstance?.resize())
  resizeObserver.observe(chartRef.value)
})

watch(() => props.candidate, render, { deep: true })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<style scoped>
.kr-graph { position: relative; width: 100%; height: 100%; min-height: 480px; }
.kr-graph__canvas { width: 100%; height: 100%; }
.kr-graph__tooltip {
  position: absolute; pointer-events: none; z-index: 5;
  display: grid; gap: 2px; padding: 8px 12px;
  border: 1px solid color-mix(in srgb, var(--ds-color-primary-strong) 40%, var(--ds-color-border));
  border-radius: 8px;
  background: var(--ds-surface-overlay);
  box-shadow: var(--ds-elevation-3);
  font-size: 11px; color: var(--ds-color-text);
  white-space: nowrap;
}
.kr-graph__tooltip strong { color: var(--ds-color-primary-strong); font-weight: 560; }
.kr-graph__tooltip span { color: var(--ds-color-muted); font-size: 10px; }
</style>
