<template>
  <div ref="host" class="whale-host" :class="[`whale-host--${placement}`, `whale-host--${state}`]" aria-hidden="true"></div>
</template>

<script setup>
import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Group,
  LineBasicMaterial,
  LineSegments,
  NormalBlending,
  PerspectiveCamera,
  Points,
  PointsMaterial,
  Scene,
  WebGLRenderer
} from 'three'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { clamp, getGlobalFluidField, getWhaleBreath, getWhaleMotionProfile, getWhaleSwimMotion } from './organismMotion'
import { createStellarField, resolveStellarQuality, updateStellarField } from './stellarOcean'
import { resolveWhaleQuality } from './whaleQuality'
import { createWhalePointCloud, whaleRegions } from './whaleShape'
import { observeCanvasTheme, readCanvasPalette } from './canvasTheme.js'
import { resolveEffectTheme } from './effectTheme.js'
import { subscribe } from '../../visual/motionScheduler.js'

const props = defineProps({
  state: { type: String, default: 'idle' },
  placement: { type: String, default: 'home' },
  isolated: { type: Boolean, default: false }
})

const host = ref(null)
let dispose = () => {}
let applyState = () => {}

onMounted(() => {
  const element = host.value
  let effectTheme = resolveEffectTheme(readCanvasPalette())
  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  const quality = resolveWhaleQuality({ width: window.innerWidth, dpr: window.devicePixelRatio || 1, reducedMotion: reducedQuery.matches })
  const scene = new Scene()
  const camera = new PerspectiveCamera(42, 1, 0.1, 100)
  camera.position.set(0, 0, 5.5)
  const renderer = new WebGLRenderer({ alpha: true, antialias: false, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
  element.appendChild(renderer.domElement)
  const swimmer = new Group()
  scene.add(swimmer)

  const cloud = createWhalePointCloud(quality.particleCount)
  const geometry = new BufferGeometry()
  const positionAttribute = new BufferAttribute(cloud.positions, 3)
  geometry.setAttribute('position', positionAttribute)
  geometry.setAttribute('region', new BufferAttribute(cloud.regions, 1))
  const material = new PointsMaterial({ color: '#7ad7f5', size: 0.021, transparent: true, opacity: props.isolated ? 0.92 : 0.46, depthWrite: false, blending: AdditiveBlending, sizeAttenuation: true })
  const points = new Points(geometry, material)
  swimmer.add(points)

  const connectionCount = 120
  const connectionPairs = new Uint32Array(connectionCount * 2)
  const linePositions = new Float32Array(connectionCount * 6)
  for (let index = 0; index < connectionCount; index += 1) {
    connectionPairs[index * 2] = Math.floor(Math.random() * quality.particleCount)
    connectionPairs[index * 2 + 1] = Math.floor(Math.random() * quality.particleCount)
  }
  const lineGeometry = new BufferGeometry()
  const lineAttribute = new BufferAttribute(linePositions, 3)
  lineGeometry.setAttribute('position', lineAttribute)
  const lineMaterial = new LineBasicMaterial({ color: '#2496ed', transparent: true, opacity: 0.09, depthWrite: false })
  const lines = new LineSegments(lineGeometry, lineMaterial)
  swimmer.add(lines)

  const breathCount = quality.tier === 'high' ? 340 : quality.tier === 'medium' ? 180 : 90
  const breathPositions = new Float32Array(breathCount * 3)
  const breathLanes = new Float32Array(breathCount)
  const breathOffsets = new Float32Array(breathCount)
  for (let index = 0; index < breathCount; index += 1) {
    breathLanes[index] = Math.random()
    breathOffsets[index] = Math.random() * Math.PI * 2
    breathPositions[index * 3] = 50
  }
  const breathGeometry = new BufferGeometry()
  const breathAttribute = new BufferAttribute(breathPositions, 3)
  breathGeometry.setAttribute('position', breathAttribute)
  const breathMaterial = new PointsMaterial({ color: '#b6edff', size: 0.017, transparent: true, opacity: 0, depthWrite: false, blending: AdditiveBlending, sizeAttenuation: true })
  swimmer.add(new Points(breathGeometry, breathMaterial))

  const stellarField = createStellarField(resolveStellarQuality({ width: window.innerWidth, dpr: window.devicePixelRatio || 1, reducedMotion: reducedQuery.matches }))
  const stellarPoints = stellarField.layers.map((layer, index) => {
    const starGeometry = new BufferGeometry()
    const position = new BufferAttribute(layer.positions, 3)
    starGeometry.setAttribute('position', position)
    const starMaterial = new PointsMaterial({ color: ['#7f9fb0', '#4da9ff', '#a8dfff'][index], size: [0.009, 0.014, 0.021][index], transparent: true, opacity: [0.14, 0.22, 0.38][index], depthWrite: false, blending: AdditiveBlending, sizeAttenuation: true })
    const stars = new Points(starGeometry, starMaterial)
    scene.add(stars)
    return { geometry: starGeometry, position, material: starMaterial }
  })
  const stellarLinePositions = new Float32Array(stellarField.chainPairs.length * 6)
  const stellarLineGeometry = new BufferGeometry()
  const stellarLineAttribute = new BufferAttribute(stellarLinePositions, 3)
  stellarLineGeometry.setAttribute('position', stellarLineAttribute)
  const stellarChains = new LineSegments(stellarLineGeometry, new LineBasicMaterial({ color: '#4da9ff', transparent: true, opacity: 0.07, depthWrite: false }))
  scene.add(stellarChains)
  const stellarFlowPositions = new Float32Array(stellarField.flowProgress.length * 3)
  const stellarFlowGeometry = new BufferGeometry()
  const stellarFlowAttribute = new BufferAttribute(stellarFlowPositions, 3)
  stellarFlowGeometry.setAttribute('position', stellarFlowAttribute)
  const stellarFlowMaterial = new PointsMaterial({ color: '#bceeff', size: 0.018, transparent: true, opacity: 0.58, depthWrite: false, blending: AdditiveBlending, sizeAttenuation: true })
  scene.add(new Points(stellarFlowGeometry, stellarFlowMaterial))

  let visible = true
  let lastTime = 0
  let frameCounter = 0
  let slowFrames = 0
  let fastFrames = 0
  let drawScale = 1
  const pointer = { x: 99, y: 99, active: false }

  const resize = () => {
    const width = Math.max(element.clientWidth, 1)
    const height = Math.max(element.clientHeight, 1)
    camera.aspect = width / height
    camera.updateProjectionMatrix()
    renderer.setSize(width, height, false)
  }
  const syncConnections = () => {
    const active = Math.floor(quality.particleCount * drawScale)
    for (let index = 0; index < connectionCount; index += 1) {
      const lineOffset = index * 6
      const a = (connectionPairs[index * 2] % active) * 3
      const b = (connectionPairs[index * 2 + 1] % active) * 3
      linePositions[lineOffset] = cloud.positions[a]
      linePositions[lineOffset + 1] = cloud.positions[a + 1]
      linePositions[lineOffset + 2] = cloud.positions[a + 2]
      linePositions[lineOffset + 3] = cloud.positions[b]
      linePositions[lineOffset + 4] = cloud.positions[b + 1]
      linePositions[lineOffset + 5] = cloud.positions[b + 2]
    }
    lineAttribute.needsUpdate = true
  }
  const syncStellarChains = (time, tide = 0) => {
    const midLayer = stellarField.layers[1]
    for (let index = 0; index < stellarField.chainPairs.length / 2; index += 1) {
      const offset = index * 12
      const a = stellarField.chainPairs[index * 2] * 3
      const b = stellarField.chainPairs[index * 2 + 1] * 3
      stellarLinePositions[offset] = midLayer.positions[a]
      stellarLinePositions[offset + 1] = midLayer.positions[a + 1]
      stellarLinePositions[offset + 2] = midLayer.positions[a + 2]
      const curve = Math.sin(time * 0.00024 + index * 1.71) * 0.045
      const middleX = (midLayer.positions[a] + midLayer.positions[b]) * 0.5
      const middleY = (midLayer.positions[a + 1] + midLayer.positions[b + 1]) * 0.5 + curve
      const middleZ = (midLayer.positions[a + 2] + midLayer.positions[b + 2]) * 0.5
      stellarLinePositions[offset + 3] = middleX
      stellarLinePositions[offset + 4] = middleY
      stellarLinePositions[offset + 5] = middleZ
      stellarLinePositions[offset + 6] = middleX
      stellarLinePositions[offset + 7] = middleY
      stellarLinePositions[offset + 8] = middleZ
      stellarLinePositions[offset + 9] = midLayer.positions[b]
      stellarLinePositions[offset + 10] = midLayer.positions[b + 1]
      stellarLinePositions[offset + 11] = midLayer.positions[b + 2]
    }
    stellarLineAttribute.needsUpdate = true
    stellarChains.material.opacity = 0.045 + tide * 0.025
    for (let index = 0; index < stellarField.flowProgress.length; index += 1) {
      const pairIndex = stellarField.flowPairs[index]
      const a = stellarField.chainPairs[pairIndex * 2] * 3
      const b = stellarField.chainPairs[pairIndex * 2 + 1] * 3
      const progress = (stellarField.flowProgress[index] + time * 0.000036 * (0.72 + (index % 5) * 0.11)) % 1
      const offset = index * 3
      stellarFlowPositions[offset] = midLayer.positions[a] + (midLayer.positions[b] - midLayer.positions[a]) * progress
      stellarFlowPositions[offset + 1] = midLayer.positions[a + 1] + (midLayer.positions[b + 1] - midLayer.positions[a + 1]) * progress + Math.sin(progress * Math.PI) * 0.03
      stellarFlowPositions[offset + 2] = midLayer.positions[a + 2] + (midLayer.positions[b + 2] - midLayer.positions[a + 2]) * progress
    }
    stellarFlowAttribute.needsUpdate = true
  }
  const updateStellarOcean = (time, breath) => {
    const tide = updateStellarField(stellarField, time, {
      whale: { x: 0.1, y: -0.04, inhale: breath.inhale, exhale: breath.exhale },
      jellyfish: props.isolated ? { x: 1.05, y: 0.78, strength: 0.32 + breath.exhale * 0.42 } : undefined,
      pointer
    })
    stellarPoints.forEach(({ position, material }, index) => {
      position.needsUpdate = true
      material.opacity = [0.14, 0.22, 0.38][index] + (index === 2 ? tide * 0.05 : tide * 0.018)
    })
    if (frameCounter % 3 === 0) syncStellarChains(time, tide)
  }
  const updateParticles = (time) => {
    const profile = getWhaleMotionProfile(props.state)
    const breath = getWhaleBreath(time, props.state)
    const swim = getWhaleSwimMotion(time, props.state)
    const stroke = time * Math.PI * 2 / 4600
    swimmer.position.set(-swim.x * .7, swim.y + swim.x * .28, 0)
    // Face left and lift the nose; keep the complete silhouette inside the canvas.
    swimmer.scale.set(-.76, .76, .76)
    swimmer.rotation.z = -.28 + swim.rotation + Math.sin(stroke - .5) * .018
    updateStellarOcean(time, breath)
    const activeCount = Math.floor(quality.particleCount * drawScale)
    const fluid = getGlobalFluidField(0, 0, time, 0.23)
    points.position.x = fluid.x * 0.026 + Math.sin(time * 0.00017) * 0.014
    points.position.y = fluid.y * 0.03 + Math.cos(time * 0.00013) * 0.018
    points.rotation.set(Math.sin(time * 0.00019) * 0.004, 0, Math.sin(time * 0.00015) * 0.009)

    for (let index = 0; index < activeCount; index += 1) {
      const offset = index * 3
      const baseX = cloud.basePositions[offset]
      const baseY = cloud.basePositions[offset + 1]
      const baseZ = cloud.basePositions[offset + 2]
      const phase = cloud.phases[index]
      const flow = cloud.flows[index]
      const region = cloud.regions[index]
      let x = baseX
      let y = baseY
      let z = baseZ
      if (region === whaleRegions.body) {
        const rearWeight = clamp((.8 - baseX) / 1.9)
        y += Math.sin(stroke - rearWeight * .9) * rearWeight ** 2 * .085
        const bodyWeight = clamp(1 - Math.abs(baseX - 0.08) / 1.72) * (0.62 + flow * 0.38)
        const expansion = breath.intensity * 0.027 * bodyWeight
        x += (baseX - 0.08) * expansion * 0.58 - breath.inhale * clamp((baseX - 0.4) / 1.1) * 0.018
        y += baseY * expansion * 1.36 + Math.sin(time * 0.0011 + phase + baseX * 2.1) * 0.012 * profile.flow * flow
        z += baseZ * expansion * 0.82 + Math.cos(time * 0.00087 + phase * 1.3) * 0.014 * profile.flow * flow
      } else if (region === whaleRegions.tail) {
        const tailProgress = clamp((-baseX - 1) / .95)
        // One shared stroke bends the tail as a surface, rather than jittering each point.
        const bend = Math.sin(stroke - .9 - tailProgress * .75) * .32 * profile.strength
        const tailX = baseX + 1
        const tailY = baseY - .08
        x = -1 + tailX * Math.cos(bend) - tailY * Math.sin(bend)
        y = .08 + tailX * Math.sin(bend) + tailY * Math.cos(bend)
        y += Math.sin(stroke - .9) * .085 + Math.sin(stroke - 1.65) * tailProgress ** 2 * .09
        z += Math.sin(stroke - tailProgress) * .025 * tailProgress
      } else {
        y += Math.sin(stroke + .7) * .045 * clamp((-baseY - .4) / .55)
        z += Math.cos(stroke + .7) * .045 * profile.flow
      }
      if (profile.turbulence && baseX > 0.52 && baseY < 0.32) {
        const turbulence = Math.sin(time * 0.0021 + phase * 2.7) * profile.turbulence * 0.034
        y += turbulence
        z += turbulence * 0.68
      }
      if (pointer.active) {
        const dx = x - pointer.x
        const dy = y - pointer.y
        const distance = dx * dx + dy * dy
        if (distance < 0.82) {
          const influence = (1 - distance / 0.82) * 0.022
          x += dx * influence
          y += dy * influence
        }
      }
      cloud.positions[offset] = x
      cloud.positions[offset + 1] = y
      cloud.positions[offset + 2] = z
    }
    positionAttribute.needsUpdate = true
    geometry.setDrawRange(0, activeCount)
    for (let index = 0; index < breathCount; index += 1) {
      const offset = index * 3
      const release = (breath.exhale - breathLanes[index] * 0.72) * 1.48
      if (breath.phase === 'exhale' && release > 0 && release < 1) {
        breathPositions[offset] = 1.5 + release * (0.72 + cloud.flows[index % cloud.flows.length] * 0.45)
        breathPositions[offset + 1] = 0.02 + release * 0.5 + Math.sin(time * 0.001 + breathOffsets[index]) * 0.09
        breathPositions[offset + 2] = Math.cos(time * 0.00083 + breathOffsets[index]) * 0.18 * (1 - release)
      } else breathPositions[offset] = 50
    }
    breathAttribute.needsUpdate = true
    breathMaterial.opacity = breath.phase === 'exhale' ? 0.36 * breath.exhale : 0
    material.opacity = (props.isolated ? 0.92 : ({ home: 0.54, agent: 0.72, knowledge: 0.24, operations: 0.34, memory: 0.18 }[props.placement] || 0.32)) * (0.9 + breath.intensity * 0.1)
    if (frameCounter % 3 === 0) syncConnections()
  }
  const adaptQuality = (delta) => {
    if (delta > 34) {
      slowFrames += 1; fastFrames = 0
      if (slowFrames > 84 && drawScale > 0.55) { drawScale = Math.max(0.55, drawScale - 0.18); slowFrames = 0 }
    } else if (delta < 22) {
      fastFrames += 1; slowFrames = 0
      if (fastFrames > 320 && drawScale < 1) { drawScale = Math.min(1, drawScale + 0.1); fastFrames = 0 }
    }
  }
  // P3：WebGL 鲸鱼不再自建 rAF，接入全页共享调度器（30fps + 离屏暂停）。
  const loopId = `particle-whale-${Math.random().toString(36).slice(2, 8)}`
  let unsubscribeLoop = () => {}
  const step = time => {
    const delta = Math.min(time - lastTime || 16, 64)
    lastTime = time; frameCounter += 1; adaptQuality(delta); updateParticles(time)
    renderer.render(scene, camera)
  }
  const syncMotion = () => {
    unsubscribeLoop(); unsubscribeLoop = () => {}; lastTime = 0
    if (quality.animate && !reducedQuery.matches && visible) {
      unsubscribeLoop = subscribe((_dt, now) => step(now), { fps: 30, id: loopId })
    } else renderer.render(scene, camera)
  }
  const pointerMove = (event) => {
    const bounds = element.getBoundingClientRect()
    pointer.x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 4.2
    pointer.y = (0.5 - (event.clientY - bounds.top) / bounds.height) * 2.4
    pointer.active = true
  }
  const pointerLeave = () => { pointer.active = false }
  const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; syncMotion() })
  observer.observe(element)
  applyState = () => {
    material.color.set(props.state === 'warning' || props.state === 'error' ? effectTheme.primary : effectTheme.strong)
    points.scale.setScalar(props.placement === 'agent' ? 1.16 : props.placement === 'knowledge' ? 0.76 : 1)
    lineMaterial.opacity = props.state === 'executing' ? 0.15 : 0.09
    syncMotion()
  }
  const applyTheme = palette => {
    effectTheme = resolveEffectTheme(palette)
    element.dataset.effectTheme = effectTheme.theme
    element.dataset.effectColor = effectTheme.strong
    lineMaterial.color.set(effectTheme.primary)
    breathMaterial.color.set(effectTheme.star)
    stellarChains.material.color.set(effectTheme.primary)
    stellarFlowMaterial.color.set(effectTheme.star)
    stellarPoints.forEach(({ material: starMaterial }, index) => starMaterial.color.set([effectTheme.muted, effectTheme.primary, effectTheme.star][index]))
    for (const themed of [material, breathMaterial, stellarFlowMaterial, ...stellarPoints.map(layer => layer.material)]) {
      themed.blending = effectTheme.blend === 'normal' ? NormalBlending : AdditiveBlending
      themed.needsUpdate = true
    }
    applyState()
  }
  updateStellarOcean(0, getWhaleBreath(0, props.state))
  resize(); applyTheme(readCanvasPalette())
  const stopTheme = observeCanvasTheme(applyTheme)
  element.addEventListener('pointermove', pointerMove)
  element.addEventListener('pointerleave', pointerLeave)
  window.addEventListener('resize', resize)
  document.addEventListener('visibilitychange', syncMotion)
  reducedQuery.addEventListener('change', syncMotion)
  dispose = () => {
    stopTheme()
    unsubscribeLoop(); observer.disconnect()
    element.removeEventListener('pointermove', pointerMove); element.removeEventListener('pointerleave', pointerLeave)
    window.removeEventListener('resize', resize); document.removeEventListener('visibilitychange', syncMotion); reducedQuery.removeEventListener('change', syncMotion)
    geometry.dispose(); material.dispose(); lineGeometry.dispose(); lineMaterial.dispose(); breathGeometry.dispose(); breathMaterial.dispose()
    stellarPoints.forEach(({ geometry: starGeometry, material: starMaterial }) => { starGeometry.dispose(); starMaterial.dispose() })
    stellarLineGeometry.dispose(); stellarChains.material.dispose(); stellarFlowGeometry.dispose(); stellarFlowMaterial.dispose()
    renderer.dispose(); renderer.domElement.remove()
  }
})

watch(() => [props.state, props.placement], () => applyState())
onBeforeUnmount(() => dispose())
</script>

<style scoped>
.whale-host { position: fixed; z-index: 0; width: min(58vw, 920px); height: min(64vh, 700px); right: -5vw; top: 10vh; pointer-events: auto; transition: opacity 420ms ease, transform 620ms ease; }
.whale-host--knowledge { top: 4vh; right: -15vw; transform: scale(.78); }
.whale-host--operations { top: auto; bottom: -18vh; right: 2vw; transform: scale(.86); }
.whale-host--agent { top: 8vh; right: -2vw; transform: scale(1.08); }
.whale-host--memory { top: auto; bottom: -20vh; right: -8vw; transform: scale(.72); }
.whale-host--warning { filter: saturate(.75); }
.whale-host--home { top: 0; bottom: auto; left: 50%; right: auto; transform: translateX(-50%); width: min(43vw, 650px); height: min(36vh, 380px); }
@media (max-width: 767px) { .whale-host { width: 118vw; height: 46vh; right: -38vw; top: 10vh; opacity: .36; } .whale-host--agent { top: 16vh; } }
@media (max-width: 767px) { .whale-host--home { left: 50%; right: auto; top: 10vh; width: 85vw; height: 26vh; } }
@media (prefers-reduced-motion: reduce) { .whale-host { pointer-events: none; transition: none; } }
</style>
