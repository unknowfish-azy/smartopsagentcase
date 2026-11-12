<template>
  <svg ref="svg" class="living-jellyfish" :class="`living-jellyfish--${state}`" :data-motion-mode="motionMode" viewBox="0 0 400 470" aria-hidden="true">
    <defs>
      <radialGradient id="jelly-body" cx="50%" cy="38%" r="65%"><stop offset="0" stop-color="var(--jelly-core, #ff9fd5)" stop-opacity=".88"/><stop offset=".42" stop-color="var(--jelly-body-color, #ff4fa3)" stop-opacity=".58"/><stop offset="1" stop-color="var(--jelly-edge, #7c6cff)" stop-opacity=".1"/></radialGradient>
      <linearGradient id="jelly-rim" x1="0" x2="1"><stop stop-color="var(--jelly-core, #ff6bc1)" stop-opacity=".25"/><stop offset=".45" stop-color="var(--jelly-core, #ff9ed8)"/><stop offset="1" stop-color="var(--jelly-edge, #d94bff)" stop-opacity=".34"/></linearGradient>
      <linearGradient id="jelly-tentacle" x1="0" y1="0" x2="0" y2="1"><stop stop-color="var(--jelly-edge, #b17dff)" stop-opacity=".75"/><stop offset=".5" stop-color="var(--jelly-flow, #5aa9ff)" stop-opacity=".74"/><stop offset="1" stop-color="var(--jelly-flow, #78e7ff)" stop-opacity=".08"/></linearGradient>
      <filter id="jelly-glow" x="-45%" y="-45%" width="190%" height="190%"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      <filter id="jelly-soft"><feGaussianBlur stdDeviation="0.35"/></filter>
      <linearGradient id="jelly-ring" x1="0" x2="1"><stop stop-color="var(--jelly-flow, #79efff)" stop-opacity="0"/><stop offset=".48" stop-color="var(--jelly-edge, #b3a5ff)" stop-opacity=".9"/><stop offset="1" stop-color="var(--jelly-core, #ff8ccc)" stop-opacity="0"/></linearGradient>
    </defs>
    <g ref="organism" class="organism">
      <g class="pulse-rings"><ellipse v-for="ring in rings" :key="ring" ref="ringEls" class="pulse-ring" /></g>
      <g class="tentacles"><path v-for="tentacle in tentacles" :key="tentacle.id" ref="tentacleEls" class="tentacle"/></g>
      <path ref="bodyGlow" class="body-glow"/>
      <path ref="body" class="body"/>
      <path ref="rim" class="rim"/>
      <g class="bell-ribs" fill="none" stroke="#b9eaff" stroke-width="1.2" opacity=".5"><path d="M200 74 C160 91 138 140 132 189"/><path d="M200 74 C184 106 177 150 178 201"/><path d="M200 74 C216 106 223 150 222 201"/><path d="M200 74 C240 91 262 140 268 189"/><path d="M87 184 Q200 227 313 184" stroke-width="2"/></g>
      <g class="internal-flow"><path v-for="flow in flows" :key="flow" ref="flowEls"/></g>
      <g class="particles"><circle v-for="particle in visibleParticles" :key="particle.id" ref="particleEls" r="1.05"/></g>
    </g>
  </svg>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getEcosystemTide, getJellyfishProfile } from './organismMotion'
import { getStellarFlowField } from './stellarOcean'
import { subscribe } from '../../visual/motionScheduler.js'

const props = defineProps({
  state: { type: String, default: 'idle' },
  ecosystem: { type: String, default: '' },
  motionMode: { type: String, default: 'balanced' }
})

const svg = ref(null)
const organism = ref(null)
const body = ref(null)
const bodyGlow = ref(null)
const rim = ref(null)
const tentacleEls = ref([])
const flowEls = ref([])
const particleEls = ref([])
const ringEls = ref([])
const tentacles = Array.from({ length: 12 }, (_, index) => ({ id: index, phase: index * 1.87, length: 108 + ((index * 43) % 82), offset: (index - 5.5) * 12.2, speed: 0.58 + (index % 5) * 0.12 }))
const flows = Array.from({ length: 6 }, (_, index) => index)
const rings = Array.from({ length: 3 }, (_, index) => index)
const particles = Array.from({ length: 200 }, (_, index) => ({
  id: index,
  phase: index * 2.399,
  radius: ((index * 17) % 97) / 97,
  angle: index * 1.618,
  kind: index % 5 === 0 ? 'outer' : index % 3 === 0 ? 'tentacle' : 'body',
  tentacle: index % 12,
  speed: 0.23 + (index % 7) * 0.047
}))

const pointer = { x: 200, y: 190, active: false }
const visibleParticles = computed(() => props.motionMode === 'balanced' ? particles : particles.slice(0, 120))
let visible = true
let reduced = false
let particleTime = 0
let query
let visibilityHandler

function bodyPath(amount = 0) {
  const wide = 114 + amount * 10
  const top = 74 - amount * 4
  const bottom = 184 + amount * 4
  return `M ${200 - wide} ${bottom} C ${200 - wide + 4} ${top + 20}, 145 ${top}, 200 ${top} C 255 ${top}, ${200 + wide - 4} ${top + 20}, ${200 + wide} ${bottom} C 292 ${bottom + 20}, 255 ${bottom + 29}, 200 ${bottom + 25} C 145 ${bottom + 29}, 108 ${bottom + 20}, ${200 - wide} ${bottom} Z`
}
function getTentacle(tentacle, time, profile, coupling) {
  const baseX = 200 + tentacle.offset
  const baseY = 186 - Math.cos(tentacle.offset * 0.04) * 5
  const flow = getStellarFlowField(baseX * 0.01, tentacle.offset * 0.02, time, tentacle.phase)
  const amplitude = (20 + Math.abs(tentacle.offset) * 0.18) * profile.tentacle * (1 + coupling * 0.22)
  const wave = Math.sin(time * 0.00072 * tentacle.speed + tentacle.phase) * amplitude
  const delayed = Math.sin(time * 0.00054 * tentacle.speed + tentacle.phase * 1.7) * amplitude * 1.18
  const pull = coupling * (baseX < 200 ? 1 : -1) * 9
  return {
    baseX, baseY,
    c1x: baseX + wave * 0.62 + flow.x * 5 + pull * 0.16,
    c1y: baseY + tentacle.length * 0.27,
    c2x: baseX + tentacle.offset * .55 - wave * 0.48 + delayed * 0.82 + flow.x * 8 + pull * 0.52,
    c2y: baseY + tentacle.length * 0.7,
    tipX: baseX + tentacle.offset * .85 + delayed + flow.x * 12 + pull,
    tipY: baseY + tentacle.length
  }
}
function cubic(geometry, progress) {
  const inverse = 1 - progress
  const x = inverse ** 3 * geometry.baseX + 3 * inverse ** 2 * progress * geometry.c1x + 3 * inverse * progress ** 2 * geometry.c2x + progress ** 3 * geometry.tipX
  const y = inverse ** 3 * geometry.baseY + 3 * inverse ** 2 * progress * geometry.c1y + 3 * inverse * progress ** 2 * geometry.c2y + progress ** 3 * geometry.tipY
  return { x, y }
}
function render(time = 0, staticFrame = false) {
  const profile = getJellyfishProfile(props.state)
  const tide = getEcosystemTide(time, props.state === 'working' ? 'executing' : props.state)
  const coupling = props.ecosystem ? tide.release : 0
  const fluid = getStellarFlowField(0.6, -0.2, time, 0.71)
  const breathe = (Math.sin(time * (Math.PI * 2) / (profile.breathDuration * 1000) + 0.8) + 1) * 0.5
  const pointerStrength = pointer.active ? 1 : 0
  const pointerX = (200 - pointer.x) * 0.026 * pointerStrength
  const pointerY = (165 - pointer.y) * 0.018 * pointerStrength
  // A broad, slow swim plus a short upward stroke on each bell contraction.
  const driftX = fluid.x * 8 + Math.sin(time * 0.00027 + 0.7) * 23 + pointerX
  const driftY = fluid.y * 12 + Math.cos(time * 0.00021 + 2.1) * 25 - breathe * 10 + pointerY
  const tilt = Math.sin(time * 0.00023 + 1.2) * 4 + pointerX * 0.07
  organism.value?.setAttribute('transform', `translate(${driftX.toFixed(2)} ${driftY.toFixed(2)}) rotate(${tilt.toFixed(2)} 200 185)`)
  const shape = bodyPath(breathe * 0.8 + coupling * 0.42)
  body.value?.setAttribute('d', shape)
  bodyGlow.value?.setAttribute('d', shape)
  rim.value?.setAttribute('d', `M 86 ${184 + breathe * 4} C 92 98, 145 ${69 - breathe * 3}, 200 ${69 - breathe * 3} C 255 ${69 - breathe * 3}, 308 98, 314 ${184 + breathe * 4}`)
  bodyGlow.value?.setAttribute('opacity', `${0.38 + breathe * 0.18 + coupling * 0.14}`)
  ringEls.value.forEach((ring, index) => {
    const progress = (time * 0.000105 + index / rings.length) % 1
    ring?.setAttribute('cx', '200')
    ring?.setAttribute('cy', `${165 + progress * 16}`)
    ring?.setAttribute('rx', `${48 + progress * 122}`)
    ring?.setAttribute('ry', `${13 + progress * 30}`)
    ring?.setAttribute('opacity', `${(1 - progress) * (0.24 + breathe * 0.2 + coupling * 0.18)}`)
  })

  const geometry = tentacles.map((tentacle) => getTentacle(tentacle, time, profile, coupling))
  geometry.forEach((curve, index) => {
    tentacleEls.value[index]?.setAttribute('d', `M ${curve.baseX} ${curve.baseY} C ${curve.c1x.toFixed(1)} ${curve.c1y.toFixed(1)}, ${curve.c2x.toFixed(1)} ${curve.c2y.toFixed(1)}, ${curve.tipX.toFixed(1)} ${curve.tipY.toFixed(1)}`)
  })
  flows.forEach((flow, index) => {
    const curve = geometry[(index * 2 + 1) % geometry.length]
    const startX = 178 + index * 8.8
    flowEls.value[index]?.setAttribute('d', `M ${startX} 108 C ${startX + 10} 142, ${curve.c1x.toFixed(1)} ${(curve.c1y - 15).toFixed(1)}, ${curve.c2x.toFixed(1)} ${(curve.c2y - 4).toFixed(1)}`)
    flowEls.value[index]?.setAttribute('stroke-dashoffset', `${-(time * 0.018 * profile.flow + index * 17)}`)
  })

  if (!staticFrame && time - particleTime < 32) return
  particleTime = time
  visibleParticles.value.forEach((particle, index) => {
    const element = particleEls.value[index]
    if (!element) return
    let x = 200
    let y = 145
    let opacity = 0.36
    if (particle.kind === 'tentacle') {
      const progress = (particle.radius + time * 0.00006 * profile.flow * particle.speed) % 1
      const point = cubic(geometry[particle.tentacle], progress)
      x = point.x + Math.sin(time * 0.001 + particle.phase) * 1.8
      y = point.y
      opacity = 0.22 + progress * 0.42 + coupling * 0.18
    } else if (particle.kind === 'outer') {
      const radius = 118 + particle.radius * 74
      const angle = particle.angle + time * 0.00008 * particle.speed
      x = 200 + Math.cos(angle) * radius
      y = 160 + Math.sin(angle * 1.17) * radius * 0.68
      opacity = 0.07 + particle.radius * 0.14
    } else {
      const radius = particle.radius * (70 + breathe * 11)
      const angle = particle.angle + time * 0.00028 * (0.4 + profile.flow) * particle.speed
      x = 200 + Math.cos(angle) * radius * 1.3
      y = 136 + Math.sin(angle * 1.14) * radius * 0.7 + Math.sin(time * 0.001 + particle.phase) * 3
      opacity = 0.22 + (1 - particle.radius) * 0.36 + coupling * 0.16
    }
    element.setAttribute('cx', x.toFixed(2))
    element.setAttribute('cy', y.toFixed(2))
    element.setAttribute('opacity', opacity.toFixed(2))
    element.setAttribute('fill', ['var(--jelly-core, #ff8ccc)', 'var(--jelly-flow, #78e7ff)', 'var(--jelly-edge, #b7a1ff)'][index % 3])
  })
}
// P3：不再自建 rAF，交给全页共享调度器（30fps）统一排队；离屏与隐藏由调度器暂停。
const loopId = `living-jellyfish-${Math.random().toString(36).slice(2, 8)}`
let unsubscribeLoop = () => {}
function onPointerMove(event) {
  const bounds = svg.value.getBoundingClientRect()
  pointer.x = (event.clientX - bounds.left) / bounds.width * 400
  pointer.y = (event.clientY - bounds.top) / bounds.height * 470
  pointer.active = true
}
function onPointerLeave() { pointer.active = false }
function syncMotion() {
  reduced = query.matches || props.motionMode === 'reduced-motion'
  unsubscribeLoop()
  unsubscribeLoop = () => {}
  if (!visible || reduced) render(performance.now(), true)
  else unsubscribeLoop = subscribe((_dt, now) => render(now), { fps: 30, id: loopId })
}
onMounted(() => {
  query = window.matchMedia('(prefers-reduced-motion: reduce)')
  svg.value.addEventListener('pointermove', onPointerMove)
  svg.value.addEventListener('pointerleave', onPointerLeave)
  visibilityHandler = () => { visible = !document.hidden; syncMotion() }
  document.addEventListener('visibilitychange', visibilityHandler)
  query.addEventListener('change', syncMotion)
  syncMotion()
})
onBeforeUnmount(() => {
  unsubscribeLoop()
  svg.value?.removeEventListener('pointermove', onPointerMove)
  svg.value?.removeEventListener('pointerleave', onPointerLeave)
  document.removeEventListener('visibilitychange', visibilityHandler)
  query?.removeEventListener('change', syncMotion)
})
watch(() => props.motionMode, () => { if (query) syncMotion() }, { flush: 'post' })
</script>

<style scoped>
.living-jellyfish { display: block; width: min(42vw, 540px); height: min(72vh, 680px); overflow: visible; pointer-events: auto; }
.organism { transform-origin: center; will-change: transform; }
.tentacle { fill: none; stroke: url(#jelly-tentacle); stroke-width: 2.4; stroke-linecap: round; filter: url(#jelly-soft); opacity: .82; }
.body-glow { fill: #ff4fa3; filter: url(#jelly-glow); opacity: .42; }
.body { fill: url(#jelly-body); stroke: rgba(255,151,212,.72); stroke-width: 1.3; filter: url(#jelly-glow); }
.pulse-ring { fill: none; stroke: url(#jelly-ring); stroke-width: 1.5; stroke-dasharray: 3 8; filter: url(#jelly-soft); }
.rim { fill: none; stroke: url(#jelly-rim); stroke-width: 2.1; stroke-linecap: round; filter: url(#jelly-soft); }
.internal-flow path { fill: none; stroke: #78e7ff; stroke-opacity: .7; stroke-width: 1.5; stroke-dasharray: 3 8; filter: url(#jelly-soft); }
.particles circle { filter: url(#jelly-soft); }
.living-jellyfish--warning .body-glow, .living-jellyfish--error .body-glow { fill: #ff6bc1; }
:global([data-theme='light'] .living-jellyfish) { --jelly-core: #563f64; --jelly-body-color: #614365; --jelly-edge: #444c78; --jelly-flow: #315f77; }
:global([data-theme='light'] .living-jellyfish .body-glow) { fill: var(--jelly-body-color); filter: none; }
:global([data-theme='light'] .living-jellyfish .body) { stroke: var(--jelly-core); filter: none; }
:global([data-theme='light'] .living-jellyfish .bell-ribs) { stroke: var(--jelly-flow); }
:global([data-theme='light'] .living-jellyfish .internal-flow path) { stroke: var(--jelly-flow); }
@media (max-width: 767px) { .living-jellyfish { width: min(88vw, 390px); height: 390px; } }
@media (prefers-reduced-motion: reduce) { .living-jellyfish { pointer-events: none; } }
</style>
