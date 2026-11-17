<template>
  <div ref="rootEl" class="core-orbit" :class="{ 'core-orbit--loading': loading }">
    <canvas ref="canvasEl" class="core-orbit__canvas" aria-hidden="true" />
    <span class="core-orbit__tag">AI CORE · 决策引擎</span>
  </div>
</template>

<script setup>
/**
 * AgentCoreOrbit — 控制中心「AI 决策核心」HUD 特效
 *
 * 观感：中央呼吸光球 + 旋转进度弧（复盘解决率）+ 双层虚线环 + 轨道节点 + 雷达扫掠，
 * 对齐科幻 HUD 数据核风格；进度弧与当前闭环阶段由真实数据驱动。
 *
 * 降级红线（与 InspectorHeroStream 一致）：
 *  - prefers-reduced-motion / visualMode 非 balanced / 系统降级 → 只画静态一帧；
 *  - 单 rAF 循环、dpr 上限 2、ResizeObserver 自适应、无新增依赖；
 *  - 纯装饰层：只消费聚合数字（progress 0~1、loading），不消费事件 ID。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { visualMode } from '../../visual/visualMode'

const props = defineProps({
  /** 复盘解决率 0~1，驱动进度弧 */
  progress: { type: Number, default: 0 },
  /** 加载中：光球加速脉动 */
  loading: { type: Boolean, default: false }
})

const rootEl = ref(null)
const canvasEl = ref(null)
const width = ref(0)
const height = ref(0)

let frameId = null
let resizeObserver = null
let motionMedia = null
let degradedMedia = null
let reduceHit = false
let degradedHit = false
let phase = 0
let lastTs = null
// 轨道节点相位（确定性分布，避免每帧随机抖动）
const NODES = [0.2, 0.45, 0.72, 0.9]

const isStatic = () => reduceHit || degradedHit || visualMode.value !== 'balanced'

const CYAN = [122, 215, 245]

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

  const cx = w / 2
  const cy = h / 2
  const speed = isStatic() ? 0 : phase * 0.001
  const pulseSpeed = props.loading ? 0.006 : 0.0032
  const breathe = isStatic() ? 0.5 : 0.5 + Math.sin(phase * pulseSpeed) * 0.5

  // HUD 四角括号
  context.strokeStyle = `rgba(${CYAN[0]}, ${CYAN[1]}, ${CYAN[2]}, .4)`
  context.lineWidth = 1
  const m = 6
  const arm = 10
  ;[[m, m, 1, 1], [w - m, m, -1, 1], [m, h - m, 1, -1], [w - m, h - m, -1, -1]].forEach(([x, y, sx, sy]) => {
    context.beginPath()
    context.moveTo(x + sx * arm, y)
    context.lineTo(x, y)
    context.lineTo(x, y + sy * arm)
    context.stroke()
  })

  // 中央光球：径向渐变 + 呼吸
  const coreR = 11 + breathe * 3.5
  const core = context.createRadialGradient(cx, cy, 1, cx, cy, coreR * 2.6)
  core.addColorStop(0, 'rgba(235, 250, 255, .95)')
  core.addColorStop(0.28, `rgba(${CYAN[0]}, ${CYAN[1]}, ${CYAN[2]}, .75)`)
  core.addColorStop(0.6, 'rgba(36, 150, 237, .28)')
  core.addColorStop(1, 'rgba(36, 150, 237, 0)')
  context.fillStyle = core
  context.beginPath()
  context.arc(cx, cy, coreR * 2.6, 0, Math.PI * 2)
  context.fill()
  context.fillStyle = 'rgba(240, 252, 255, .92)'
  context.beginPath()
  context.arc(cx, cy, coreR * 0.42, 0, Math.PI * 2)
  context.fill()

  // 进度弧（复盘解决率）：亮青圆头弧，起点正上方
  const progress = Math.min(1, Math.max(0, Number(props.progress) || 0))
  const rProgress = 26
  context.lineWidth = 3
  context.strokeStyle = 'rgba(122, 215, 245, .16)'
  context.beginPath()
  context.arc(cx, cy, rProgress, 0, Math.PI * 2)
  context.stroke()
  if (progress > 0) {
    context.strokeStyle = `rgba(${CYAN[0]}, ${CYAN[1]}, ${CYAN[2]}, .95)`
    context.lineCap = 'round'
    context.shadowColor = 'rgba(122, 215, 245, .8)'
    context.shadowBlur = 6
    context.beginPath()
    context.arc(cx, cy, rProgress, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * progress)
    context.stroke()
    context.shadowBlur = 0
  }

  // 外层虚线环：慢速旋转
  context.setLineDash([5, 7])
  context.lineWidth = 1
  context.strokeStyle = `rgba(${CYAN[0]}, ${CYAN[1]}, ${CYAN[2]}, .35)`
  context.beginPath()
  context.arc(cx, cy, 38, speed * 0.7, speed * 0.7 + Math.PI * 2)
  context.stroke()
  context.setLineDash([])

  // 稀疏刻度环：反向旋转
  context.strokeStyle = `rgba(${CYAN[0]}, ${CYAN[1]}, ${CYAN[2]}, .22)`
  for (let i = 0; i < 12; i += 1) {
    const angle = -speed * 0.45 + (i / 12) * Math.PI * 2
    const r1 = 46
    const r2 = i % 3 === 0 ? 52 : 49
    context.beginPath()
    context.moveTo(cx + Math.cos(angle) * r1, cy + Math.sin(angle) * r1)
    context.lineTo(cx + Math.cos(angle) * r2, cy + Math.sin(angle) * r2)
    context.stroke()
  }

  // 雷达扫掠线：渐隐拖尾
  const sweepAngle = speed * 1.4
  const sweep = context.createLinearGradient(cx, cy, cx + Math.cos(sweepAngle) * 56, cy + Math.sin(sweepAngle) * 56)
  sweep.addColorStop(0, 'rgba(122, 215, 245, .5)')
  sweep.addColorStop(1, 'rgba(122, 215, 245, 0)')
  context.strokeStyle = sweep
  context.lineWidth = 1.5
  context.beginPath()
  context.moveTo(cx, cy)
  context.lineTo(cx + Math.cos(sweepAngle) * 56, cy + Math.sin(sweepAngle) * 56)
  context.stroke()

  // 轨道节点：绕核运行，微光点 + 到核的细连线
  NODES.forEach((offset, index) => {
    const angle = speed * (0.5 + index * 0.12) + offset * Math.PI * 2
    const r = 38 + (index % 2) * 8
    const x = cx + Math.cos(angle) * r
    const y = cy + Math.sin(angle) * r
    context.strokeStyle = `rgba(${CYAN[0]}, ${CYAN[1]}, ${CYAN[2]}, .12)`
    context.lineWidth = 1
    context.beginPath()
    context.moveTo(cx, cy)
    context.lineTo(x, y)
    context.stroke()
    context.fillStyle = `rgba(${CYAN[0]}, ${CYAN[1]}, ${CYAN[2]}, ${0.45 + Math.sin(phase * 0.004 + index) * 0.3})`
    context.beginPath()
    context.arc(x, y, 2.2, 0, Math.PI * 2)
    context.fill()
  })
}

function tick(timestamp) {
  if (lastTs == null) lastTs = timestamp
  phase += Math.min(64, timestamp - lastTs)
  lastTs = timestamp
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
  const rect = rootEl.value?.getBoundingClientRect()
  width.value = Math.max(160, Math.round(rect?.width || 220))
  height.value = Math.max(110, Math.round(rect?.height || 150))
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
  if (rootEl.value) resizeObserver.observe(rootEl.value)
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
</script>

<style scoped>
.core-orbit {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 120px;
}
.core-orbit__canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.core-orbit__tag {
  position: absolute;
  top: 8px;
  left: 12px;
  color: rgba(122, 215, 245, .6);
  font: 9px var(--font-mono, ui-monospace, monospace);
  letter-spacing: .14em;
}
@media (prefers-reduced-motion: reduce) {
  .core-orbit__canvas { opacity: .7; }
}
</style>
