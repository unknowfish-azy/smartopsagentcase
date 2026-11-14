<template>
  <section class="axis-card" role="tabpanel" :aria-labelledby="`axis-${view}`">
    <div class="axis-title">
      <h2>共享时间轴 · <span class="view-name">{{ viewLabel }}</span></h2>
      <span class="axis-count">{{ windowKey }} · {{ countLabel }}</span>
    </div>
    <div class="axis-canvas-wrap" ref="wrapRef">
      <canvas ref="canvasRef" role="img" :aria-label="`洞察台时间轴 · ${viewLabel} 投影 · ${countLabel}`"></canvas>
      <div v-if="emptyState" class="axis-empty">{{ emptyState }}</div>
      <div v-else-if="errorState" class="axis-error"><span>{{ errorState }}</span><button @click="$emit('retry')">重试</button></div>
      <div v-else-if="loadingState" class="axis-empty">加载中…</div>
      <div v-show="tip.visible" class="tip" :style="tip.style" v-html="tip.html"></div>
    </div>
    <div class="axis-foot">
      <template v-if="view === 'events'">
        <span v-for="s in severities" :key="s.key"><i :style="{ background: s.color }"></i>{{ s.cn }}</span>
        <span><i class="dot-linked"></i>带小点 = 已关联运行</span>
      </template>
      <template v-else-if="view === 'stats'">
        <span v-for="s in severities" :key="s.key"><i :style="{ background: s.color }"></i>{{ s.cn }}</span>
        <span>同一批纠察按时间分箱 · 窗口内前端聚合</span>
      </template>
      <template v-else>
        <span><i class="dot-ok"></i>SUCCESS</span>
        <span><i class="dot-warn"></i>TIMEOUT</span>
        <span><i class="dot-bad"></i>FAILED</span>
        <span><i class="dot-linked"></i>已关联 trace</span>
      </template>
    </div>
    <!-- 屏幕阅读器列表：当前投影可见项 -->
    <ul class="sr-only">
      <template v-if="view === 'events'">
        <li v-for="e in events" :key="e.id">{{ fmtDateTime(e.at) }} · {{ severityMeta(e.severity).cn }} · {{ e.taskId }} · {{ e.traceId ? '已关联' : '未关联' }}</li>
      </template>
      <template v-else-if="view === 'runs'">
        <li v-for="r in runs" :key="r.id">{{ fmtDateTime(r.at) }} · {{ r.tool }} · {{ r.status }} · {{ r.traceId ? '已关联 trace' : '未关联' }}</li>
      </template>
      <template v-else>
        <li v-for="(b, i) in bins" :key="i">{{ fmtDateTime(b.from) }}–{{ fmtTime(b.to) }} · 严重 {{ b.CRITICAL }} 高 {{ b.HIGH }} 警告 {{ b.WARN }} 通过 {{ b.PASS }}</li>
      </template>
    </ul>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  SEVERITIES, TOOLS, BIN_COUNTS, binEvents, fmtDateTime, fmtTime,
  runsByTraceMap, severityMeta, toolMeta
} from './deskModel'

const props = defineProps({
  view: { type: String, required: true },
  windowKey: { type: String, required: true },
  events: { type: Array, default: () => [] },
  runs: { type: Array, default: () => [] },
  range: { type: Object, required: true },
  selected: { type: Object, default: null },
  eventsStatus: { type: String, default: 'ready' },
  runsStatus: { type: String, default: 'ready' },
  eventsError: { type: String, default: '' },
  runsError: { type: String, default: '' }
})
const emit = defineEmits(['select', 'hover', 'retry'])

const canvasRef = ref(null)
const wrapRef = ref(null)
const tip = ref({ visible: false, html: '', style: {} })

const severities = SEVERITIES
const viewLabel = { events: '纠察', stats: '统计', runs: '运行' }[props.view]
const countLabel = computed(() => {
  if (props.view === 'events') return `${props.events.length} 条纠察`
  if (props.view === 'runs') return `${props.runs.length} 条运行`
  return `${props.events.length} 条纠察`
})

const emptyState = computed(() => {
  if (props.view === 'events' && props.eventsStatus === 'ready' && !props.events.length) return '窗口内没有纠察事件'
  if (props.view === 'runs' && props.runsStatus === 'ready' && !props.runs.length) return '窗口内没有运行记录'
  return ''
})
const errorState = computed(() => {
  if (props.view === 'runs' && props.runsStatus === 'error') return props.runsError
  if ((props.view === 'events' || props.view === 'stats') && props.eventsStatus === 'error') return props.eventsError
  return ''
})
const loadingState = computed(() => {
  if (props.view === 'runs') return props.runsStatus === 'loading'
  return props.eventsStatus === 'loading'
})

const runsByTrace = computed(() => runsByTraceMap(props.runs))

const bins = computed(() => binEvents(props.events, props.windowKey, props.range.start, props.range.end))

/* ---------- 布局 ---------- */
const M = { l: 56, r: 16, t: 16, b: 36 }

function layout() {
  const rect = wrapRef.value.getBoundingClientRect()
  return { width: rect.width, height: rect.height }
}

function xOf(ts, rect) {
  const { start, end } = props.range
  return M.l + ((ts - start) / (end - start)) * (rect.width - M.l - M.r)
}

/* ---------- 绘制 ---------- */
let ctx = null
let rafId = null
let transitionStart = 0
let previousView = null
const reduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

function draw() {
  const rect = layout()
  if (!rect.width) return
  const canvas = canvasRef.value
  const dpr = window.devicePixelRatio || 1
  if (canvas.width !== Math.round(rect.width * dpr) || canvas.height !== Math.round(rect.height * dpr)) {
    canvas.width = Math.round(rect.width * dpr)
    canvas.height = Math.round(rect.height * dpr)
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, rect.width, rect.height)

  drawGrid(rect)
  drawSelectionBand(rect)

  const now = performance.now()
  const progress = previousView ? Math.min(1, (now - transitionStart) / (reduced ? 1 : 420)) : 1
  if (previousView && progress < 1) {
    drawProjection(previousView, 1 - progress, -6, rect)
    drawProjection(props.view, progress, 6 * (1 - progress), rect)
    rafId = requestAnimationFrame(draw)
  } else {
    previousView = null
    drawProjection(props.view, 1, 0, rect)
  }
  drawHover(rect)
}

function drawGrid(rect) {
  const { start, end } = props.range
  const span = end - start
  const wide = rect.width >= 640
  const steps = wide ? (props.windowKey === '24h' ? 6 : 7) : 3
  ctx.font = '10px Consolas, monospace'
  ctx.textBaseline = 'middle'
  for (let i = 0; i <= steps; i += 1) {
    const t = start + (span / steps) * i
    const x = xOf(t, rect)
    ctx.strokeStyle = 'rgba(255,255,255,.055)'
    ctx.beginPath()
    ctx.moveTo(x, M.t)
    ctx.lineTo(x, rect.height - M.b)
    ctx.stroke()
    ctx.fillStyle = '#5d6b78'
    ctx.textAlign = i === 0 ? 'left' : i === steps ? 'right' : 'center'
    const date = new Date(t)
    const md = date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
    const label = props.windowKey === '24h'
      ? (wide ? `${md} ${date.getHours()}时` : `${date.getHours()}时`)
      : md
    ctx.fillText(label, x, rect.height - 13)
  }
  ctx.textAlign = 'left'
}

function drawSelectionBand(rect) {
  if (!props.selected) return
  const x = xOf(props.selected.at, rect)
  ctx.fillStyle = 'rgba(122,215,245,.07)'
  ctx.fillRect(x - 1, M.t, 2, rect.height - M.t - M.b)
  ctx.strokeStyle = 'rgba(122,215,245,.35)'
  ctx.setLineDash([3, 4])
  ctx.beginPath()
  ctx.moveTo(x, M.t)
  ctx.lineTo(x, rect.height - M.b)
  ctx.stroke()
  ctx.setLineDash([])
}

function drawProjection(view, alpha, dy, rect) {
  ctx.save()
  ctx.globalAlpha = alpha
  ctx.translate(0, dy)
  if (view === 'events') drawEvents(rect)
  else if (view === 'stats') drawStats(rect)
  else if (view === 'runs') drawRuns(rect)
  ctx.restore()
}

function drawEvents(rect) {
  const events = props.events
  const lanes = SEVERITIES
  const laneH = (rect.height - M.t - M.b - 40) / lanes.length

  lanes.forEach((lane, index) => {
    const y = M.t + laneH * (index + 0.5)
    ctx.fillStyle = '#5d6b78'
    ctx.font = '10px Consolas, monospace'
    ctx.textBaseline = 'middle'
    ctx.fillText(lane.cn, 8, y)
    ctx.strokeStyle = 'rgba(255,255,255,.04)'
    ctx.beginPath()
    ctx.moveTo(M.l, y)
    ctx.lineTo(rect.width - M.r, y)
    ctx.stroke()
  })

  events.forEach(event => {
    const lane = lanes.findIndex(item => item.key === event.severity)
    const y = M.t + laneH * (lane + 0.5)
    const x = xOf(event.at, rect)
    const selected = props.selected?.id === event.id
    const linked = runsByTrace.value.has(event.traceId)

    ctx.strokeStyle = 'rgba(255,255,255,.16)'
    ctx.beginPath()
    ctx.moveTo(x, y)
    ctx.lineTo(x, y + (linked ? 12 : 6))
    ctx.stroke()

    ctx.beginPath()
    ctx.arc(x, y, selected ? 6 : 4, 0, Math.PI * 2)
    ctx.fillStyle = severityMeta(event.severity).color
    ctx.fill()
    if (selected) {
      ctx.beginPath()
      ctx.arc(x, y, 10, 0, Math.PI * 2)
      ctx.strokeStyle = severityMeta(event.severity).color
      ctx.stroke()
    }
    if (linked) {
      ctx.beginPath()
      ctx.arc(x, y + 14, 2, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(122,215,245,.85)'
      ctx.fill()
    }
  })

  // 密度带
  const list = bins.value
  const maxBin = Math.max(1, ...list.map(bin => bin.CRITICAL + bin.HIGH + bin.WARN + bin.PASS))
  const binW = (rect.width - M.l - M.r) / list.length
  const top = rect.height - M.b - 30
  ctx.fillStyle = '#5d6b78'
  ctx.font = '9px Consolas, monospace'
  ctx.fillText('密度', 14, top + 8)
  list.forEach((bin, index) => {
    const total = bin.CRITICAL + bin.HIGH + bin.WARN + bin.PASS
    if (!total) return
    const x = xOf(bin.from, rect) + 2
    const h = Math.max(2, (total / maxBin) * 18)
    ctx.fillStyle = 'rgba(36,150,237,.4)'
    ctx.fillRect(x, top + 22 - h, Math.max(2, binW - 4), h)
  })
}

function drawStats(rect) {
  const list = bins.value
  const max = Math.max(1, ...list.map(bin => bin.CRITICAL + bin.HIGH + bin.WARN + bin.PASS))
  const base = rect.height - M.b
  const usable = rect.height - M.t - M.b - 26
  const gap = 4
  const barW = Math.max(6, Math.min(26, (rect.width - M.l - M.r) / list.length - gap))
  const binW = (rect.width - M.l - M.r) / list.length

  list.forEach((bin, index) => {
    const x = xOf(bin.from, rect) + (binW - barW) / 2
    let y = base
    SEVERITIES.slice().reverse().forEach(lane => {
      const value = bin[lane.key]
      if (!value) return
      const h = (value / max) * usable
      ctx.fillStyle = lane.color
      ctx.globalAlpha = 0.82
      ctx.fillRect(x, y - h, barW, h)
      ctx.globalAlpha = 1
      y -= h
    })
  })

  ctx.fillStyle = '#5d6b78'
  ctx.font = '10px Consolas, monospace'
  const tickStep = Math.max(1, Math.ceil(max / 4))
  const tickCount = Math.max(1, Math.ceil(max / tickStep))
  for (let i = 0; i <= tickCount; i += 1) {
    const value = tickStep * i
    const y = base - (usable / tickCount) * i
    ctx.fillText(String(value), 24, y)
    ctx.strokeStyle = 'rgba(255,255,255,.05)'
    ctx.beginPath()
    ctx.moveTo(M.l, y)
    ctx.lineTo(rect.width - M.r, y)
    ctx.stroke()
  }

  if (props.selected) {
    const index = list.findIndex(bin => props.selected.at >= bin.from && props.selected.at < bin.to)
    if (index >= 0) {
      const x = xOf(list[index].from, rect)
      ctx.strokeStyle = 'rgba(122,215,245,.7)'
      ctx.strokeRect(x + 1, M.t, binW - 2, base - M.t)
    }
  }
}

function runPositions(rect) {
  const runs = props.runs
  const laneH = (rect.height - M.t - M.b) / TOOLS.length
  const seen = {}
  return runs.map(run => {
    const lane = TOOLS.findIndex(item => item.key === run.tool)
    const count = (seen[run.tool] = (seen[run.tool] || 0) + 1) - 1
    const row = count % 3
    const y = M.t + laneH * lane + laneH * 0.5 + (row - 1) * 11
    return { run, x: xOf(run.at, rect), y, width: Math.max(4, (run.duration / 40) * 54) }
  })
}

function drawRuns(rect) {
  const runs = props.runs
  const lanes = TOOLS
  const laneH = (rect.height - M.t - M.b) / lanes.length

  lanes.forEach((lane, index) => {
    const y = M.t + laneH * (index + 0.5)
    ctx.fillStyle = '#5d6b78'
    ctx.font = '10px Consolas, monospace'
    ctx.textBaseline = 'middle'
    ctx.fillText(lane.key.split('-')[0], 8, y)
    ctx.strokeStyle = 'rgba(255,255,255,.04)'
    ctx.beginPath()
    ctx.moveTo(M.l, y)
    ctx.lineTo(rect.width - M.r, y)
    ctx.stroke()
  })

  runPositions(rect).forEach(({ run, x, y, width }) => {
    const selected = props.selected?.id === run.id
    const color = run.status === 'SUCCESS' ? '#3fb950' : run.status === 'FAILED' ? '#f85149' : '#d29922'
    ctx.fillStyle = color
    ctx.globalAlpha = selected ? 1 : 0.78
    ctx.fillRect(x, y - 3, width, 6)
    ctx.globalAlpha = 1
    if (selected) {
      ctx.strokeStyle = '#e8f2f7'
      ctx.strokeRect(x - 1, y - 5, width + 2, 10)
    }
    if (run.traceId) {
      ctx.fillStyle = 'rgba(122,215,245,.9)'
      ctx.fillRect(x, y + 5, 2, 2)
    }
  })
}

let hoverPos = null
function drawHover(rect) {
  if (!hoverPos) { tip.value = { visible: false, html: '', style: {} }; return }
  const item = hitTest(hoverPos.x, hoverPos.y)
  if (!item) { tip.value = { visible: false, html: '', style: {} }; return }

  const x = xOf(item.at, rect)
  ctx.strokeStyle = 'rgba(232,242,247,.3)'
  ctx.setLineDash([2, 3])
  ctx.beginPath()
  ctx.moveTo(x, M.t)
  ctx.lineTo(x, rect.height - M.b)
  ctx.stroke()
  ctx.setLineDash([])

  const isRun = item.__type === 'run'
  const html = `<b>${item.id}</b>` +
    `<span><i>时间</i><i>${fmtDateTime(item.at)}</i></span>` +
    (isRun
      ? `<span><i>工具</i><i>${toolMeta(item.tool).cn}</i></span><span><i>结果</i><i>${item.status}${item.exitCode == null ? '' : ` · exit ${item.exitCode}`}</i></span><span><i>时长</i><i>${Number(item.duration).toFixed(1)}s</i></span>`
      : `<span><i>等级</i><i>${severityMeta(item.severity).cn}</i></span><span><i>任务</i><i>${item.taskId}</i></span><span><i>目标</i><i>${item.target || '—'}</i></span>`) +
    `<span><i>关联</i><i>${item.traceId ? '已关联 trace' : '未关联'}</i></span>`
  tip.value = {
    visible: true,
    html,
    style: { left: `${Math.min(rect.width - 110, Math.max(110, x))}px`, top: `${Math.max(84, hoverPos.y - 10)}px` }
  }
}

function hitTest(px, py) {
  const rect = canvasRef.value.getBoundingClientRect()
  if (px < M.l || px > rect.width - M.r) return null
  if (props.view === 'events') {
    const laneH = (rect.height - M.t - M.b - 40) / SEVERITIES.length
    let best = null
    props.events.forEach(event => {
      const lane = SEVERITIES.findIndex(item => item.key === event.severity)
      const x = xOf(event.at, rect)
      const y = M.t + laneH * (lane + 0.5)
      if (Math.hypot(px - x, py - y) < 12) best = { ...event, __type: 'event' }
    })
    return best
  }
  if (props.view === 'runs') {
    let best = null
    runPositions(rect).forEach(({ run, x, y, width }) => {
      if (px >= x - 4 && px <= x + width + 4 && Math.abs(py - y) < 7) best = { ...run, __type: 'run' }
    })
    return best
  }
  const list = bins.value
  const index = Math.floor(((px - M.l) / (rect.width - M.l - M.r)) * list.length)
  const bin = list[Math.max(0, Math.min(list.length - 1, index))]
  if (!bin) return null
  const total = bin.CRITICAL + bin.HIGH + bin.WARN + bin.PASS
  if (!total) return null
  return { __type: 'bin', id: `BIN ${fmtTime(bin.from)}–${fmtTime(bin.to)}`, at: (bin.from + bin.to) / 2 }
}

/* ---------- 事件 ---------- */
function onPointerMove(e) {
  const rect = canvasRef.value.getBoundingClientRect()
  hoverPos = { x: e.clientX - rect.left, y: e.clientY - rect.top }
  draw()
}
function onPointerLeave() {
  hoverPos = null
  draw()
}
function onClick() {
  if (!hoverPos) return
  const item = hitTest(hoverPos.x, hoverPos.y)
  if (item && item.__type !== 'bin') emit('select', item)
}

let ro = null
function start() {
  ctx = canvasRef.value.getContext('2d')
  draw()
  ro = new ResizeObserver(() => draw())
  ro.observe(wrapRef.value)
}
function stop() {
  if (rafId) cancelAnimationFrame(rafId)
  if (ro) ro.disconnect()
}

watch(() => props.view, (nv, ov) => {
  if (nv !== ov) {
    previousView = ov
    transitionStart = performance.now()
  }
  draw()
})
watch([() => props.events, () => props.runs, () => props.selected, () => props.windowKey, () => props.range], draw, { deep: false })

onMounted(start)
onBeforeUnmount(stop)
</script>

<style scoped>
.axis-card { background: var(--ds-surface-raised); border: 1px solid var(--ds-surface-overlay); border-radius: 12px; padding: 16px; min-height: 480px; display: flex; flex-direction: column; }
.axis-title { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; }
.axis-title h2 { margin: 0; font-size: 16px; }
.view-name { color: var(--smart-primary); }
.axis-count { color: var(--smart-muted); font-size: 12px; }
.axis-canvas-wrap { width: 100%; height: 420px; position: relative; flex: 1; }
.axis-canvas-wrap canvas { width: 100%; height: 100%; display: block; }
.axis-empty, .axis-error { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--smart-muted); font-size: 13px; }
.axis-error button { background: var(--ds-surface-overlay); border: 0; color: var(--smart-text); padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.tip { position: absolute; z-index: 5; min-width: 186px; padding: 8px 10px; border: 1px solid color-mix(in srgb, var(--smart-surface) 14%, transparent); border-radius: 5px; background: var(--smart-surface-raised); color: var(--smart-text); font: 10.5px/1.65 Consolas, monospace; pointer-events: none; transform: translate(-50%, -110%); }
.tip b { display: block; margin-bottom: 4px; color: var(--smart-primary-strong); }
.tip span { display: flex; justify-content: space-between; gap: 14px; color: var(--smart-muted); }
.tip span i { font-style: normal; color: var(--smart-text); }
.axis-foot { display: flex; flex-wrap: wrap; gap: 12px 18px; padding-top: 10px; border-top: 1px solid var(--ds-surface-overlay); color: var(--smart-muted); font: 10px Consolas, monospace; letter-spacing: .06em; margin-top: 10px; }
.axis-foot i { display: inline-block; width: 10px; height: 10px; margin-right: 5px; border-radius: 2px; vertical-align: -1px; }
.dot-linked { background: var(--smart-primary-strong); border-radius: 50% !important; }
.dot-ok { background: var(--ds-semantic-success); }
.dot-warn { background: var(--ds-semantic-warning); }
.dot-bad { background: var(--ds-semantic-danger); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
</style>
