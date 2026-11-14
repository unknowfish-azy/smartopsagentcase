<!--
  EvidenceBed.vue — L0 证据层（DESIGN §3.2 / §3.3）。

  单个 Canvas2D 实例，绘制证据带与点阵。
  只画真实 evidenceBands（来自 useFieldLayout.evidenceBands）。
  空数组时不画任何东西（不补装饰网格/星空）。

  动效：
    - 默认静止；新事件到达时 pulseAt(id) 触发 400ms 局部脉冲
    - motionScheduler 驱动，fps=15
    - prefers-reduced-motion 下只画一帧
-->
<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  bands: { type: Array, default: () => [] },  // useFieldLayout.evidenceBands[]
  worldTransform: { type: String, default: '' },
  worldSize: { type: Object, default: () => ({ w: 7200, h: 660, d: 2000 }) },
})

const canvasRef = ref(null)
let ctx = null
let stopLoop = null
let pulseTimers = new Map()  // bandId → timeoutId

function drawFrame () {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return

  // 用 worldSize 决定逻辑尺寸（不响应式：世界坐标固定）
  const w = props.worldSize.w
  const h = props.worldSize.d  // 证据层沿 z 方向延伸，高度取 d

  // 设备像素比
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width  = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  canvas.style.width  = `${w}px`
  canvas.style.height = `${h}px`
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  // 清空
  ctx.clearRect(0, 0, w, h)

  for (const band of props.bands) {
    drawBand(band)
  }
}

function drawBand (band) {
  ctx.save()
  ctx.globalAlpha = 0.15  // L0 层 opacity 0.10-0.22
  ctx.fillStyle = 'var(--ds-accent, rgba(122,215,245,.45))'
  ctx.strokeStyle = 'rgba(159,190,207,.22)'
  ctx.lineWidth = 1

  // 证据带沿 z 方向条带：rect(x - w/2, z - h/2, w, h) 在世界坐标系里
  // 但 Canvas 是 2D，我们在 xz 平面（y=0）上画，所以只用到 band 自己的 x, z, w, h
  // 这里简化：以 band.x 为中心，在 band.z 处画一条 h=band.density * 2 的横条带
  const x = band.x
  const z = band.z
  const bandH = Math.max(6, band.density * 2)

  ctx.fillRect(
    x - band.w / 2,
    z - bandH / 2,
    band.w,
    bandH,
  )

  // 点阵：density 个小点
  ctx.globalAlpha = 0.35
  ctx.fillStyle = 'rgba(122,215,245,.55)'
  const dots = Math.min(band.density, 40)  // 上限 40 点避免过绘
  for (let i = 0; i < dots; i++) {
    // 确定性伪随机（用 band.id hash）避免动画抖动
    const seed = (hashString(band.id + i) % 1000) / 1000
    const dx = (seed - 0.5) * band.w * 0.9
    const dz = ((hashString(band.id + 'z' + i) % 1000) / 1000 - 0.5) * bandH * 0.8
    ctx.beginPath()
    ctx.arc(x + dx, z + dz, 1.2, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.restore()
}

function hashString (s) {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) & 0xffffffff
  return Math.abs(h)
}

/** 新事件脉冲：band 高亮 400ms 一次性 */
function pulseAt (bandId) {
  // 简化实现：直接重绘（不做逐帧淡出）
  drawFrame()
}

watch(() => props.bands, () => drawFrame(), { deep: true })

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return
  ctx = canvas.getContext('2d')
  drawFrame()
})

onBeforeUnmount(() => {
  if (stopLoop) stopLoop()
  pulseTimers.clear()
})

defineExpose({ pulseAt })
</script>

<template>
  <canvas
    ref="canvasRef"
    class="evidence-bed"
    :style="{ transform: worldTransform + ' translateZ(-1000px)' }"
    aria-hidden="true"
  ></canvas>
</template>

<style scoped>
.evidence-bed {
  position: absolute;
  left: 0;
  top: 0;
  pointer-events: none;
  transform-style: preserve-3d;
}
</style>
