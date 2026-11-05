<template>
  <!--
    蜘蛛巡网动效（哨兵 CRAWLER 面板）。
    宿主契约：stage 给 position:relative + 确定高度；画布 absolute 铺满 stage，不越界不裁切。
    画布 aria-hidden + pointer-events:none；语义由宿主以文字 + 图例说明。

    与现实数据的绑定（区别于纯装饰）：
      - :nodes 传入真实哨兵任务（{id,status,lastSeenAt,enabled}），每个任务 = 外圈一个网节点，
        颜色由采集状态决定（青=在线 / 红=离线 / 橙=异常 / 灰=缺连接）；
      - 蜘蛛会趋近「最近一次采样」的任务节点并脉冲高亮，反映真实采集活动；
      - :active-id 传入表格 hover 的任务 id：优先成为脉冲 + 巡访目标，并在网图里画稳态高亮环，
        实现「表格 ↔ 网图」联动（悬停某行，网里对应节点亮起，蜘蛛走去那一点）；
      - 无任务 / 后端未接入时退化为示意网（无任务节点、随机巡游），不伪造数据。
    常驻循环动效：可见即爬行，离屏/切后台暂停；reduced-motion 只画静态网 + 静止蜘蛛。
  -->
  <div ref="root" class="spider-crawler" aria-hidden="true">
    <canvas ref="canvas" class="crawler-canvas" />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createRng, createSpider, createWeb, restPose, stepSpider, STATUS_COLORS, pickTargetTaskKey } from './spiderCrawler.js'

const props = defineProps({
  seed: { type: Number, default: 42 },
  speed: { type: Number, default: 1 }, // 速度倍率（引擎基准 34px/s）
  /** 真实哨兵任务节点：{ id, status, lastSeenAt, enabled }，空数组 = 示意网 */
  nodes: { type: Array, default: () => [] },
  /** 'ready' | 'unavailable' | 'unknown' —— 决定是否有真实节点可画 */
  status: { type: String, default: 'unknown' },
  /** 表格 hover 的任务 id：优先成为脉冲 + 巡访目标，实现"表格 ↔ 网图"联动高亮 */
  activeId: { type: String, default: null }
})

// 单霓虹青（MASTER.md）；蜘蛛亮青为焦点色，网线低透明度退后
const COLORS = {
  web: 'rgba(122, 215, 245, 0.26)',
  webInner: 'rgba(122, 215, 245, 0.14)',
  node: 'rgba(122, 215, 245, 0.55)',
  nodeCore: '#7AD7F5',
  leg: 'rgba(191, 239, 255, 0.85)',
  legStepping: '#BFEFFF',
  bodyEdge: 'rgba(122, 215, 245, 0.9)',
  bodyFill0: '#BFEFFF',
  bodyFill1: '#2496ED',
  bodyFill2: '#0D3A5E',
  glow: 'rgba(36, 150, 237, 0.45)'
}

const root = ref(null)
const canvas = ref(null)
let ctx = null, web = null, spider = null, rng = null
let raf = 0, last = 0, frames = 0, paused = false, running = false, disposed = false
let motionQuery = null, resizeObserver = null, intersectionObserver = null

const targetNodeKey = ref(null)
const activeNodeKey = ref(null)
const taskSignature = ref('')
const DPR_CAP = 2

// 当前巡访目标：activeId（表格联动）优先，否则取最近一次采样的真实任务节点。
// 抽成纯函数（pickTargetTaskKey）便于单测，且不依赖组件内部状态。
function computeTargetKey() {
  return activeNodeKey.value || pickTargetTaskKey(web, props.nodes, null)
}

// 把真实任务的最新状态写回网节点（不改几何）：轮询刷新时蜘蛛平滑续走，不瞬移回原点
function syncTaskStatus() {
  if (!web || !web.taskNodeKey) return
  for (const n of (props.nodes || [])) {
    const key = web.taskNodeKey.get(n.id)
    if (key == null) continue
    const task = web.webTasks.get(key)
    if (task) {
      task.status = n.status
      task.lastSeenAt = n.lastSeenAt
      task.enabled = n.enabled
    }
  }
  targetNodeKey.value = computeTargetKey()
}

function taskSig() {
  return (props.nodes || []).map(n => n.id).join('|')
}

// 仅在任务 id 集合 / 数量变化时重建几何；其余情况原地更新状态，避免蜘蛛跳变
function maybeRebuild() {
  const sig = taskSig()
  if (sig !== taskSignature.value) {
    taskSignature.value = sig
    if (!rebuildWeb()) return
  } else {
    syncTaskStatus()
  }
  if (!running && !motionQuery?.matches) start()
  else if (motionQuery?.matches) drawReducedFrame()
  else drawScene()
}

// 重建蛛网 + 蜘蛛（按当前尺寸与真实任务）。返回是否成功（容器无尺寸则 false）。
function rebuildWeb() {
  if (!root.value || !canvas.value) return false
  const rect = root.value.getBoundingClientRect()
  if (rect.width < 40 || rect.height < 40) return false
  const dpr = Math.min(DPR_CAP, window.devicePixelRatio || 1)
  const w = Math.round(rect.width)
  const h = Math.round(rect.height)
  if (canvas.value.width !== w * dpr || canvas.value.height !== h * dpr) {
    canvas.value.width = w * dpr
    canvas.value.height = h * dpr
  }
  if (!ctx) ctx = canvas.value.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  web = createWeb({ width: w, height: h, seed: props.seed, tasks: props.nodes })
  rng = createRng(props.seed * 31 + 7)
  const scale = Math.max(1, Math.min(2.6, web.maxRadius / 60))
  spider = createSpider(web, rng, scale)
  targetNodeKey.value = computeTargetKey()
  return true
}

function drawNode(x, y, size, fill) {
  ctx.fillStyle = fill
  ctx.beginPath()
  ctx.moveTo(x, y - size)
  ctx.lineTo(x + size, y)
  ctx.lineTo(x, y + size)
  ctx.lineTo(x - size, y)
  ctx.closePath()
  ctx.fill()
}

// 脉冲环：随 pulsePhase 由内向外扩散并淡出，标记「正在/刚采集」的真实节点
function drawPulse(x, y, col) {
  const phase = ((spider.pulsePhase || 0) % 1.6) / 1.6
  const radius = 4 + phase * 16
  const alpha = 1 - phase
  ctx.save()
  ctx.globalAlpha = alpha * 0.9
  ctx.strokeStyle = col
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.arc(x, y, radius, 0, Math.PI * 2)
  ctx.stroke()
  ctx.restore()
}

// 联动高亮环：表格 hover 对应的节点，画一圈 steady 亮环，强调"表格 ↔ 网图"的对位关系
function drawActiveRing(x, y, col) {
  ctx.save()
  ctx.globalAlpha = 0.95
  ctx.strokeStyle = '#FFFFFF'
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.arc(x, y, 9, 0, Math.PI * 2)
  ctx.stroke()
  ctx.globalAlpha = 0.5
  ctx.strokeStyle = col
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.arc(x, y, 12, 0, Math.PI * 2)
  ctx.stroke()
  ctx.restore()
}

function drawWeb() {
  ctx.lineWidth = 1
  for (const seg of web.segments) {
    const nearCenter = Math.hypot((seg.ax + seg.bx) / 2 - web.cx, (seg.ay + seg.by) / 2 - web.cy) < web.maxRadius * 0.4
    ctx.strokeStyle = nearCenter ? COLORS.webInner : COLORS.web
    ctx.beginPath()
    ctx.moveTo(seg.ax, seg.ay)
    ctx.lineTo(seg.bx, seg.by)
    ctx.stroke()
  }
  // 节点：真实任务节点按状态着色；装饰节点低透明退后；目标节点加脉冲环
  for (const [key, x] of web.nodeX) {
    const y = web.nodeY.get(key)
    const task = web.webTasks.get(key)
    if (task) {
      const col = STATUS_COLORS[task.status] || STATUS_COLORS.none
      const isActive = key === activeNodeKey.value
      const isTarget = key === targetNodeKey.value
      drawNode(x, y, isActive ? 4.8 : 3.4, col)
      if (isActive) drawActiveRing(x, y, col)
      if (isTarget) drawPulse(x, y, col)
    } else {
      drawNode(x, y, 2.2, COLORS.node)
    }
  }
  const cs = 3.2
  ctx.fillStyle = COLORS.nodeCore
  ctx.beginPath()
  ctx.moveTo(web.cx, web.cy - cs)
  ctx.lineTo(web.cx + cs, web.cy)
  ctx.lineTo(web.cx, web.cy + cs)
  ctx.lineTo(web.cx - cs, web.cy)
  ctx.closePath()
  ctx.fill()
}

function drawSpider() {
  const s = spider
  const k = s.scale || 1
  const bodyY = s.bodyY + s.bob
  for (const leg of s.legs) {
    const hx = s.bodyX + Math.cos(s.heading + Math.PI / 2 * leg.side) * leg.hipDist * 0.4
    const hy = bodyY + Math.sin(s.heading + Math.PI / 2 * leg.side) * leg.hipDist * 0.4
    const mx = (hx + leg.footX) / 2 + Math.cos(s.heading + Math.PI / 2 * leg.side) * 4 * k
    const my = (hy + leg.footY) / 2 + Math.sin(s.heading + Math.PI / 2 * leg.side) * 4 * k
    ctx.strokeStyle = leg.stepping ? COLORS.legStepping : COLORS.leg
    ctx.lineWidth = Math.max(1, k * 0.9)
    ctx.beginPath()
    ctx.moveTo(hx, hy)
    ctx.lineTo(mx, my)
    ctx.lineTo(leg.footX, leg.footY)
    ctx.stroke()
    ctx.fillStyle = COLORS.node
    const fs = Math.max(1.4, 1 * k)
    ctx.fillRect(leg.footX - fs / 2, leg.footY - fs / 2, fs, fs)
  }
  ctx.save()
  ctx.translate(s.bodyX, bodyY)
  ctx.rotate(s.heading)
  ctx.shadowColor = COLORS.glow
  ctx.shadowBlur = 10 * k
  const grad = ctx.createLinearGradient(-9 * k, 0, 11 * k, 0)
  grad.addColorStop(0, COLORS.bodyFill2)
  grad.addColorStop(0.55, COLORS.bodyFill1)
  grad.addColorStop(1, COLORS.bodyFill0)
  ctx.fillStyle = grad
  ctx.strokeStyle = COLORS.bodyEdge
  ctx.lineWidth = Math.max(1, k * 0.8)
  ctx.beginPath()
  ctx.moveTo(-2 * k, -4.5 * k)
  ctx.lineTo(-9 * k, 0)
  ctx.lineTo(-2 * k, 4.5 * k)
  ctx.lineTo(1 * k, 0)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()
  ctx.beginPath()
  ctx.moveTo(4 * k, -3 * k)
  ctx.lineTo(10 * k, 0)
  ctx.lineTo(4 * k, 3 * k)
  ctx.lineTo(1.5 * k, 0)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()
  ctx.restore()
}

function drawScene() {
  if (!ctx || !web) return
  ctx.clearRect(0, 0, web.width, web.height)
  drawWeb()
  drawSpider()
}

function loop(now) {
  if (!running) return
  raf = requestAnimationFrame(loop)
  if (paused) { last = 0; return }
  if (!last) { last = now; return }
  const dt = Math.min(0.05, Math.max(0, (now - last) / 1000))
  last = now
  stepSpider(spider, web, dt * props.speed, rng, targetNodeKey.value)
  drawScene()
  frames += 1
}

function drawReducedFrame() {
  restPose(spider, web)
  drawScene()
  frames = 1
}

function start() {
  if (running || disposed) return
  if (!rebuildWeb()) return
  if (motionQuery?.matches) { drawReducedFrame(); return }
  running = true
  paused = false
  last = 0
  raf = requestAnimationFrame(loop)
}

function stop() {
  running = false
  paused = false
  if (raf) { cancelAnimationFrame(raf); raf = 0 }
}

function onVisibility() {
  if (!running) return
  paused = document.hidden
  last = 0
}

function onMotionChange() {
  if (motionQuery?.matches) { stop(); if (rebuildWeb()) drawReducedFrame() }
  else { stop(); start() }
}

// 真实任务变化：仅 id 集合/数量变化才重建几何；否则原地更新状态（蜘蛛平滑续走）。
// 轮询刷新（状态翻转 / 新采样）触发此处，不会让蜘蛛跳回原点。
watch(() => props.nodes, maybeRebuild, { deep: true })

// 表格 hover 联动：activeId 优先成为脉冲 + 巡访目标，并在网图里画稳态高亮环
watch(() => props.activeId, id => {
  activeNodeKey.value = (id != null && web && web.taskNodeKey && web.taskNodeKey.has(id))
    ? web.taskNodeKey.get(id)
    : null
  targetNodeKey.value = computeTargetKey()
  if (!running && web) {
    if (motionQuery?.matches) drawReducedFrame()
    else drawScene()
  }
})

// 测试钩子：断言动效确实在跑（帧数/位置推进/迈步中的腿数）
function debugState() {
  return {
    frames,
    running,
    paused,
    bodyX: spider ? Math.round(spider.bodyX * 10) / 10 : 0,
    bodyY: spider ? Math.round(spider.bodyY * 10) / 10 : 0,
    segments: web ? web.segments.length : 0,
    nodeCount: web ? web.taskCount : 0,
    hasData: !!(web && web.taskCount > 0),
    status: props.status,
    targetKey: targetNodeKey.value,
    activeKey: activeNodeKey.value,
    stepping: spider ? spider.legs.filter(leg => leg.stepping).length : 0,
    reducedMotion: motionQuery?.matches === true
  }
}

onMounted(() => {
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  motionQuery.addEventListener('change', onMotionChange)
  document.addEventListener('visibilitychange', onVisibility)
  if (root.value) {
    resizeObserver = new ResizeObserver(() => {
      if (!rebuildWeb()) return
      if (!running && !motionQuery?.matches) start()
      else if (motionQuery?.matches) drawReducedFrame()
      else drawScene()
    })
    resizeObserver.observe(root.value)
    intersectionObserver = new IntersectionObserver(entries => {
      if (!running) return
      paused = !entries[0]?.isIntersecting
      last = 0
    })
    intersectionObserver.observe(root.value)
  }
  start()
  if (import.meta.env.DEV) window.__spiderCrawler = debugState
})

onBeforeUnmount(() => {
  disposed = true
  stop()
  resizeObserver?.disconnect()
  intersectionObserver?.disconnect()
  motionQuery?.removeEventListener('change', onMotionChange)
  document.removeEventListener('visibilitychange', onVisibility)
  if (import.meta.env.DEV) delete window.__spiderCrawler
  ctx = null
  web = null
  spider = null
})

defineExpose({ debugState })
</script>

<style scoped>
.spider-crawler { position: absolute; inset: 0; pointer-events: none; }
.crawler-canvas { display: block; width: 100%; height: 100%; }
</style>
