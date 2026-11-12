<template>
  <div ref="root" class="black-hole-background" aria-hidden="true">
    <img ref="reference" class="black-hole-reference" :src="imageSrc" alt="" @load="prepare" />
    <canvas ref="canvas" class="black-hole-canvas"></canvas>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { BH_CONFIG } from './blackHoleConfig.js'

// P3：默认不再加载 1MB 的 black-hole-effect.png，改用 <1KB 静态星野占位，
// 消除整图 getImageData 同步扫描对渲染线程的阻塞；外部仍可传 imageSrc 覆盖。
defineProps({ imageSrc: { type: String, default: '/assets/starfield-placeholder.svg' } })
const root = ref(null), reference = ref(null), canvas = ref(null)
let ctx, observer, motion
let stars = [], frame = 0, enabled = true, last = 0
let width = 1, height = 1, scale = 1, left = 0, top = 0

function prepare() {
  const image = reference.value
  if (!image?.naturalWidth || !ctx) return
  const sample = document.createElement('canvas')
  sample.width = image.naturalWidth
  sample.height = image.naturalHeight
  const sampling = sample.getContext('2d', { willReadFrequently: true })
  sampling.drawImage(image, 0, 0)
  const { data } = sampling.getImageData(0, 0, sample.width, sample.height)
  const light = (x, y) => data[(y * sample.width + x) * 4]
  stars = []
  // Sample isolated existing white points. Exclude the disk, figure and corner mark.
  for (let y = 5; y < sample.height - 5; y += 5) {
    for (let x = 5; x < sample.width - 5; x += 5) {
      const nx = x / sample.width, ny = y / sample.height
      if (((nx - .54) / .47) ** 2 + ((ny - .42) / .25) ** 2 < 1) continue
      if (nx > .84 && ny > .91) continue
      let sx = x, sy = y, peak = 0
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        const value = light(x + dx, y + dy)
        if (value > peak) { peak = value; sx = x + dx; sy = y + dy }
      }
      if (peak < 195) continue
      const surround = (light(sx - 3, sy) + light(sx + 3, sy) + light(sx, sy - 3) + light(sx, sy + 3)) / 4
      if (surround > 85) continue
      stars.push({ x: sx, y: sy, phase: Math.random() * Math.PI * 2, speed: .6 + Math.random() * .8 })
    }
  }
  if (!stars.length) {
    // 内联占位图没有实拍白点可采样：用确定性伪随机补齐星点，保证可复现。
    let seed = 20261112
    const rand = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296 }
    for (let i = 0; i < (BH_CONFIG.starCount || 260); i++) {
      stars.push({ x: rand() * sample.width, y: rand() * sample.height, phase: rand() * Math.PI * 2, speed: .6 + rand() * .8 })
    }
  }
  const stride = Math.max(1, Math.ceil(stars.length / BH_CONFIG.starCount))
  stars = stars.filter((_, index) => index % stride === 0)
  resize()
  sync()
}

function resize() {
  if (!ctx || !root.value) return
  width = root.value.clientWidth
  height = root.value.clientHeight
  const ratio = Math.min(window.devicePixelRatio || 1, BH_CONFIG.maxPixelRatio)
  canvas.value.width = Math.round(width * ratio)
  canvas.value.height = Math.round(height * ratio)
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  const image = reference.value
  if (!image?.naturalWidth) return
  // Match CSS cover and its focal point exactly, including on viewport resize.
  // The source stays untouched; only the viewport crops the scaled photograph.
  scale = Math.max(width / image.naturalWidth, height / image.naturalHeight)
  left = (width - image.naturalWidth * scale) / 2
  top = (height - image.naturalHeight * scale) * .42
}

function animate(time) {
  if (time - last >= 1000 / BH_CONFIG.fps) {
    last = time
    ctx.clearRect(0, 0, width, height)
    for (const star of stars) {
      const alpha = BH_CONFIG.twinkleDepth * (.5 + .5 * Math.sin(time * .001 * star.speed + star.phase)) ** 2
      const x = left + star.x * scale, y = top + star.y * scale
      const radius = Math.max(.5, 2.5 * scale)
      const mask = ctx.createRadialGradient(x, y, 0, x, y, radius)
      mask.addColorStop(0, 'rgba(0,0,0,' + alpha + ')')
      mask.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = mask
      ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2)
    }
  }
  frame = requestAnimationFrame(animate)
}
function sync() {
  cancelAnimationFrame(frame)
  frame = 0
  ctx?.clearRect(0, 0, width, height)
  if (enabled && ctx && stars.length && !document.hidden && !motion?.matches) {
    last = 0
    frame = requestAnimationFrame(animate)
  }
}
function start() { enabled = true; sync() }
function stop() { enabled = false; sync() }
onMounted(() => {
  ctx = canvas.value.getContext('2d')
  if (!ctx) return
  motion = window.matchMedia('(prefers-reduced-motion: reduce)')
  motion.addEventListener('change', sync)
  document.addEventListener('visibilitychange', sync)
  observer = new ResizeObserver(resize)
  observer.observe(root.value)
  prepare()
})
onBeforeUnmount(() => {
  enabled = false
  cancelAnimationFrame(frame)
  observer?.disconnect()
  motion?.removeEventListener('change', sync)
  document.removeEventListener('visibilitychange', sync)
})
defineExpose({ start, stop, resize })
</script>

<style scoped>
.black-hole-background { position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none; background: #000; }
.black-hole-reference, .black-hole-canvas { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.black-hole-reference { object-fit: cover; object-position: 50% 42%; opacity: 1; filter: brightness(.28) saturate(.72); }
</style>
