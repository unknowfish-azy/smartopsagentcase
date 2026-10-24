<template>
  <canvas ref="particleCanvas" class="particle-background" aria-hidden="true"></canvas>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const particleCanvas = ref(null)
let stopParticles = () => {}

onMounted(() => {
  const canvas = particleCanvas.value
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
  const particles = []
  let width = 0
  let height = 0
  let frame = 0
  let previousTime = 0

  const paint = (elapsed = 0) => {
    ctx.clearRect(0, 0, width, height)
    for (const particle of particles) {
      particle.x = (particle.x + particle.vx * elapsed / width + 1) % 1
      particle.y = (particle.y + particle.vy * elapsed / height + 1) % 1
    }

    const reach = width < 700 ? 100 : 150
    ctx.lineWidth = .6
    for (let i = 0; i < particles.length; i++) {
      const a = particles[i]
      for (let j = i + 1; j < particles.length; j++) {
        const b = particles[j]
        const distance = Math.hypot((a.x - b.x) * width, (a.y - b.y) * height)
        if (distance >= reach) continue
        ctx.strokeStyle = `rgba(99,207,223,${.2 * (1 - distance / reach)})`
        ctx.beginPath()
        ctx.moveTo(a.x * width, a.y * height)
        ctx.lineTo(b.x * width, b.y * height)
        ctx.stroke()
      }
    }

    for (const particle of particles) {
      const x = particle.x * width
      const y = particle.y * height
      const glow = ctx.createRadialGradient(x, y, 0, x, y, particle.size * 6)
      glow.addColorStop(0, 'rgba(99,207,223,.24)')
      glow.addColorStop(1, 'rgba(99,207,223,0)')
      ctx.fillStyle = glow
      ctx.beginPath()
      ctx.arc(x, y, particle.size * 6, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = `rgba(155,231,245,${particle.opacity})`
      ctx.beginPath()
      ctx.arc(x, y, particle.size, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  const animate = time => {
    // Limit animation to 30 fps and avoid jumps after a suspended tab.
    const elapsed = previousTime ? time - previousTime : 34
    if (elapsed >= 1000 / 30) {
      paint(Math.min(elapsed, 50) / 1000)
      previousTime = time
    }
    frame = requestAnimationFrame(animate)
  }

  const syncAnimation = () => {
    cancelAnimationFrame(frame)
    previousTime = 0
    if (document.hidden) return
    paint()
    if (!motionPreference.matches) frame = requestAnimationFrame(animate)
  }

  const resize = () => {
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    width = Math.max(canvas.clientWidth, 1)
    height = Math.max(canvas.clientHeight, 1)
    canvas.width = Math.round(width * ratio)
    canvas.height = Math.round(height * ratio)
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
    const count = Math.min(width < 700 ? 45 : 110, Math.max(24, Math.round(width * height / 13000)))
    particles.length = Math.min(particles.length, count)
    while (particles.length < count) {
      particles.push({
        x: Math.random(), y: Math.random(),
        vx: (Math.random() - .5) * 16, vy: (Math.random() - .5) * 16,
        size: .8 + Math.random() * 1.3, opacity: .35 + Math.random() * .4
      })
    }
    syncAnimation()
  }

  resize()
  window.addEventListener('resize', resize)
  document.addEventListener('visibilitychange', syncAnimation)
  motionPreference.addEventListener('change', syncAnimation)
  stopParticles = () => {
    cancelAnimationFrame(frame)
    window.removeEventListener('resize', resize)
    document.removeEventListener('visibilitychange', syncAnimation)
    motionPreference.removeEventListener('change', syncAnimation)
  }
})
onBeforeUnmount(() => stopParticles())
</script>

<style scoped>
.particle-background { position: fixed; inset: 0; z-index: 0; width: 100%; height: 100%; pointer-events: none; }
</style>
