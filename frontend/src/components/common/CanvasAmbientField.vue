<template>
  <canvas ref="canvas" class="canvas-ambient-field" aria-hidden="true" />
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getGlobalFluidField } from './organismMotion.js'
import { observeCanvasTheme, readCanvasPalette } from './canvasTheme.js'
import { visualMode } from '../../visual/visualMode.js'

const canvas = ref(null)
let dispose = () => {}

onMounted(() => {
  const element = canvas.value
  const context = element.getContext('2d', { alpha: true })
  if (!context) return
  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  const reducedMotion = () => reducedQuery.matches || visualMode.value === 'reduced-motion'
  const stars = Array.from({ length: window.innerWidth < 768 ? 70 : 130 }, (_, index) => ({
    x: ((Math.sin(index * 12.9898) * 43758.5453) % 1 + 1) % 1,
    y: ((Math.sin(index * 78.233 + 2) * 43758.5453) % 1 + 1) % 1,
    size: .5 + Math.abs(Math.sin(index * 4.17)) * 1.6,
    phase: index * .83
  }))
  let palette = readCanvasPalette()
  let width = 1
  let height = 1
  let pixelRatio = 1
  let frame = 0
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
    stars.forEach(star => {
      const fluid = getGlobalFluidField(star.x * 4, star.y * 3, time, star.phase)
      const x = (star.x + fluid.x * .012) * width
      const y = (star.y + fluid.y * .012) * height
      const pulse = reducedMotion() ? .65 : .52 + Math.sin(time * .001 + star.phase) * .22
      context.globalAlpha = Math.max(.12, pulse)
      context.fillStyle = star.size > 1.6 ? palette.effectStrong : palette.effectStar
      context.beginPath()
      context.arc(x, y, star.size, 0, Math.PI * 2)
      context.fill()
    })
    context.globalAlpha = 1
  }

  const render = time => {
    if (visible && !document.hidden && !reducedMotion()) {
      draw(time)
      frame = requestAnimationFrame(render)
    } else draw()
  }
  const syncMotion = () => {
    cancelAnimationFrame(frame)
    if (visible && !document.hidden && !reducedMotion()) frame = requestAnimationFrame(render)
    else draw()
  }
  const onTheme = nextPalette => { palette = nextPalette; draw() }
  const onVisibility = () => { visible = !document.hidden; syncMotion() }
  const stopTheme = observeCanvasTheme(onTheme)
  const stopMode = watch(visualMode, syncMotion)

  resize()
  syncMotion()
  window.addEventListener('resize', resize)
  document.addEventListener('visibilitychange', onVisibility)
  reducedQuery.addEventListener?.('change', syncMotion)
  dispose = () => {
    cancelAnimationFrame(frame)
    stopTheme()
    stopMode()
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
