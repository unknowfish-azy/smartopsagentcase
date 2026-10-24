<template>
  <canvas ref="canvas" class="galaxy-background" aria-hidden="true"></canvas>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const canvas = ref(null)
let frame = 0
let resizeHandler
let visibilityHandler
let motionQuery
let motionHandler

onMounted(() => {
  const element = canvas.value
  const context = element?.getContext('2d')
  if (!element || !context) return
  const stars = []
  let width = 1
  let height = 1
  let centerX = 0
  let centerY = 0
  let scale = 1
  let previous = 0

  const random = (seed => () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296 })(9137)
  const resize = () => {
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5)
    width = Math.max(1, element.clientWidth)
    height = Math.max(1, element.clientHeight)
    element.width = Math.round(width * ratio)
    element.height = Math.round(height * ratio)
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    centerX = width * .54
    centerY = height * .48
    scale = Math.min(width, height) * .46
    const count = width < 700 ? 260 : 620
    stars.length = 0
    for (let i = 0; i < count; i++) {
      const arm = i % 2 ? 0 : Math.PI
      const radius = Math.pow(random(), .72)
      const angle = arm + radius * Math.PI * 3.1 + (random() - .5) * (.25 + radius * .6)
      stars.push({ radius, angle, size: .35 + random() * 1.35, alpha: .2 + random() * .65, warm: random() > .72 })
    }
  }
  const paint = (time, animate) => {
    context.clearRect(0, 0, width, height)
    const glow = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, scale * .8)
    glow.addColorStop(0, 'rgba(255,222,166,.22)')
    glow.addColorStop(.18, 'rgba(98,171,220,.1)')
    glow.addColorStop(1, 'rgba(0,0,0,0)')
    context.fillStyle = glow
    context.fillRect(0, 0, width, height)
    const drift = animate ? time * .000018 : 0
    for (const star of stars) {
      const radius = star.radius * scale
      const angle = star.angle + drift * (1.2 - star.radius)
      const x = centerX + Math.cos(angle) * radius
      const y = centerY + Math.sin(angle) * radius * .34
      const spread = 1 + star.radius * 2.4
      context.fillStyle = star.warm ? `rgba(255,219,167,${star.alpha})` : `rgba(157,220,255,${star.alpha})`
      context.beginPath()
      context.arc(x, y, star.size * spread, 0, Math.PI * 2)
      context.fill()
    }
  }
  const animate = time => {
    if (document.hidden || motionQuery.matches) return
    if (time - previous > 1000 / 24) { paint(time, true); previous = time }
    frame = requestAnimationFrame(animate)
  }
  const sync = () => {
    cancelAnimationFrame(frame)
    paint(0, false)
    if (!document.hidden && !motionQuery.matches) frame = requestAnimationFrame(animate)
  }
  resizeHandler = () => { resize(); sync() }
  visibilityHandler = sync
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  resize()
  sync()
  window.addEventListener('resize', resizeHandler, { passive: true })
  document.addEventListener('visibilitychange', visibilityHandler)
  motionHandler = sync
  motionQuery.addEventListener?.('change', motionHandler)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  if (visibilityHandler) document.removeEventListener('visibilitychange', visibilityHandler)
  motionQuery?.removeEventListener?.('change', motionHandler)
})
</script>

<style scoped>
.galaxy-background { position: absolute; inset: 0; z-index: -1; width: 100%; height: 100%; pointer-events: none; opacity: .72; background: #03070d; }
:global([data-theme='light'] .galaxy-background) { opacity: .2; mix-blend-mode: multiply; }
</style>
