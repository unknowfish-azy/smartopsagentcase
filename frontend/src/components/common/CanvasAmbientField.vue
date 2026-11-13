<template>
  <canvas ref="canvas" class="canvas-ambient-field" aria-hidden="true" />
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getGlobalFluidField } from './organismMotion.js'
import { observeCanvasTheme, readCanvasPalette } from './canvasTheme.js'
import { visualMode } from '../../visual/visualMode.js'
import { subscribe } from '../../visual/motionScheduler.js'

defineProps({
  /** 从哪个 DOM 元素读 Canvas 色板变量；默认 document.documentElement。
   *  允许登录页注入启佑风格的局部 --smart-* 令牌而不影响控制台。 */
  paletteRoot: { type: Object, default: null },
  /** 星星数量乘数（默认 1，即 70/130 颗）。启佑登录页可用 1.6 增密。 */
  starMultiplier: { type: Number, default: 1 },
  /** 是否启用粒子间连线网络（经典 particle-network 效果，启佑登录页启用）。 */
  connectParticles: { type: Boolean, default: false },
  /** 连线最大距离（像素），connectParticles 为 true 时生效。 */
  connectMaxDist: { type: Number, default: 120 },
})

const canvas = ref(null)
let dispose = () => {}

onMounted(() => {
  const element = canvas.value
  const context = element.getContext('2d', { alpha: true })
  if (!context) return
  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  const reducedMotion = () => reducedQuery.matches || visualMode.value === 'reduced-motion'
  const baseCount = window.innerWidth < 768 ? 70 : 130
  const stars = Array.from({ length: Math.round(baseCount * starMultiplier.value) }, (_, index) => ({
    x: ((Math.sin(index * 12.9898) * 43758.5453) % 1 + 1) % 1,
    y: ((Math.sin(index * 78.233 + 2) * 43758.5453) % 1 + 1) % 1,
    size: .5 + Math.abs(Math.sin(index * 4.17)) * 1.6,
    phase: index * .83
  }))
  const root = paletteRoot.value || document.documentElement
  let palette = readCanvasPalette(root)
  let width = 1
  let height = 1
  let pixelRatio = 1
  let visible = !document.hidden

  const resize = () => {
    const bounds = element.getBoundingClientRect()
    width = Math.max(1, bounds.width)
    height = Math.max(1, bounds.height)
    pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5)
    element.width = Math.round(width * pixelRatio)
    element.height = Math.round(height * pixelRatio)
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
    draw()
  }

  const draw = (time = 0) => {
    element.dataset.effectTheme = palette.theme
    element.dataset.effectColor = palette.effectStrong
    context.clearRect(0, 0, width, height)
    const gradient = context.createLinearGradient(0, 0, width, height)
    gradient.addColorStop(0, palette.background)
    gradient.addColorStop(.55, palette.surface)
    gradient.addColorStop(1, palette.background)
    context.fillStyle = gradient
    context.fillRect(0, 0, width, height)
    // 计算每颗星的当前像素坐标（复用 fluid drift 逻辑）
    const positions = stars.map(star => {
      const fluid = getGlobalFluidField(star.x * 4, star.y * 3, time, star.phase)
      return {
        px: (star.x + fluid.x * .012) * width,
        py: (star.y + fluid.y * .012) * height,
        size: star.size,
        phase: star.phase,
      }
    })
    // 粒子间连线网络（启佑风格增强）
    if (connectParticles.value) {
      const maxDist = connectMaxDist.value
      const maxDist2 = maxDist * maxDist
      context.lineCap = 'round'
      for (let i = 0; i < positions.length; i++) {
        const a = positions[i]
        for (let j = i + 1; j < positions.length; j++) {
          const b = positions[j]
          const dx = a.px - b.px
          const dy = a.py - b.py
          const dist2 = dx * dx + dy * dy
          if (dist2 < maxDist2) {
            const dist = Math.sqrt(dist2)
            const alpha = (1 - dist / maxDist) * .22
            context.globalAlpha = alpha
            context.strokeStyle = palette.effectStrong
            context.lineWidth = .5
            context.beginPath()
            context.moveTo(a.px, a.py)
            context.lineTo(b.px, b.py)
            context.stroke()
          }
        }
      }
    }
    // 画星星（在连线之上）
    positions.forEach(pos => {
      const pulse = reducedMotion() ? .65 : .52 + Math.sin(time * .001 + pos.phase) * .22
      context.globalAlpha = Math.max(.12, pulse)
      context.fillStyle = pos.size > 1.6 ? palette.effectStrong : palette.effectStar
      context.beginPath()
      context.arc(pos.px, pos.py, pos.size, 0, Math.PI * 2)
      context.fill()
    })
    context.globalAlpha = 1
  }

  // P3：不再自建 rAF 循环，改由全页共享调度器统一驱动（30fps，离屏自动暂停）。
  const loopId = `ambient-field-${Math.random().toString(36).slice(2, 8)}`
  let unsubscribeLoop = () => {}
  const syncMotion = () => {
    unsubscribeLoop()
    unsubscribeLoop = () => {}
    if (visible && !document.hidden && !reducedMotion()) {
      unsubscribeLoop = subscribe((_dt, now) => draw(now), { fps: 30, id: loopId })
    } else draw()
  }
  // 主题变化始终监听 documentElement（data-theme 在 html 上），但色板从 paletteRoot 读取。
  const onTheme = () => { palette = readCanvasPalette(root); draw() }
  const onVisibility = () => { visible = !document.hidden; syncMotion() }
  const stopTheme = observeCanvasTheme(onTheme)
  const stopMode = watch(visualMode, syncMotion)
  // paletteRoot 变化时（如登录页从启佑风格切回默认）手动重读色板
  const stopRoot = watch(paletteRoot, nextRoot => {
    palette = readCanvasPalette(nextRoot || document.documentElement)
    draw()
  })

  resize()
  syncMotion()
  window.addEventListener('resize', resize)
  document.addEventListener('visibilitychange', onVisibility)
  reducedQuery.addEventListener?.('change', syncMotion)
  dispose = () => {
    unsubscribeLoop()
    stopTheme()
    stopMode()
    stopRoot?.()
    window.removeEventListener('resize', resize)
    document.removeEventListener('visibilitychange', onVisibility)
    reducedQuery.removeEventListener?.('change', syncMotion)
  }
})

onBeforeUnmount(() => dispose())
</script>

<style scoped>
.canvas-ambient-field { position: fixed; z-index: 0; inset: 0; width: 100%; height: 100%; pointer-events: none; opacity: .92; }
:global([data-theme='light'] .canvas-ambient-field) { opacity: .7; }
@media (prefers-reduced-motion: reduce) { .canvas-ambient-field { opacity: .78; } }
</style>
