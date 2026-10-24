<template>
  <div ref="root" class="milky-way" :data-state="state" :data-effect-theme="effectTheme" aria-hidden="true">
    <canvas ref="canvas" />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { observeCanvasTheme, readCanvasPalette } from '../common/canvasTheme.js'
import { resolveEffectTheme } from '../common/effectTheme.js'

const props = defineProps({
  particleSize: { type: Number, default: .6 },
  coreColor: { type: String, default: '#f5f5ff' },
  accentColor: { type: String, default: '#ffe6ad' },
  outerColor: { type: String, default: '#e05c12' },
  backgroundColor: { type: String, default: '#03070d' },
  mouseInfluence: { type: Boolean, default: true },
  rotationSpeed: { type: Number, default: .35 },
  viewportCoverage: { type: Number, default: 0 },
  centerX: { type: Number, default: .5 },
})
const root = ref(null), canvas = ref(null), state = ref('loading')
const effectTheme = ref('dark')
let stopTheme = () => {}
let disposed = false, scene, frame = 0, previous = 0, visible = true
let resizeObserver, intersectionObserver, motionQuery
const pointer = { x: 0, y: 0 }

function stop() { cancelAnimationFrame(frame); frame = 0; previous = 0 }
function animate(time) {
  frame = 0
  if (disposed || !scene || !visible || document.hidden || motionQuery.matches) return
  // Limit background work to 30fps; keep time-based motion consistent.
  if (!previous || time - previous >= 1000 / 30) {
    scene.render(previous ? (time - previous) / 1000 : 0, pointer)
    previous = time
  }
  frame = requestAnimationFrame(animate)
}
function sync() {
  stop()
  if (!scene || disposed || !visible || document.hidden) return
  scene.render(0, pointer)
  if (!motionQuery.matches) frame = requestAnimationFrame(animate)
}
function resize() {
  if (!scene || !root.value) return
  scene.resize(Math.max(1, root.value.clientWidth), Math.max(1, root.value.clientHeight))
  sync()
}
function move(event) {
  if (!props.mouseInfluence || motionQuery?.matches || event.pointerType === 'touch') return
  pointer.x = event.clientX / window.innerWidth * 2 - 1
  pointer.y = event.clientY / window.innerHeight * 2 - 1
}
function contextLost(event) { event.preventDefault(); stop(); state.value = 'fallback' }

function themeOptions(palette) {
  const colors = resolveEffectTheme(palette)
  effectTheme.value = colors.theme
  return colors.theme === 'light'
    ? { theme: 'light', coreColor: colors.coreColor, accentColor: colors.accentColor, outerColor: colors.outerColor, backgroundColor: colors.background }
    : { theme: 'dark', coreColor: props.coreColor, accentColor: props.accentColor, outerColor: props.outerColor, backgroundColor: props.backgroundColor }
}

onMounted(async () => {
  themeOptions(readCanvasPalette())
  stopTheme = observeCanvasTheme(palette => { scene?.setTheme(themeOptions(palette)); effectTheme.value = palette.theme; sync() })
  try {
    const { createMilkyWayScene } = await import('./milky-way-scene.js')
    if (disposed) return
    const clamp = (n, min, max, fallback) => Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback
    scene = createMilkyWayScene(canvas.value, { ...props, ...themeOptions(readCanvasPalette()), particleSize: clamp(props.particleSize, .2, 3, .6), rotationSpeed: clamp(props.rotationSpeed, 0, 2, .35) })
    motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    motionQuery.addEventListener('change', sync)
    document.addEventListener('visibilitychange', sync)
    window.addEventListener('pointermove', move, { passive: true })
    canvas.value.addEventListener('webglcontextlost', contextLost)
    resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(root.value)
    intersectionObserver = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; sync() })
    intersectionObserver.observe(root.value)
    resize()
    state.value = 'ready'
  } catch {
    // Keep a quiet CSS nebula when WebGL is unavailable; login stays usable.
    stop()
    scene?.dispose()
    scene = null
    state.value = 'fallback'
  }
})
onBeforeUnmount(() => {
  disposed = true
  stopTheme()
  stop()
  resizeObserver?.disconnect()
  intersectionObserver?.disconnect()
  motionQuery?.removeEventListener('change', sync)
  document.removeEventListener('visibilitychange', sync)
  window.removeEventListener('pointermove', move)
  canvas.value?.removeEventListener('webglcontextlost', contextLost)
  scene?.dispose()
})
</script>

<style scoped>
.milky-way { position: absolute; inset: 0; z-index: -1; overflow: hidden; pointer-events: none; background: radial-gradient(ellipse at 35% 58%, #262b46 0, #0e1526 25%, #03070d 70%); }
.milky-way canvas { display: block; width: 100%; height: 100%; pointer-events: none; }
.milky-way::after { content: ''; position: absolute; inset: 0; background: radial-gradient(ellipse at 45% 55%, transparent 25%, rgba(3,7,13,.4) 85%); pointer-events: none; }
.milky-way[data-state='fallback'] canvas { visibility: hidden; }
:global([data-theme='light'] .milky-way) {
  opacity: 1;
  background: linear-gradient(140deg, #f4f7f9 0%, #eaf2f5 52%, #f7fafb 100%);
}
:global([data-theme='light'] .milky-way canvas) { opacity: .26; }
:global([data-theme='light'] .milky-way::after) { background: radial-gradient(ellipse at 45% 55%, transparent 25%, rgba(244, 247, 249, .4) 85%); }
</style>

