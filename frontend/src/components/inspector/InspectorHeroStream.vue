<template>
  <canvas ref="canvasEl" class="hero-stream" aria-hidden="true" />
</template>

<script setup>
/**
 * InspectorHeroStream — 纠察中心头部「量化数据流」特效层
 *
 * 观感：横向流光线条（红色系），模拟量化平台行情数据流。
 *
 * 事件绑定（与页面文案「每个粒子对应一条纠察事件」一致）：
 *  - 流光数量与真实纠察事件 1:1（超过 46 条时按时间序均匀抽样）；
 *  - 颜色统一红色系，按严重度区分亮度：PASS → 深红，WARN → 亮红，HIGH → 亮红，CRITICAL → 近白热红；
 *  - 流光 y 坐标按事件时间序均匀分布到轨道带，时间相邻的事件轨迹相邻；
 *  - 无真实事件时画 10 条装饰性兜底流光并叠加明显的红色呼吸效果
 *    （亮度随呼吸脉动、各条错峰，光晕常驻脉动），与真实事件的 1:1 流光明显区分；
 *  - 告警聚合计数（total/warn/high/critical）仍驱动红色边缘呼吸光晕。
 *
 * 降级红线（与 InspectorEventField 一致）：
 *  - prefers-reduced-motion / visualMode 非 balanced / 系统降级 → 只画静态一帧；
 *  - 单 rAF 循环、dpr 上限 2、ResizeObserver 自适应、无新增依赖；
 *  - 只读消费事件列表（severity + 顺序），不输出事件 ID。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { visualMode } from '../../visual/visualMode'

const props = defineProps({
  events: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  warn: { type: Number, default: 0 },
  high: { type: Number, default: 0 },
  critical: { type: Number, default: 0 }
})

const canvasEl = ref(null)
const width = ref(0)
const height = ref(0)

let frameId = null
let resizeObserver = null
let motionMedia = null
let degradedMedia = null
let reduceHit = false
let degradedHit = false
let streaks = []
let fallbackMode = false
let phase = 0
let lastTs = null

// 红色系打底色（深度备选，随机取用）
const RED_COLORS = [
  [248, 81, 73], // 亮红
  [224, 49, 44], // 深红
  [255, 127, 118] // 软红
]
// 严重度 → 流光颜色：统一红色系，越严重越亮（CRITICAL 近白热红最醒目）
const SEVERITY_COLORS = {
  PASS: [[201, 58, 52]], // 深红（通过态最暗）
  WARN: [[248, 81, 73]], // 亮红
  HIGH: [[255, 106, 95]], // 高亮红
  CRITICAL: [[255, 178, 168]] // 近白热红
}
const MAX_STREAKS = 46

const alertRatio = () => {
  const total = Math.max(0, Number(props.total) || 0)
  if (!total) return 0
  const alerts = Math.max(0, (Number(props.warn) || 0) + (Number(props.high) || 0) + (Number(props.critical) || 0))
  return Math.min(1, alerts / total)
}

const isStatic = () => reduceHit || degradedHit || visualMode.value !== 'balanced'

function severityKeyOf(event) {
  const level = String(event?.severity || '').toUpperCase()
  return level === 'WARNING' ? 'WARN' : level
}

function streakFromEvent(event, index, count, initial = false) {
  const palette = SEVERITY_COLORS[severityKeyOf(event)] || RED_COLORS
  const color = palette[(Math.random() * palette.length) | 0]
  const length = 40 + Math.random() * 190
  // y 按事件时间序均匀分带 + 轻微抖动，时间相邻的事件轨迹相邻
  const band = height.value / (count + 1)
  const y = Math.min(
    Math.max(band * (index + 1) + (Math.random() - 0.5) * band * 0.5, 8),
    Math.max(10, height.value - 8)
  )
  return {
    y,
    x: initial ? Math.random() * width.value : -length - Math.random() * 240,
    length,
    speed: 26 + Math.random() * 130,
    color,
    alpha: 0.2 + Math.random() * 0.5,
    width: Math.random() < 0.78 ? 1 : 2
  }
}

/* 装饰性兜底流光：无真实事件时画明显的红色呼吸流光（亮度随呼吸脉动），保证空库时仍有强观感 */
const FALLBACK_COUNT = 10

function fallbackStreak(index, count, initial = false) {
  const color = RED_COLORS[(Math.random() * RED_COLORS.length) | 0]
  const length = 40 + Math.random() * 190
  const band = height.value / (count + 1)
  const y = Math.min(
    Math.max(band * (index + 1) + (Math.random() - 0.5) * band * 0.5, 8),
    Math.max(10, height.value - 8)
  )
  return {
    y,
    x: initial ? Math.random() * width.value : -length - Math.random() * 240,
    length,
    speed: 26 + Math.random() * 130,
    color,
    // 兜底态基础亮度对齐真实事件（0.2+），呼吸调制在 draw 时叠加
    alpha: 0.22 + Math.random() * 0.18,
    width: Math.random() < 0.5 ? 1 : 2,
    breatheOffset: index * 0.9
  }
}

/* 事件列表 → 流光列表（1:1，超上限按时间序均匀抽样；无事件时用装饰性兜底） */
function buildStreaks(initial = false) {
  const events = Array.isArray(props.events) ? props.events : []
  const count = events.length
  fallbackMode = !count
  if (!width.value || !height.value) {
    streaks = []
    return
  }
  if (!count) {
    streaks = Array.from({ length: FALLBACK_COUNT }, (_, i) => fallbackStreak(i, FALLBACK_COUNT, initial))
    return
  }
  const stride = Math.ceil(count / MAX_STREAKS)
  const picked = []
  for (let i = 0; i < count; i += stride) picked.push(events[i])
  streaks = picked.map((event, i) => streakFromEvent(event, i, picked.length, initial))
}

function respawn(streak) {
  // 回收到左侧重进：保持该事件的颜色 / 轨道 / 形态，只重置位置
  return { ...streak, x: -streak.length - Math.random() * 240 }
}

function draw() {
  const canvas = canvasEl.value
  if (!canvas) return
  const context = canvas.getContext('2d')
  if (!context) return

  const dpr = Math.min(2, globalThis.devicePixelRatio || 1)
  const w = width.value
  const h = height.value
  const pixelW = Math.round(w * dpr)
  const pixelH = Math.round(h * dpr)
  if (canvas.width !== pixelW || canvas.height !== pixelH) {
    canvas.width = pixelW
    canvas.height = pixelH
    canvas.style.width = `${w}px`
    canvas.style.height = `${h}px`
  }
  context.setTransform(dpr, 0, 0, dpr, 0, 0)
  context.clearRect(0, 0, w, h)

  // 红色呼吸光晕：兜底态（无事件）常驻明显脉动；有事件时按告警占比驱动
  const ratio = alertRatio()
  if (fallbackMode || ratio > 0) {
    const pulse = isStatic()
      ? 0.5
      : 0.42 + Math.sin(phase * 0.0022) * 0.28
    const strength = fallbackMode
      ? (isStatic() ? 0.16 : 0.18 + Math.sin(phase * 0.0022) * 0.12)
      : 0.3 * ratio * pulse
    const glow = context.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.28, w / 2, h / 2, Math.max(w, h) * 0.62)
    glow.addColorStop(0, 'rgba(248, 81, 73, 0)')
    glow.addColorStop(1, `rgba(248, 81, 73, ${strength.toFixed(3)})`)
    context.fillStyle = glow
    context.fillRect(0, 0, w, h)
  }

  context.lineCap = 'round'
  streaks.forEach((streak, index) => {
    const [r, g, b] = streak.color
    const tail = Math.max(streak.x - streak.length, -streak.length)
    // 兜底态：亮度随呼吸脉动（各条错峰），波谷不低于 0.08 保证始终可见
    const breathe = fallbackMode && !isStatic()
      ? 0.55 + 0.45 * Math.sin(phase * 0.0032 + (streak.breatheOffset ?? index))
      : 1
    const alpha = Math.max(0.08, streak.alpha * breathe)
    const gradient = context.createLinearGradient(tail, 0, streak.x, 0)
    gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0)`)
    gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`)
    context.strokeStyle = gradient
    context.lineWidth = streak.width
    context.beginPath()
    context.moveTo(tail, streak.y)
    context.lineTo(streak.x, streak.y)
    context.stroke()
  })
}

function tick(timestamp) {
  if (lastTs == null) lastTs = timestamp
  const delta = Math.min(64, timestamp - lastTs)
  lastTs = timestamp
  phase += delta
  streaks.forEach((streak, index) => {
    streak.x += streak.speed * (delta / 1000)
    if (streak.x - streak.length > width.value) streaks[index] = respawn(streak)
  })
  draw()
  frameId = requestAnimationFrame(tick)
}

function restart() {
  if (frameId != null) {
    cancelAnimationFrame(frameId)
    frameId = null
  }
  lastTs = null
  if (!canvasEl.value || !width.value) return
  if (isStatic()) draw()
  else frameId = requestAnimationFrame(tick)
}

function measure() {
  const rect = canvasEl.value?.parentElement?.getBoundingClientRect()
  width.value = Math.max(240, Math.round(rect?.width || 640))
  height.value = Math.max(48, Math.round(rect?.height || 220))
  buildStreaks(true)
  restart()
}

onMounted(() => {
  try {
    motionMedia = globalThis.matchMedia('(prefers-reduced-motion: reduce)')
    reduceHit = motionMedia.matches
    motionMedia.addEventListener?.('change', onMotionChange)
    degradedMedia = globalThis.matchMedia('(data-motion-degraded: true)')
    degradedHit = degradedMedia.matches
    degradedMedia.addEventListener?.('change', onDegradedChange)
  } catch {
    /* 能力探测不可用时按完整档位运行 */
  }
  measure()
  resizeObserver = new ResizeObserver(measure)
  if (canvasEl.value?.parentElement) resizeObserver.observe(canvasEl.value.parentElement)
})

function onMotionChange(event) {
  reduceHit = event.matches
  restart()
}
function onDegradedChange(event) {
  degradedHit = event.matches
  restart()
}

onBeforeUnmount(() => {
  if (frameId != null) cancelAnimationFrame(frameId)
  resizeObserver?.disconnect()
  motionMedia?.removeEventListener?.('change', onMotionChange)
  degradedMedia?.removeEventListener?.('change', onDegradedChange)
})

// 真实事件列表变化（刷新 / 切 DEMO）→ 按 1:1 重建流光并立即可见；
// 告警计数变化 → 静态档重绘呼吸光晕，运行中的流光在回收时逐步转红。
watch(() => props.events, () => {
  buildStreaks()
  if (isStatic()) draw()
})
watch(() => [props.total, props.warn, props.high, props.critical], () => {
  if (isStatic()) draw()
})
</script>

<style scoped>
.hero-stream {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  opacity: .9;
}
@media (prefers-reduced-motion: reduce) {
  .hero-stream { opacity: .55; }
}
</style>
