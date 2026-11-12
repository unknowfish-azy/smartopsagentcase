<template>
  <canvas ref="canvas" class="canvas-whale" :class="[`canvas-whale--${placement}`, `canvas-whale--${state}`]" aria-hidden="true" />
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getGlobalFluidField, getWhaleBreath, getWhaleSwimMotion } from './organismMotion.js'
import { createWhalePointCloud } from './whaleShape.js'
import { observeCanvasTheme, readCanvasPalette } from './canvasTheme.js'
import { visualMode } from '../../visual/visualMode.js'
import { subscribe } from '../../visual/motionScheduler.js'

const props = defineProps({
  state: { type: String, default: 'idle' },
  placement: { type: String, default: 'home' },
  isolated: { type: Boolean, default: false }
})

const canvas = ref(null)
let dispose = () => {}
let redraw = () => {}

function resolveQuality(width, reducedMotion) {
  if (reducedMotion) return { count: 1500, animate: false }
  if (width >= 1440) return { count: 4600, animate: true }
  if (width >= 768) return { count: 3200, animate: true }
  return { count: 1700, animate: true }
}

function tintColor(context, color, alpha) {
  context.globalAlpha = alpha
  context.fillStyle = color
}

onMounted(() => {
  const element = canvas.value
  const context = element.getContext('2d', { alpha: true })
  if (!context) return

  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  const reducedMotion = () => reducedQuery.matches || visualMode.value === 'reduced-motion'
  let quality = resolveQuality(window.innerWidth, reducedMotion())
  const cloud = createWhalePointCloud(quality.count)
  let palette = readCanvasPalette()
  let visible = !document.hidden
  let width = 1
  let height = 1
  let pixelRatio = 1

  const resize = () => {
    const bounds = element.getBoundingClientRect()
    width = Math.max(1, bounds.width)
    height = Math.max(1, bounds.height)
    pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5)
    element.width = Math.round(width * pixelRatio)
    element.height = Math.round(height * pixelRatio)
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
    redraw()
  }

  const draw = (time = 0) => {
    element.dataset.effectTheme = palette.theme
    element.dataset.effectColor = palette.effectStrong
    context.clearRect(0, 0, width, height)
    const breath = getWhaleBreath(time, props.state)
    const swim = getWhaleSwimMotion(time, props.state)
    const scale = Math.min(width / 4.2, height / 2.4) * (props.placement === 'agent' ? 1.08 : props.placement === 'knowledge' ? .76 : 1)
    const centerX = width * .5 + swim.x * scale * .08
    const centerY = height * .5 + swim.y * scale
    const pointRadius = Math.max(.55, Math.min(1.45, scale * .009))
    const lineStep = Math.max(18, Math.floor(cloud.phases.length / 120))

    context.save()
    context.translate(centerX, centerY)
    context.rotate(swim.rotation)
    context.scale(scale, scale)
    context.lineWidth = .012
    context.strokeStyle = palette.border
    context.globalAlpha = props.isolated ? .18 : .1
    context.beginPath()
    for (let index = lineStep; index < cloud.phases.length; index += lineStep) {
      const current = index * 3
      const previous = (index - lineStep) * 3
      context.moveTo(cloud.basePositions[previous], cloud.basePositions[previous + 1])
      context.lineTo(cloud.basePositions[current], cloud.basePositions[current + 1])
    }
    context.stroke()

    context.globalAlpha = 1
    for (let index = 0; index < cloud.phases.length; index += 1) {
      const offset = index * 3
      const baseX = cloud.basePositions[offset]
      const baseY = cloud.basePositions[offset + 1]
      const fluid = getGlobalFluidField(baseX, baseY, time, cloud.phases[index])
      const movement = .018 * cloud.flows[index]
      const x = baseX + fluid.x * movement + Math.sin(time * .0008 + cloud.phases[index]) * .012
      const y = baseY + fluid.y * movement + Math.cos(time * .0007 + cloud.phases[index]) * .01
      const breathScale = 1 + breath.intensity * .035
      const opacity = (props.isolated ? .8 : palette.theme === 'light' ? .68 : .34) * (0.88 + breath.intensity * .12)
      tintColor(context, cloud.regions[index] === 1 ? palette.effectPrimary : palette.effectStrong, opacity)
      context.beginPath()
      context.arc(x * breathScale, y * breathScale, pointRadius / scale, 0, Math.PI * 2)
      context.fill()
    }
    context.restore()
  }

  // P3：鲸鱼 2D 云团接入全页共享 rAF 调度器，避免与星野/果冻叠加逐帧竞争。
  const loopId = `canvas-whale-${Math.random().toString(36).slice(2, 8)}`
  let unsubscribeLoop = () => {}
  const syncMotion = () => {
    unsubscribeLoop()
    unsubscribeLoop = () => {}
    quality = resolveQuality(window.innerWidth, reducedMotion())
    if (visible && !document.hidden && quality.animate && !reducedMotion()) {
      unsubscribeLoop = subscribe((_dt, now) => draw(now), { fps: 30, id: loopId })
    } else draw()
  }

  const onTheme = nextPalette => { palette = nextPalette; redraw() }
  const onVisibility = () => { visible = !document.hidden; syncMotion() }
  const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting && !document.hidden; syncMotion() })
  const resizeObserver = new ResizeObserver(resize)
  observer.observe(element)
  resizeObserver.observe(element)
  const stopTheme = observeCanvasTheme(onTheme)

  const stopMode = watch(visualMode, syncMotion)
  redraw = () => draw(reducedMotion() ? 0 : performance.now())
  resize()
  syncMotion()
  window.addEventListener('resize', resize)
  document.addEventListener('visibilitychange', onVisibility)
  reducedQuery.addEventListener?.('change', syncMotion)

  dispose = () => {
    unsubscribeLoop()
    observer.disconnect()
    resizeObserver.disconnect()
    stopTheme()
    stopMode()
    window.removeEventListener('resize', resize)
    document.removeEventListener('visibilitychange', onVisibility)
    reducedQuery.removeEventListener?.('change', syncMotion)
  }
})

watch(() => [props.state, props.placement, props.isolated], () => redraw())
onBeforeUnmount(() => dispose())
</script>

<style scoped>
.canvas-whale { position: fixed; z-index: 0; width: min(58vw, 920px); height: min(64vh, 700px); right: -5vw; top: 10vh; pointer-events: none; opacity: .9; transition: opacity 420ms ease, transform 620ms ease; }
.canvas-whale--knowledge { top: 4vh; right: -15vw; transform: scale(.78); }
.canvas-whale--operations { top: auto; bottom: -18vh; right: 2vw; transform: scale(.86); }
.canvas-whale--agent { top: 8vh; right: -2vw; transform: scale(1.08); }
.canvas-whale--memory { top: auto; bottom: -20vh; right: -8vw; transform: scale(.72); }
.canvas-whale--home { top: 0; bottom: auto; left: 50%; right: auto; transform: translateX(-50%); width: min(43vw, 650px); height: min(36vh, 380px); }
:global([data-theme='light'] .canvas-whale) { opacity: .32; filter: none; }
@media (max-width: 767px) { .canvas-whale { width: 118vw; height: 46vh; right: -38vw; top: 10vh; opacity: .52; } .canvas-whale--agent { top: 16vh; } .canvas-whale--home { left: 50%; right: auto; top: 10vh; width: 85vw; height: 26vh; } }
@media (prefers-reduced-motion: reduce) { .canvas-whale { transition: none; } }
</style>
