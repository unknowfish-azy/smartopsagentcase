<template>
  <div ref="wrapRef" class="spread-host">
    <canvas ref="canvasRef" class="spread-canvas" :aria-label="ariaLabel" role="img"></canvas>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  rows: { type: Array, default: () => [] }   // [{ key, cn, en, peak, grade }] 已排序
})

const wrapRef = ref(null)
const canvasRef = ref(null)
let ro = null
let lastDpr = 1

const ariaLabel = computed(() =>
  `窗口内离散落差条形图 · ${props.rows.map(r => r.en).join('/') || '未选择'}`
)

function draw() {
  const canvas = canvasRef.value
  const host = wrapRef.value
  if (!canvas || !host) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const rect = host.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return

  const needResize = canvas.width !== Math.round(rect.width * dpr) ||
                     canvas.height !== Math.round(rect.height * dpr)
  if (needResize || dpr !== lastDpr) {
    canvas.width = Math.round(rect.width * dpr)
    canvas.height = Math.round(rect.height * dpr)
    canvas.style.width = `${rect.width}px`
    canvas.style.height = `${rect.height}px`
    lastDpr = dpr
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, rect.width, rect.height)

  const styles = getComputedStyle(host)
  const c_text = styles.getPropertyValue('--sp-text').trim() || '#E8F2F7'
  const c_dim = '#5D6B78'
  const c_bar = styles.getPropertyValue('--sp-accent').trim() || '#2496ED'
  const c_warn = '#D29922'
  const c_crit = '#F85149'

  ctx.font = '10px Consolas, "Cascadia Mono", monospace'
  ctx.textBaseline = 'middle'

  const rows = props.rows
  if (!rows.length) {
    ctx.fillStyle = c_dim
    ctx.textAlign = 'center'
    ctx.fillText('—', rect.width / 2, rect.height / 2)
    return
  }

  const max = Math.max(...rows.map(r => r.peak), 1)
  const rowH = Math.min(30, (rect.height - 8) / rows.length)
  const labelW = 88

  rows.forEach((row, i) => {
    const y = 6 + rowH * i
    const barH = Math.min(12, rowH - 10)
    const color = row.grade === 'crit' ? c_crit : row.grade === 'warn' ? c_warn : c_bar

    ctx.fillStyle = c_dim
    ctx.textAlign = 'left'
    ctx.fillText(row.en, 4, y + rowH / 2)

    const trackX = labelW
    const trackW = rect.width - labelW - 52
    ctx.fillStyle = 'rgba(255,255,255,.07)'
    ctx.fillRect(trackX, y + (rowH - barH) / 2, trackW, barH)

    const w = Math.max(2, (row.peak / max) * trackW)
    ctx.fillStyle = color
    ctx.fillRect(trackX, y + (rowH - barH) / 2, w, barH)

    ctx.fillStyle = c_text
    ctx.textAlign = 'right'
    ctx.fillText(`${row.peak.toFixed(1)}%`, rect.width - 6, y + rowH / 2)
  })
}

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => draw())
    ro.observe(canvasRef.value)
  }
  draw()
})
onBeforeUnmount(() => ro?.disconnect())

watch(() => [props.rows, () => props.rows.map(r => r.peak).join(',')],
  () => draw(), { deep: true })
</script>

<style scoped>
.spread-host {
  width: 100%;
  height: 100%;
  --sp-text: var(--ds-color-text, var(--smart-text, #E8F2F7));
  --sp-accent: var(--ds-color-primary, var(--smart-primary, #2496ED));
}

.spread-canvas {
  display: block;
  width: 100%;
  height: 100%;
}

@media (prefers-reduced-motion: reduce) {
  .spread-host * { transition: none !important; animation: none !important; }
}
</style>
