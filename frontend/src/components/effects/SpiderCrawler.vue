<template>
  <!--
    蜘蛛巡网动效（哨兵 CRAWLER 面板的氛围层）。
    宿主契约：stage 给 position:relative + 确定高度；画布 absolute 铺满 stage，不越界不裁切。
    画布 aria-hidden + pointer-events:none；语义由宿主以文字说明（蜘蛛 = 哨兵巡检意象，不承载实时数据）。
    常驻循环动效：可见即爬行，离屏/切后台暂停；reduced-motion 只画静态网 + 静止蜘蛛。
  -->
  <div ref="root" class="spider-crawler" aria-hidden="true">
    <canvas ref="canvas" class="crawler-canvas" />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { createRng, createSpider, createWeb, restPose, stepSpider } from './spiderCrawler.js'

const props = defineProps({
  seed: { type: Number, default: 42 },
  speed: { type: Number, default: 1 } // 速度倍率（引擎基准 34px/s）
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

const DPR_CAP = 2

// 懒初始化（ModelShareDonut / MilestoneRain 同款教训）：root 不在 DOM 或尺寸为 0 时绝不碰 canvas，
// 避免 init(null) 抛错污染 Vue post flush 队列。
function ensureContext() {
  if (!root.value || !canvas.value) return false
  const rect = root.value.getBoundingClientRect()
  if (rect.width < 40 || rect.height < 40) return false
  const dpr = Math.min(DPR_CAP, window.devicePixelRatio || 1)
  const w = Math.round(rect.width), h = Math.round(rect.height)
  if (canvas.value.width !== w * dpr || canvas.value.height !== h * dpr) {
    canvas.value.width = w * dpr
    canvas.value.height = h * dpr
  }
  if (!ctx) ctx = canvas.value.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  if (!web || web.width !== w || web.height !== h) {
    web = createWeb({ width: w, height: h, seed: props.seed })
    rng = createRng(props.seed * 31 + 7)
    // 大网蜘蛛等比放大：参考图里蜘蛛占网径约 1/4，缩放系数随网径自适应（上限 2.6 防失控）
    const scale = Math.max(1, Math.min(2.6, web.maxRadius / 60))
    spider = createSpider(web, rng, scale)
  }
  return true
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
  // 节点：小菱形（几何锐利），中心略大
  for (const [key, x] of web.nodeX) {
    const y = web.nodeY.get(key)
    const size = 2.2
    ctx.fillStyle = COLORS.node
    ctx.beginPath()
    ctx.moveTo(x, y - size)
    ctx.lineTo(x + size, y)
    ctx.lineTo(x, y + size)
    ctx.lineTo(x - size, y)
    ctx.closePath()
    ctx.fill()
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
  // 腿：髋 → 膝（中点外抬） → 足，两段折线保持节肢感
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
    // 足端小点：踩在网线上的锚定感
    ctx.fillStyle = COLORS.node
    const fs = Math.max(1.4, 1 * k)
    ctx.fillRect(leg.footX - fs / 2, leg.footY - fs / 2, fs, fs)
  }
  // 躯干：头胸（前） + 腹部（后），沿行进方向的梭形
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
  // 腹部（后端，较大菱形）
  ctx.beginPath()
  ctx.moveTo(-2 * k, -4.5 * k)
  ctx.lineTo(-9 * k, 0)
  ctx.lineTo(-2 * k, 4.5 * k)
  ctx.lineTo(1 * k, 0)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()
  // 头胸（前端，较小）
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
  const dt = Math.min(0.05, Math.max(0, (now - last) / 1000)) // 长帧钳制
  last = now
  stepSpider(spider, web, dt * props.speed, rng)
  drawScene()
  frames += 1
}

// 降低动效：静态网 + 静止蜘蛛（MASTER.md reduced-motion 契约）
function drawReducedFrame() {
  restPose(spider, web)
  drawScene()
  frames = 1
}

function start() {
  if (running || disposed) return
  if (!ensureContext()) return
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
  if (motionQuery?.matches) { stop(); if (ensureContext()) drawReducedFrame() }
  else { stop(); start() }
}

// 测试钩子：断言动效确实在跑（帧数/位置推进/迈步中的腿数）
function debugState() {
  return {
    frames,
    running,
    paused,
    bodyX: spider ? Math.round(spider.bodyX * 10) / 10 : 0,
    bodyY: spider ? Math.round(spider.bodyY * 10) / 10 : 0,
    segments: web ? web.segments.length : 0,
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
      if (!ensureContext()) return
      if (!running && !motionQuery?.matches) start() // 容器从 0 尺寸变为可见：补启动
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
