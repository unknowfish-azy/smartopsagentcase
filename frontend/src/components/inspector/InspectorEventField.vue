<template>
  <div ref="rootEl" class="event-field" :class="{ 'event-field--static': isStatic }">
    <span v-if="demo" class="event-field__demo">DEMO · 虚构示例，非真实纠察</span>

    <canvas
      v-show="!isNarrow"
      ref="canvasEl"
      class="event-field__canvas"
      aria-label="纠察事件时间轴"
      @click="onCanvasClick"
      @mousemove="onCanvasMove"
      @mouseleave="hovered = null"
    />
    <div v-if="!points.length && !isNarrow" class="event-field__empty">
      <span class="event-field__empty-dot" aria-hidden="true"></span>
      {{ emptyText }}
    </div>
    <div
      v-if="hovered && !isNarrow"
      class="event-field__tip"
      :style="{ left: `${hovered.x}px`, top: `${hovered.y}px` }"
    >
      <strong>{{ hovered.point.severity }}</strong>
      <span>{{ hovered.point.taskId }}</span>
      <small>{{ formatTime(hovered.point.at) }}</small>
    </div>

    <ul v-if="isNarrow" class="event-field__list">
      <li v-for="point in points" :key="point.id">
        <button type="button" @click="emit('select', point.raw)">
          <i :style="{ background: colorOf(point.severity) }" aria-hidden="true"></i>
          <span>{{ point.severity }}</span>
          <strong>{{ point.taskId }}</strong>
          <small>{{ formatTime(point.at) }}</small>
        </button>
      </li>
      <li v-if="!points.length" class="event-field__list-empty">{{ emptyText }}</li>
    </ul>
  </div>
</template>

<script setup>
/**
 * InspectorEventField — 数据驱动的事件粒子时间轴
 *
 * 设计红线：
 *  - 1 个粒子 = 1 条真实（或明确标注 DEMO 的）纠察事件，绝不凭空生成装饰粒子；
 *  - 粒子 X 由 createdAt/at 决定、Y 由 severity 决定，颜色由等级决定；
 *  - Canvas 单独接降级：prefers-reduced-motion / 三档 visualMode /
 *    data-motion-degraded / 窄屏，命中即出静态帧或退化为列表；
 *  - 粒子上限 120，单帧 rAF，ResizeObserver 自适应，无新增依赖。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { visualMode } from '../../visual/visualMode'

const props = defineProps({
  events: { type: Array, default: () => [] },
  selectedId: { type: [String, Number], default: null },
  demo: { type: Boolean, default: false },
  emptyText: { type: String, default: '等待真实纠察事件接入' },
  maxPoints: { type: Number, default: 120 }
})
const emit = defineEmits(['select'])

const SEVERITIES = ['PASS', 'WARN', 'HIGH', 'CRITICAL']
const COLORS = {
  PASS: '#3fb950',
  WARN: '#d29922',
  HIGH: '#e08a3c',
  CRITICAL: '#f85149',
  INFO: '#58a6ff'
}
const TRACK_COLOR = 'rgba(159, 190, 207, .16)'
const TEXT_COLOR = 'rgba(146, 166, 181, .75)'

const rootEl = ref(null)
const canvasEl = ref(null)
const hovered = ref(null)
const isNarrow = ref(false)
const reduceHit = ref(false)
const degradedHit = ref(false)
const width = ref(0)
const height = ref(0)

let frameId = null
let resizeObserver = null
let motionMedia = null

const isStatic = computed(() =>
  reduceHit.value || degradedHit.value || visualMode.value !== 'balanced' || isNarrow.value
)

function colorOf(severity) {
  return COLORS[String(severity || '').toUpperCase()] || COLORS.INFO
}

function toTimestamp(event) {
  const raw = event.at ?? event.createdAt ?? event.time
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw
  const parsed = Date.parse(raw)
  return Number.isNaN(parsed) ? 0 : parsed
}

function severityOf(event) {
  const value = String(event.severity || 'INFO').toUpperCase()
  return SEVERITIES.includes(value) ? value : 'PASS'
}

const points = computed(() => props.events
  .map(event => ({
    id: event.id,
    at: toTimestamp(event),
    severity: severityOf(event),
    taskId: event.taskId || event.task || 'unknown',
    raw: event
  }))
  .filter(point => point.id != null && point.at > 0)
  .sort((a, b) => a.at - b.at)
  .slice(0, props.maxPoints)
)

const bounds = computed(() => {
  if (!points.value.length) return { min: 0, max: 1 }
  const stamps = points.value.map(point => point.at)
  const min = Math.min(...stamps)
  const max = Math.max(...stamps)
  return max - min < 60000 ? { min: min - 1800000, max: max + 1800000 } : { min, max }
})

function layout() {
  const padX = 62
  const padTop = 24
  const padBottom = 22
  const usableW = Math.max(1, width.value - padX * 2)
  const usableH = Math.max(1, height.value - padTop - padBottom)
  return { padX, padTop, usableW, usableH }
}

function geometryOf(point) {
  const { padX, padTop, usableW, usableH } = layout()
  const ratio = (point.at - bounds.value.min) / (bounds.value.max - bounds.value.min || 1)
  const lane = SEVERITIES.indexOf(point.severity)
  return {
    x: padX + Math.min(1, Math.max(0, ratio)) * usableW,
    y: padTop + ((lane + 0.5) / SEVERITIES.length) * usableH
  }
}

function formatTime(stamp) {
  try {
    return new Date(stamp).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
    })
  } catch {
    return 'Time N/A'
  }
}

function draw(phase = 0) {
  const canvas = canvasEl.value
  if (!canvas || isNarrow.value) return
  const context = canvas.getContext('2d')
  if (!context) return

  const dpr = Math.min(2, globalThis.devicePixelRatio || 1)
  const w = width.value
  const h = height.value
  const pixelW = Math.round(w * dpr)
  const pixelH = Math.round(h * dpr)
  // 只在尺寸变化时重建 backing store，避免 rAF 每帧重新分配显存
  if (canvas.width !== pixelW || canvas.height !== pixelH) {
    canvas.width = pixelW
    canvas.height = pixelH
    canvas.style.width = `${w}px`
    canvas.style.height = `${h}px`
  }
  context.setTransform(dpr, 0, 0, dpr, 0, 0)
  context.clearRect(0, 0, w, h)

  const { padX, padTop, usableW, usableH } = layout()

  // 四条等级轨道
  context.lineWidth = 1
  context.strokeStyle = TRACK_COLOR
  for (let index = 0; index < SEVERITIES.length; index += 1) {
    const y = padTop + ((index + 0.5) / SEVERITIES.length) * usableH
    context.beginPath()
    context.moveTo(padX, y)
    context.lineTo(padX + usableW, y)
    context.stroke()
  }

  // 每条轨道左侧写等级名（右对齐），底部写时间窗起止
  context.font = '11px ui-monospace, monospace'
  context.fillStyle = TEXT_COLOR
  context.textBaseline = 'middle'
  context.textAlign = 'right'
  SEVERITIES.forEach((level, index) => {
    const y = padTop + ((index + 0.5) / SEVERITIES.length) * usableH
    context.fillText(level, padX - 8, y)
  })
  context.textAlign = 'left'
  context.fillText(formatTime(bounds.value.min), padX, h - 10)
  context.textAlign = 'right'
  context.fillText(formatTime(bounds.value.max), padX + usableW, h - 10)
  context.textAlign = 'left'

  // 事件粒子
  points.value.forEach((point, index) => {
    const { x, y } = geometryOf(point)
    const selected = props.selectedId != null && String(point.id) === String(props.selectedId)
    const breathe = isStatic.value ? 0 : Math.sin(phase * 0.0016 + index * 0.7) * 0.7
    const radius = (selected ? 5 : 3.2) + breathe
    context.beginPath()
    context.arc(x, y, Math.max(1.5, radius), 0, Math.PI * 2)
    context.fillStyle = colorOf(point.severity)
    context.globalAlpha = selected ? 1 : 0.82
    context.fill()
    context.globalAlpha = 1
    if (selected) {
      context.beginPath()
      context.arc(x, y, radius + 5, 0, Math.PI * 2)
      context.strokeStyle = colorOf(point.severity)
      context.lineWidth = 1
      context.stroke()
    }
  })
}

function tick(timestamp) {
  draw(timestamp)
  if (!isStatic.value) frameId = requestAnimationFrame(tick)
}

function restart() {
  if (frameId != null) cancelAnimationFrame(frameId)
  frameId = null
  if (isNarrow.value || !canvasEl.value) return
  if (isStatic.value) draw(0)
  else frameId = requestAnimationFrame(tick)
}

function measure() {
  const rect = rootEl.value?.getBoundingClientRect()
  width.value = Math.max(240, Math.round(rect?.width || 640))
  height.value = Math.max(150, Math.round(rect?.height || 220))
  isNarrow.value = globalThis.innerWidth < 768
  nextTick(restart)
}

function hitTest(clientX, clientY) {
  const rect = canvasEl.value?.getBoundingClientRect()
  if (!rect) return null
  const x = clientX - rect.left
  const y = clientY - rect.top
  let best = null
  let bestDist = 12
  points.value.forEach(point => {
    const position = geometryOf(point)
    const dist = Math.hypot(position.x - x, position.y - y)
    if (dist < bestDist) { bestDist = dist; best = { point, ...position } }
  })
  return best
}

function onCanvasClick(event) {
  const hit = hitTest(event.clientX, event.clientY)
  if (hit) emit('select', hit.point.raw)
}

function onCanvasMove(event) {
  const hit = hitTest(event.clientX, event.clientY)
  hovered.value = hit ? { ...hit, x: hit.x + 10, y: Math.max(6, hit.y - 46) } : null
  if (canvasEl.value) canvasEl.value.style.cursor = hit ? 'pointer' : 'default'
}

function onMotionChange(event) { reduceHit.value = event.matches }
function onResize() { measure() }

watch(() => props.events, () => nextTick(restart), { deep: false })
watch(() => props.selectedId, () => { if (isStatic.value) draw(0) })
watch(isStatic, () => restart())

onMounted(() => {
  motionMedia = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)') || null
  reduceHit.value = Boolean(motionMedia?.matches)
  motionMedia?.addEventListener?.('change', onMotionChange)
  degradedHit.value = document.documentElement.getAttribute('data-motion-degraded') === 'true'
  globalThis.addEventListener('resize', onResize)
  if (typeof ResizeObserver !== 'undefined' && rootEl.value) {
    resizeObserver = new ResizeObserver(measure)
    resizeObserver.observe(rootEl.value)
  }
  measure()
})

onBeforeUnmount(() => {
  if (frameId != null) cancelAnimationFrame(frameId)
  resizeObserver?.disconnect()
  motionMedia?.removeEventListener?.('change', onMotionChange)
  globalThis.removeEventListener('resize', onResize)
})
</script>

<style scoped>
.event-field {
  position: relative;
  height: 240px;
  border: 1px solid var(--ds-hairline, rgba(159, 190, 207, .18));
  border-radius: 10px;
  background: var(--ds-color-canvas, #05090d);
  overflow: hidden;
}
.event-field__canvas { position: absolute; inset: 0; display: block; width: 100%; height: 100%; }
@media (max-width: 767px) { .event-field { height: auto; min-height: 220px; } }
.event-field__demo {
  position: absolute;
  top: 8px;
  right: 10px;
  z-index: 2;
  padding: 3px 9px;
  border: 1px solid var(--ds-pill-warning-bg, rgba(210, 153, 34, .3));
  border-radius: 999px;
  color: var(--ds-semantic-warning, #d29922);
  font: 11px var(--font-mono, ui-monospace, monospace);
  letter-spacing: .06em;
  background: var(--ds-surface-overlay, #1b212a);
}
.event-field__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--ds-color-muted, #92a6b5);
  font-size: 13px;
  pointer-events: none;
}
.event-field__empty-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ds-color-primary-strong, #7ad7f5);
}
.event-field--static .event-field__empty-dot { opacity: .6; }
.event-field__tip {
  position: absolute;
  z-index: 3;
  display: grid;
  gap: 2px;
  min-width: 140px;
  padding: 8px 10px;
  border: 1px solid var(--ds-color-border-strong, rgba(159, 190, 207, .34));
  border-radius: 8px;
  background: var(--ds-surface-overlay, #1b212a);
  box-shadow: var(--ds-elevation-2, 0 4px 16px rgba(0, 0, 0, .35));
  font-size: 12px;
  pointer-events: none;
}
.event-field__tip strong { color: var(--ds-color-text, #e8f2f7); font-size: 12px; }
.event-field__tip span { color: var(--ds-color-muted, #92a6b5); }
.event-field__tip small { color: var(--ds-color-muted, #92a6b5); font-family: var(--font-mono, ui-monospace, monospace); }
.event-field__list { list-style: none; margin: 0; padding: 8px; display: grid; gap: 6px; }
.event-field__list button {
  display: grid;
  grid-template-columns: 8px 64px 1fr auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 9px 10px;
  border: 1px solid var(--ds-hairline, rgba(159, 190, 207, .18));
  border-radius: 7px;
  background: var(--ds-surface-raised, #151a21);
  color: var(--ds-color-text, #e8f2f7);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}
.event-field__list button:hover { border-color: var(--ds-color-primary, #2496ed); }
.event-field__list i { width: 8px; height: 8px; border-radius: 50%; }
.event-field__list small { color: var(--ds-color-muted, #92a6b5); font-family: var(--font-mono, ui-monospace, monospace); }
.event-field__list-empty { padding: 24px; text-align: center; color: var(--ds-color-muted, #92a6b5); font-size: 13px; }
@media (prefers-reduced-motion: reduce) { .event-field__tip { box-shadow: none; } }
</style>
