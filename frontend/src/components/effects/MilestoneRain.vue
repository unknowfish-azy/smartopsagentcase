<template>
  <!--
    里程碑庆祝动效（「麻袋装钱」视觉的合规落地）。
    宿主契约：position:relative + overflow:visible（lggc 包的 overflow:hidden 会裁掉画布）；
    画布 aria-hidden + pointer-events:none，庆祝语义由调用方以 role="status" 区域传达。
    mode=funnel：麻袋常驻绘制（袋内储量为 props.fill 的真实进度），active 时播金币入袋；
    mode=rain：全屏金币雨 overlay，active 时播放，结束后清空。
  -->
  <div ref="root" class="milestone-rain" :class="{ 'is-funnel': mode === 'funnel' }" aria-hidden="true">
    <canvas ref="canvas" class="rain-canvas" />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createCoin, createMotes, createRng, createWorld, fadeCoins, liveCoinCount, stepCoin, stepMotes, vesselGeometry } from './milestoneRain.js'

const props = defineProps({
  active: { type: Boolean, default: false },
  mode: { type: String, default: 'funnel' }, // funnel=金币入袋 | rain=全屏金币雨
  count: { type: Number, default: 64 },
  duration: { type: Number, default: 2600 }, // ms；到时长统一淡出，0=不自动淡出
  seed: { type: Number, default: 20261018 },
  fill: { type: Number, default: 0 }, // funnel 常驻储量 0..1（真实进度，非装饰）
  palette: { type: String, default: 'gold' }, // gold=庆祝金 | neon=品牌霓虹
  ambient: { type: Boolean, default: false } // 持续动态演示：待机时袋内微尘上浮 + 扎口结呼吸（纯装饰）
})
const emit = defineEmits(['finished'])

// 受控庆祝金：仅存在于本画布（MASTER.md 单霓虹红线的庆祝例外），不进入状态色/数据色
const palettes = {
  gold: { light: '#FFE9A8', base: '#F5C942', deep: '#C9930A', edge: '#8A6408', glow: 'rgba(245,201,66,0.35)', bagStroke: 'rgba(245,201,66,0.55)', bagFill: 'rgba(245,201,66,0.08)' },
  neon: { light: '#BFEFFF', base: '#2496ED', deep: '#1464A8', edge: '#7AD7F5', glow: 'rgba(36,150,237,0.35)', bagStroke: 'rgba(122,215,245,0.55)', bagFill: 'rgba(36,150,237,0.08)' }
}

const root = ref(null)
const canvas = ref(null)
let ctx = null, world = null, coins = [], rng = createRng(props.seed)
let raf = 0, last = 0, elapsed = 0, frames = 0
let spawned = 0, spawnAcc = 0, faded = false, paused = false, running = false, disposed = false
let motionQuery = null, resizeObserver = null, intersectionObserver = null
let motes = [], ambientRaf = 0, ambientLast = 0, ambientClock = 0, ambientRunning = false

const SPAWN_INTERVAL = 26 // ms/枚
const DPR_CAP = 2

const palette = () => palettes[props.palette] || palettes.gold

// 懒初始化（ModelShareDonut 的教训）：root 不在 DOM 或尺寸为 0 时绝不碰 canvas，
// 避免 init(null) 抛错污染 Vue post flush 队列导致父组件更新全丢。
function ensureContext() {
  if (!root.value || !canvas.value) return false
  const rect = root.value.getBoundingClientRect()
  if (rect.width < 2 || rect.height < 2) return false
  const dpr = Math.min(DPR_CAP, window.devicePixelRatio || 1)
  const w = Math.round(rect.width), h = Math.round(rect.height)
  if (canvas.value.width !== w * dpr || canvas.value.height !== h * dpr) {
    canvas.value.width = w * dpr
    canvas.value.height = h * dpr
  }
  if (!ctx) ctx = canvas.value.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  if (!world || world.width !== w || world.height !== h) {
    const vessel = props.mode === 'funnel' ? vesselGeometry(w, h) : null
    world = createWorld({
      width: w,
      height: h,
      vessel,
      // funnel 脱靶金币直接落出画布底部；rain 模式落在画布下缘
      floorY: props.mode === 'funnel' ? h + 80 : h - 6,
      reducedMotion: motionQuery?.matches === true
    })
    coins = []
    motes = createMotes(createRng(props.seed + 1), 16, w, h)
  }
  return true
}

function bagPath(c, v) {
  const w = v.right - v.left, h = v.floorY - v.topY
  c.beginPath()
  c.moveTo(v.mouthLeft, v.mouthY)
  c.bezierCurveTo(v.left + w * 0.02, v.topY + h * 0.35, v.left, v.topY + h * 0.62, v.left + w * 0.06, v.floorY - h * 0.06)
  c.quadraticCurveTo(v.left + w / 2, v.floorY + h * 0.07, v.right - w * 0.06, v.floorY - h * 0.06)
  c.bezierCurveTo(v.right, v.topY + h * 0.62, v.right - w * 0.02, v.topY + h * 0.35, v.mouthRight, v.mouthY)
  c.closePath()
}

function drawVesselBack(c, v) {
  const p = palette()
  bagPath(c, v)
  const grad = c.createLinearGradient(0, v.topY, 0, v.floorY)
  grad.addColorStop(0, p.bagFill)
  grad.addColorStop(1, 'rgba(5,9,13,0.02)')
  c.fillStyle = grad
  c.fill()
  c.strokeStyle = p.bagStroke
  c.lineWidth = 1.5
  c.stroke()
}

function drawVesselFront(c, v) {
  const p = palette()
  // 正面纱罩：袋内金币像隔着一层布
  bagPath(c, v)
  c.fillStyle = 'rgba(5,9,13,0.22)'
  c.fill()
  c.strokeStyle = p.bagStroke
  c.lineWidth = 1.5
  c.stroke()
  // 扎口：绳带 + 双耳 + 结
  c.fillStyle = p.bagFill
  c.strokeStyle = p.bagStroke
  c.lineWidth = 1
  c.beginPath()
  c.rect(v.mouthLeft - 5, v.mouthY - 2, v.mouthWidth + 10, 10)
  c.fill()
  c.stroke()
  c.beginPath()
  c.moveTo(v.mouthLeft - 5, v.mouthY - 2)
  c.lineTo(v.mouthLeft - 13, v.mouthY - 10)
  c.lineTo(v.mouthLeft + 1, v.mouthY + 3)
  c.closePath()
  c.moveTo(v.mouthRight + 5, v.mouthY - 2)
  c.lineTo(v.mouthRight + 13, v.mouthY - 10)
  c.lineTo(v.mouthRight - 1, v.mouthY + 3)
  c.closePath()
  c.fill()
  c.stroke()
  const knot = (v.mouthLeft + v.mouthRight) / 2
  c.beginPath()
  c.moveTo(knot, v.mouthY - 9)
  c.lineTo(knot + 5, v.mouthY + 1)
  c.lineTo(knot, v.mouthY + 11)
  c.lineTo(knot - 5, v.mouthY + 1)
  c.closePath()
  c.fillStyle = p.base
  c.fill()
  c.stroke()
}

function drawCoin(c, coin) {
  const p = palette()
  const s = coin.size
  c.save()
  c.globalAlpha = coin.alpha
  c.translate(coin.x, coin.y)
  c.rotate(coin.rot)
  if (coins.length <= 48) { c.shadowColor = p.glow; c.shadowBlur = 8 }
  const grad = c.createLinearGradient(-s, -s, s, s)
  grad.addColorStop(0, p.light)
  grad.addColorStop(0.55, p.base)
  grad.addColorStop(1, p.deep)
  c.fillStyle = grad
  // 几何锐利：旋转菱形，不用正圆
  c.beginPath()
  c.moveTo(0, -s)
  c.lineTo(s * 0.78, 0)
  c.lineTo(0, s)
  c.lineTo(-s * 0.78, 0)
  c.closePath()
  c.fill()
  c.strokeStyle = p.edge
  c.lineWidth = 1
  c.stroke()
  if (s >= 10) {
    c.shadowBlur = 0
    c.fillStyle = p.edge
    c.font = `600 ${Math.round(s * 1.05)}px system-ui, sans-serif`
    c.textAlign = 'center'
    c.textBaseline = 'middle'
    c.fillText('¥', 0, 1)
  }
  c.restore()
}

// 常驻储量：按 props.fill 确定性铺满袋内各列（同 seed 同画面，刷新不跳变）
function drawStaticFill(c, v) {
  const fill = Math.max(0, Math.min(1, props.fill))
  if (fill <= 0) return
  const local = createRng(props.seed)
  const columnWidth = v.mouthWidth / v.columns
  for (let column = 0; column < v.columns; column += 1) {
    const jitter = 0.7 + local() * 0.5
    const count = Math.round(v.capacity * fill * jitter)
    for (let k = 0; k < count; k += 1) {
      const size = 10
      drawCoin(c, {
        x: v.mouthLeft + (column + 0.5) * columnWidth + (local() - 0.5) * size * 0.3,
        y: v.floorY - k * size * 1.05 - size * 0.6,
        rot: (column % 2 === 0 ? 1 : -1) * 0.12,
        size,
        alpha: 1
      })
    }
  }
}

// 绘制顺序（funnel）：袋背 → 常驻储量 → 已捕获金币 → 正面纱罩+扎口 → 飞行/落地金币
function drawScene() {
  if (!ctx || !world) return
  ctx.clearRect(0, 0, world.width, world.height)
  if (world.vessel) {
    const v = world.vessel
    drawVesselBack(ctx, v)
    drawStaticFill(ctx, v)
    for (const coin of coins) if (coin.state === 'captured') drawCoin(ctx, coin)
    drawVesselFront(ctx, v)
    for (const coin of coins) if (coin.state !== 'captured') drawCoin(ctx, coin)
  } else {
    for (const coin of coins) drawCoin(ctx, coin)
  }
}

// ── 持续动态演示（ambient）：待机时星尘上浮 + 扎口结呼吸脉冲。纯装饰，不承载任何数据 ──
function drawAmbientOverlay() {
  const p = palette()
  for (const mote of motes) {
    const alpha = 0.28 + Math.sin(mote.phase) * 0.18
    if (alpha <= 0.04) continue
    const x = mote.x + Math.sin(mote.phase) * mote.sway
    ctx.globalAlpha = alpha
    ctx.fillStyle = p.base
    ctx.beginPath()
    ctx.arc(x, mote.y, mote.size, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.globalAlpha = 1
  const v = world.vessel
  if (v) {
    // 扎口结呼吸：静态结之上的脉冲菱形（幅度 ±1.6px）
    const pulse = 4.5 + Math.sin(ambientClock * 2.2) * 1.6
    const kx = (v.mouthLeft + v.mouthRight) / 2
    const ky = v.mouthY + 1
    ctx.globalAlpha = 0.55 + Math.sin(ambientClock * 2.2) * 0.25
    ctx.fillStyle = p.base
    ctx.beginPath()
    ctx.moveTo(kx, ky - pulse)
    ctx.lineTo(kx + pulse * 0.8, ky)
    ctx.lineTo(kx, ky + pulse)
    ctx.lineTo(kx - pulse * 0.8, ky)
    ctx.closePath()
    ctx.fill()
    ctx.globalAlpha = 1
  }
}

function ambientLoop(now) {
  if (!ambientRunning) return
  ambientRaf = requestAnimationFrame(ambientLoop)
  if (paused) { ambientLast = 0; return }
  if (!ambientLast) { ambientLast = now; return }
  const dt = Math.min(0.05, Math.max(0, (now - ambientLast) / 1000)) // 长帧钳制
  ambientLast = now
  ambientClock += dt
  stepMotes(motes, dt, world.height)
  ctx.clearRect(0, 0, world.width, world.height)
  drawScene()
  drawAmbientOverlay()
  frames += 1
}

function startAmbient() {
  if (ambientRunning || disposed || running) return
  if (!ensureContext()) return
  if (world.reducedMotion || motionQuery?.matches) return // 降低动效：只保留静态帧
  ambientRunning = true
  ambientLast = 0
  ambientRaf = requestAnimationFrame(ambientLoop)
}

function stopAmbient() {
  ambientRunning = false
  if (ambientRaf) { cancelAnimationFrame(ambientRaf); ambientRaf = 0 }
  if (!disposed && ensureContext() && world) drawScene() // 停下后回到静态帧（funnel 保留常驻袋）
}

function loop(now) {
  if (!running) return
  raf = requestAnimationFrame(loop)
  if (paused) { last = 0; return }
  if (!last) { last = now; return }
  const dt = Math.min(0.05, Math.max(0, (now - last) / 1000)) // 长帧钳制：防后台标签页恢复时炸穿物理
  last = now
  elapsed += dt * 1000
  if (spawned < props.count) {
    spawnAcc += dt * 1000
    while (spawnAcc >= SPAWN_INTERVAL && spawned < props.count) {
      spawnAcc -= SPAWN_INTERVAL
      coins.push(createCoin(rng, world, props.mode))
      spawned += 1
    }
  }
  if (props.duration > 0 && !faded && elapsed >= props.duration) {
    faded = true
    fadeCoins(coins)
  }
  for (const coin of coins) stepCoin(coin, dt, world)
  drawScene()
  frames += 1
  if (faded && liveCoinCount(coins) === 0) finish()
}

function finish() {
  running = false
  if (raf) { cancelAnimationFrame(raf); raf = 0 }
  emit('finished')
}

// 降低动效：不积分不循环，画一帧「悬浮金币」静态画面（MASTER.md reduced-motion 契约）
function drawReducedFrame() {
  const local = createRng(props.seed)
  const v = world.vessel
  const total = Math.min(props.count, 18)
  coins = Array.from({ length: total }, (_, index) => {
    const coin = createCoin(local, world, props.mode)
    if (v) {
      coin.x = v.mouthLeft + (index / Math.max(1, total - 1)) * v.mouthWidth
      coin.y = v.mouthY - 22 - Math.sin((index / Math.max(1, total - 1)) * Math.PI) * 34
    } else {
      coin.x = world.width * (0.1 + (index / Math.max(1, total - 1)) * 0.8)
      coin.y = world.height * (0.12 + (index % 3) * 0.05)
    }
    coin.state = 'escape' // 静态态：不跑 loop 就不会衰减 life
    coin.alpha = 0.9
    coin.size = 9 + (index % 3) * 2
    return coin
  })
  drawScene()
  frames = 1
}

function start() {
  if (running || disposed) return
  if (!ensureContext()) return
  stopAmbient() // 庆祝播放期间接管画布，ambient 暂停
  if (world.reducedMotion) {
    drawReducedFrame()
    // 降低动效：静态帧即终态。异步发 finished 让调用方收敛状态（同步发会重入 active watch）
    setTimeout(() => { if (!disposed) emit('finished') }, 0)
    return
  }
  running = true
  paused = false
  last = 0
  elapsed = 0
  frames = 0
  spawned = 0
  spawnAcc = 0
  faded = false
  coins = []
  if (world.vessel) world.vessel.pile = new Array(world.vessel.columns).fill(0)
  raf = requestAnimationFrame(loop)
}

function deactivate() {
  running = false
  paused = false
  if (raf) { cancelAnimationFrame(raf); raf = 0 }
  coins = []
  if (ensureContext()) {
    ctx.clearRect(0, 0, world.width, world.height)
    // funnel 保留下常驻袋与真实储量；rain 全清
    if (props.mode === 'funnel') {
      if (world.reducedMotion) drawReducedFrame() // 保持静态终帧，不闪回
      else drawScene()
    }
  }
  // 持续动态演示：庆祝结束后回到 ambient（reduced-motion 下 startAmbient 自会拒绝）
  if (props.ambient && props.mode === 'funnel') startAmbient()
}

function redrawStatic() {
  world = null
  if (!ensureContext()) return
  ctx.clearRect(0, 0, world.width, world.height)
  if (world.reducedMotion) { drawReducedFrame(); return }
  if (props.mode === 'funnel') drawScene()
  if (props.ambient && !ambientRunning) startAmbient()
}

function onVisibility() {
  paused = document.hidden
  last = 0
  ambientLast = 0
}

function onMotionChange() {
  stopAmbient() // 切到降低动效先停 ambient 循环，redrawStatic 走静态帧分支
  if (props.active) { world = null; start() }
  else redrawStatic()
}

// 测试钩子：断言动效确实在跑（帧数/存活/已捕获/ambient 状态）
function debugState() {
  return {
    frames,
    spawned,
    live: liveCoinCount(coins),
    captured: coins.filter(coin => coin.state === 'captured').length,
    running,
    ambient: ambientRunning,
    motes: motes.length,
    mode: props.mode
  }
}

onMounted(() => {
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  motionQuery.addEventListener('change', onMotionChange)
  document.addEventListener('visibilitychange', onVisibility)
  if (root.value) {
    resizeObserver = new ResizeObserver(() => {
      const wasFunnel = props.mode === 'funnel'
      if (!ensureContext()) return
      if (props.active && !running) start() // 容器从 0 尺寸变为可见：补启动
      else if (props.ambient && !ambientRunning && !motionQuery?.matches) startAmbient()
      else if (wasFunnel) { ctx.clearRect(0, 0, world.width, world.height); drawScene() }
    })
    resizeObserver.observe(root.value)
    // 离屏暂停（与 ParticleWhale 的 visibility pause 同思路）：庆祝与 ambient 共用 paused 标志
    intersectionObserver = new IntersectionObserver(entries => {
      paused = !entries[0]?.isIntersecting
      last = 0
      ambientLast = 0
    })
    intersectionObserver.observe(root.value)
  }
  // 初始静态帧：funnel 常驻袋（rain 模式留空画布）
  if (props.mode === 'funnel') redrawStatic()
  // 测试钩子：仅 dev 暴露（生产构建不含），供浏览器测试断言捕获/帧数
  if (import.meta.env.DEV) window.__milestoneRain = debugState
})

watch(() => props.active, active => {
  if (active) start()
  else deactivate()
}, { flush: 'post' })

watch([() => props.mode, () => props.fill, () => props.palette, () => props.seed], () => {
  if (props.active) { world = null; start() }
  else redrawStatic()
}, { flush: 'post' })

// 键位切换：暂停/恢复持续动态演示（庆祝播放期间由 start/deactivate 接管）
watch(() => props.ambient, on => {
  if (props.active || disposed) return
  if (on) startAmbient()
  else stopAmbient()
}, { flush: 'post' })

onBeforeUnmount(() => {
  disposed = true
  running = false
  stopAmbient()
  if (raf) { cancelAnimationFrame(raf); raf = 0 }
  resizeObserver?.disconnect()
  intersectionObserver?.disconnect()
  motionQuery?.removeEventListener('change', onMotionChange)
  document.removeEventListener('visibilitychange', onVisibility)
  if (import.meta.env.DEV) delete window.__milestoneRain
  ctx = null
  world = null
  coins = []
  motes = []
})

// 测试钩子（dev only）：供浏览器测试断言捕获/帧数；defineExpose 供父组件按需调用
defineExpose({ debugState })
</script>

<style scoped>
.milestone-rain { position: absolute; inset: 0; pointer-events: none; }
.rain-canvas { display: block; width: 100%; height: 100%; }
</style>
